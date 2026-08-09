"""flip doctor — lint a notebook against the spec and its profile (SPEC §15).

Every check is independent and tolerant: a missing optional file is simply
skipped unless the profile requires it, and one broken file never stops the
other checks from running. `run_doctor` only reports; exiting non-zero on
ERROR findings is the CLI's job.

v0.4 check surface: OKF conformance (every entity/concept page parses and
carries a type; reserved index.md/log.md files stay frontmatter-free),
id integrity (prefix routing, aliases, duplicates), link rot (dangling
relative citations — legal in OKF, counted here), corroboration drift and
under-verified claims (recomputed via claims.corroboration_count; ungraded
sources never count), stale freshness, orphan custody (pages ↔ raw bytes ↔
provenance events), profile minimums with status gating, forced-policy
mismatches against the flat manifest fields, and — for notebooks graduated
from a beat (SPEC §14) — that the manifest's `links.beat` still resolves to
the beat root above.

`run_workspace_doctor` is the second, separate surface (SPEC §18): it lints
a workspace — the handle table, notebook coverage, uid lineage, and
cross-notebook ambiguity — and is the only doctor entry point with a `fix`
mode. doctor imports workspace; workspace never imports doctor.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import beliefs as beliefs_mod
from . import pages, workspace
from . import sources as sources_mod
from .beat import find_beat_root, load_beat
from .claims import STATUSES as CLAIM_STATUSES  # claim status enum (SPEC §7)
from .claims import corroboration_count, has_gating_verification, uncountable_sources
from .claims import source_ids as claim_source_ids

# Forecast enums and the typed-ref grammar (SPEC §7), from the owning module.
from .forecast import BEARS_ON_RE, FORECAST_STATUSES, PREDICTABILITY
from .manifest import STATUSES, VISIBILITIES, Manifest, load_manifest, save_manifest
from .profiles import SECTIONS, Profile, list_profiles, load_profile

# Source page enums (SPEC §5.4), re-exported from the owning module.
from .sources import FRESHNESS, GRADES, INDEPENDENCE
from .util import (
    HANDLE_RE,
    ROOT_FILE,
    WORKSPACE_FILE,
    age_months,
    is_notebook_root,
    new_uid,
    read_jsonl,
    split_ref,
)

PROVENANCE = "sources/_provenance.jsonl"
# Every JSONL ledger the format defines; each must at least parse.
LEDGERS = (PROVENANCE, "derived/_derivations.jsonl", "log/log.jsonl", "log/passed.jsonl")

# Entity directories whose pages must carry a compact id; sessions are entity
# pages too but have no id scheme (SPEC §8), so they are exempt here.
_ID_DIRS = ("references", "claims", "beliefs", "decisions", "questions", "forecasts")
_DIR_PREFIXES: dict[str, tuple[str, ...]] = {
    d: tuple(sorted(p for p, dd in pages.PREFIX_DIR.items() if dd == d)) for d in _ID_DIRS
}
_ID_RE = re.compile(r"^([A-Z]+)(\d+)$")

# Leading major.minor of a `flip:` profile version ("0.5", "0.5.1", …); uid
# arrived with 0.5, so missing-uid is gated on what the manifest declares.
_FLIP_VERSION_RE = re.compile(r"^(\d+)\.(\d+)")

# A qualified alias, `handle:ID` (SPEC §18) — what ensure_qualified_aliases
# writes and what the workspace stale-alias check inspects.
_QUALIFIED_ALIAS_RE = re.compile(r"^([a-z][a-z0-9-]*):([A-Z]+\d+)$")

# Directories scanned for OKF conformance, id integrity, and link rot: entity
# pages plus graduated prose under analysis/ (concept pages: any type fits,
# SPEC §3; H# hypothesis ids live there, SPEC §9).
_PAGE_DIRS = pages.SCAN_DIRS

# Manifest statuses where profile minimums are completion requirements that
# have come due: missing required paths are ERRORs (SPEC §13). While the
# notebook is still active/dormant they are WARNs — files appear with use.
CLOSED_STATUSES = ("done", "published", "archived")

_LINK_RE = re.compile(r"\]\(([^)\s]+)")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:")

# The check registry (design-composition-0.14.md, ship item 3): every finding
# code doctor can emit, promoted to a stable, documented API. Discipline files
# reference these codes in gates/checks (Form A), and disciplines.py validates
# against this set — a gate referencing a code not listed here is ERROR
# bad-discipline. Maintained by hand; test_disciplines.py asserts every code
# literal in this file is registered, so the two can't drift.
CHECK_CODES: frozenset[str] = frozenset({
    # manifest, profile, kind
    "bad-manifest", "bad-status", "bad-visibility", "missing-uid",
    "unknown-kind", "missing-required", "policy-mismatch", "missing-section",
    "missing-notebook", "kind-gap",
    # beat link
    "broken-beat-link", "deprecated-ref-separator",
    # OKF conformance, ids, links, ledgers
    "bad-jsonl", "bad-frontmatter", "missing-type", "reserved-frontmatter",
    "duplicate-id", "missing-id", "bad-id", "wrong-prefix", "missing-alias",
    "dangling-citation",
    # sources: custody, judgment, freshness
    "orphan-custody", "unlogged-capture", "bad-enum", "pre-08-vocabulary",
    "enum-without-evidence", "seeded-grade", "grade-drift",
    "orphan-provenance", "stale-freshness", "unregistered-raw",
    "source-drift", "drifted-evidence", "thin-capture", "unvocabularied-method",
    # claims
    "two-object", "pre-okf02-layout", "corroboration-drift", "under-verified",
    "unaudited-claim", "provenance-open", "unlocatable-recomputation",
    # beliefs — a claim about believers, never about the world (SPEC §7.1)
    "belief-as-evidence", "belief-two-object", "unfunctioned-belief",
    "unfalsifiable-belief", "unmeasured-prevalence", "measurement-drift",
    "dangling-about", "impure-about", "untested-belief",
    # transcripts: pinned passages
    "dangling-excerpt", "excerpt-drift", "unbacked-excerpt",
    # shared causes — one line that explains many symptoms
    "vocabulary-drift",
    # forecasts & clusters
    "undated-forecast", "missing-annul-if", "overdue-forecast", "untyped-ref",
    "dangling-bears-on", "scored-cluster", "dangling-proxy",
    "impure-inference-link", "dangling-inference-link",
    # workspace mode
    "bad-workspace-file", "handle-syntax", "dangling-workspace-entry",
    "unregistered-notebook", "duplicate-uid", "stale-alias", "ambiguous-id",
    "cross-notebook-drift", "slug-collision",
    # disciplines & slot composition (0.14)
    "unknown-discipline", "discipline-moved", "bad-discipline",
    "unresolved-slot", "discipline-dependency", "slot-name-mismatch",
    "slot-unfilled",
})


@dataclass
class Finding:
    level: str  # "ERROR" | "WARN"
    code: str  # short slug, e.g. "orphan-custody"
    message: str  # one actionable line
    path: str  # path relative to the notebook root
    # An "appears-with-use" notice — a profile minimum not yet due (WARN while
    # the notebook is active/dormant). Rendered under a distinct "expected
    # until use" section so standing notices stop training operators (and
    # agents re-running doctor for reassurance) to tune the channel out (E3).
    expected: bool = False


def _error(code: str, message: str, path: str) -> Finding:
    return Finding("ERROR", code, message, path)


def _warn(code: str, message: str, path: str, expected: bool = False) -> Finding:
    return Finding("WARN", code, message, path, expected=expected)


def _rel(page: pages.Page, root: Path) -> str:
    return page.path.relative_to(root).as_posix()


def run_doctor(root: Path) -> list[Finding]:
    findings: list[Finding] = []

    manifest = _check_manifest(root, findings)
    _check_uid(manifest, findings)
    profile = _check_profile(root, manifest, findings)
    _check_beat_link(root, manifest, findings)

    provenance = _check_ledgers(root, findings)
    by_dir = _collect_pages(root, findings)  # okf-conformance: parses + typed
    _check_reserved_files(root, findings)
    _check_notebook_md(root, profile, findings)
    _check_ids(root, by_dir, findings)
    _check_links(root, by_dir, findings)

    source_pages = [p for p in by_dir.get("references", []) if p.fm.get("type") == "Source"]
    _check_sources(root, source_pages, provenance, findings)
    _check_freshness(root, source_pages, profile, findings)
    _check_raw(root, provenance, findings)
    claim_pages = [p for p in by_dir.get("claims", []) if p.fm.get("type") == "Claim"]
    belief_pages = [p for p in by_dir.get("beliefs", []) if p.fm.get("type") == "Belief"]
    _check_claims(root, claim_pages, source_pages, profile, findings)
    _check_beliefs(root, belief_pages, claim_pages, source_pages, by_dir, findings)
    _check_transcripts(root, source_pages, claim_pages, findings)
    _check_forecasts(root, by_dir, findings)
    _check_provenance_open(root, manifest, claim_pages, source_pages, findings)
    _check_kind_contract(root, manifest, findings)
    _check_disciplines(root, manifest, findings)
    _lead_with_causes(root, source_pages, claim_pages, findings)
    return findings


def _lead_with_causes(
    root: Path,
    source_pages: list[pages.Page],
    claim_pages: list[pages.Page],
    findings: list[Finding],
) -> None:
    """Insert a cause line ahead of the symptoms that share it.

    272 warnings and 4 errors once had ONE root cause, every warning on its own
    line, and the errors looked like an evidence problem when they were a
    vocabulary problem. Anyone triaging that reasonably concludes the notebook
    is deeply unsound; the truth was that one field changed meaning. The
    per-source findings stay (they carry the paths, and --json keeps
    everything) — this just puts the explanation first.
    """
    stale = sorted(p.id or "?" for p in source_pages if sources_mod.unmigrated(p.fm))
    if not stale:
        return
    affected = sorted(
        page.id or "?"
        for page in claim_pages
        if uncountable_sources([p.fm for p in source_pages], claim_source_ids(page.fm))
    )
    msg = (
        f"{len(stale)} source(s) carry pre-0.8 independence vocabulary, so they "
        "corroborate nothing and derive grade '?'"
    )
    if affected:
        msg += (
            f"; this also explains the corroboration counts on {len(affected)} claim(s) "
            f"({', '.join(affected)})"
        )
    msg += (
        f". One cause, {len(stale) + len(affected)} symptom(s): fix it with `flip migrate` "
        "then re-judge the parked sources (`flip grade <id> --independence … --basis …`, "
        "`flip grade <id> --explain` to see what moves the letter)"
    )
    findings.insert(0, _warn("vocabulary-drift", msg, ROOT_FILE))


def _check_provenance_open(
    root: Path,
    manifest: Manifest | None,
    claim_pages: list[pages.Page],
    source_pages: list[pages.Page],
    findings: list[Finding],
) -> None:
    """PRIMARY-OPEN is a legitimate mid-pass state, not a shippable one
    (SPEC §5.5): once the notebook is done/published/archived, a load-bearing
    claim resting on a source whose chain-walk never reached a terminus is an
    ERROR; while active it's a WARN so the walk gets finished, not forgotten."""
    open_sources = {
        p.id for p in source_pages if str(p.fm.get("provenance_state") or "") == "PRIMARY-OPEN"
    }
    if not open_sources:
        return
    closed = manifest is not None and manifest.status in CLOSED_STATUSES
    from .claims import source_ids as claim_source_ids_fn

    for page in claim_pages:
        if not page.fm.get("load_bearing"):
            continue
        resting = sorted(set(claim_source_ids_fn(page.fm)) & open_sources)
        if not resting:
            continue
        rel = _rel(page, root)
        msg = (
            f"load-bearing claim {page.id or '?'} rests on {', '.join(resting)} whose "
            "provenance chain is PRIMARY-OPEN (walk not finished); finish the walk and "
            f"record a terminal state (`flip source provenance {resting[0]} …`)"
        )
        findings.append(
            _error("provenance-open", msg, rel) if closed else _warn("provenance-open", msg, rel)
        )


def run_workspace_doctor(ws_root: Path, fix: bool = False) -> list[Finding]:
    """Workspace-mode checks (SPEC §18): the table itself (bad-workspace-file,
    handle-syntax, dangling-workspace-entry), lineage sanity (duplicate-uid,
    missing-uid), coverage (unregistered-notebook), and cross-notebook
    ambiguity (ambiguous-id, slug-collision — aggregated, informational).
    `fix` binds unregistered notebooks, backfills uids, and regenerates
    qualified aliases. Finding.path is workspace-root-relative."""
    findings: list[Finding] = []
    ws_file = WORKSPACE_FILE.as_posix()
    try:
        ws = workspace.load_workspace(ws_root)
    except SystemExit as e:
        # Subsumes duplicate handles: duplicate TOML keys are a parse error.
        findings.append(_error("bad-workspace-file", str(e), ws_file))
        return findings

    bad_handles = {h for h in ws.notebooks if not HANDLE_RE.match(h)}
    for handle in sorted(bad_handles):
        findings.append(
            _error(
                "handle-syntax",
                f"handle '{handle}' is invalid (lowercase letters, digits, and "
                f"hyphens, starting with a letter); edit {ws_file} or rebind with "
                "`flip ws add --as` — an invalid handle also blocks --fix table writes",
                ws_file,
            )
        )

    # Entries that check out on disk: handle -> notebook root. Notebooks bound
    # under an invalid handle are excluded — the ERROR above is the finding,
    # and no fix should write that handle into aliases.
    bound: dict[str, Path] = {}
    for handle in sorted(ws.notebooks):
        if handle in bad_handles:
            continue
        rel = ws.notebooks[handle]
        nb_root = ws_root / rel
        if not nb_root.is_dir():
            findings.append(
                _error(
                    "dangling-workspace-entry",
                    f"handle '{handle}' points at {rel}, which does not exist; "
                    f"restore the directory or `flip ws rm {handle}`",
                    ws_file,
                )
            )
        elif not is_notebook_root(nb_root):
            findings.append(
                _error(
                    "dangling-workspace-entry",
                    f"handle '{handle}' points at {rel}, which is not a notebook root "
                    f"(no index.md with flip manifest frontmatter); `flip ws rm {handle}` "
                    "unbinds it",
                    ws_file,
                )
            )
        else:
            bound[handle] = nb_root

    # Coverage: every notebook under the root should be in the table.
    bound_rels = set(ws.notebooks.values())
    table_writable = fix and not bad_handles  # never rewrite a broken table
    dirty_table = False
    for nb_root in workspace.discover_notebooks(ws_root):
        rel = nb_root.relative_to(ws_root).as_posix()
        if rel in bound_rels:
            continue
        try:
            slug = load_manifest(nb_root).slug
        except SystemExit:
            slug = nb_root.name
        if table_writable:
            handle = workspace.default_handle(slug, set(ws.notebooks))
            ws.notebooks[handle] = rel
            bound[handle] = nb_root
            dirty_table = True
            msg = f"notebook '{slug}' at {rel} was not in the workspace table; bound as '{handle}'"
        else:
            msg = (
                f"notebook '{slug}' at {rel} is not in the workspace table; "
                f"`flip ws add {rel}` binds it"
            )
        findings.append(_warn("unregistered-notebook", msg, rel))
    if dirty_table:
        workspace.save_workspace(ws)

    # Lineage: every bound notebook carries a uid, and no uid is bound twice.
    checked: list[tuple[str, Path, str]] = []  # (handle, nb_root, rel)
    by_uid: dict[str, list[str]] = {}
    for handle in sorted(bound):
        nb_root, rel = bound[handle], ws.notebooks[handle]
        try:
            m = load_manifest(nb_root)
        except SystemExit as e:
            findings.append(
                _error(
                    "dangling-workspace-entry",
                    f"handle '{handle}': the manifest at {rel}/{ROOT_FILE} is unreadable — {e}",
                    f"{rel}/{ROOT_FILE}",
                )
            )
            continue
        checked.append((handle, nb_root, rel))
        if m.uid:
            by_uid.setdefault(m.uid, []).append(handle)
        else:
            if fix:
                m.uid = new_uid()
                save_manifest(nb_root, m)
                msg = f"notebook '{handle}' had no uid; minted {m.uid}"
            else:
                msg = (
                    f"notebook '{handle}' has no uid — the stable identity that travels "
                    "with exports and imports (SPEC §4); `flip doctor --workspace --fix` "
                    "backfills one"
                )
            findings.append(_warn("missing-uid", msg, f"{rel}/{ROOT_FILE}"))
    for uid in sorted(by_uid):
        handles = by_uid[uid]
        if len(handles) >= 2:
            findings.append(
                _warn(
                    "duplicate-uid",
                    f"notebooks {', '.join(handles)} share uid {uid} — the same lineage "
                    "bound twice; keep one and `flip ws rm` the other(s)",
                    ws_file,
                )
            )

    # Page inventory across bound notebooks: stale qualified aliases (per page),
    # then bare ids and filename stems living in ≥2 notebooks (aggregated —
    # informational, so one finding each, examples capped).
    id_owners: dict[str, set[str]] = {}
    stem_owners: dict[str, set[str]] = {}
    stale_by_handle: dict[str, set[str]] = {}
    # Cross-notebook consistency (L16): the same claim tracked in several
    # notebooks must not silently sit in different states — three notebooks,
    # one fact, three states, zero mechanisms was the motivating failure.
    claim_states: dict[str, dict[str, str]] = {}  # normalized text -> handle -> status
    for handle, nb_root, rel in checked:
        # Handles binding this same notebook in an enclosing or nested
        # workspace table are that table's aliases, not stale ones — stripping
        # them here would fight the other workspace's doctor forever.
        legitimate = {handle} | workspace.other_workspace_handles(ws_root, nb_root)
        for dirname in pages.SCAN_DIRS:
            found, _errors = pages.iter_pages_tolerant(nb_root, dirname)
            for page in found:
                stem_owners.setdefault(page.path.stem, set()).add(handle)
                if dirname == "claims" and str(page.fm.get("type", "")) == "Claim":
                    norm = " ".join(str(page.fm.get("description", "")).lower().split())
                    if norm:
                        claim_states.setdefault(norm, {})[handle] = str(
                            page.fm.get("status", "asserted")
                        )
                entity_id = page.id
                if not entity_id:
                    continue
                id_owners.setdefault(entity_id, set()).add(handle)
                stale = sorted(
                    {
                        qm.group(1)
                        for a in pages.as_list(page.fm.get("aliases"))
                        if (qm := _QUALIFIED_ALIAS_RE.match(str(a)))
                        and qm.group(2) == entity_id
                        and qm.group(1) not in legitimate
                    }
                )
                if stale:
                    stale_by_handle.setdefault(handle, set()).update(stale)
                    listed = ", ".join(f"{h}:{entity_id}" for h in stale)
                    action = (
                        "regenerated"
                        if fix
                        else "`flip doctor --workspace --fix` regenerates them"
                    )
                    findings.append(
                        _warn(
                            "stale-alias",
                            f"alias(es) {listed} no longer match the bound handle "
                            f"'{handle}'; {action}",
                            page.path.relative_to(ws_root).as_posix(),
                        )
                    )
    ambiguous = sorted(i for i, owners in id_owners.items() if len(owners) >= 2)
    if ambiguous:
        shown = "; ".join(f"{i} ({', '.join(sorted(id_owners[i]))})" for i in ambiguous[:5])
        more = f"; +{len(ambiguous) - 5} more" if len(ambiguous) > 5 else ""
        findings.append(
            _warn(
                "ambiguous-id",
                f"{len(ambiguous)} id(s) live in more than one bound notebook — bare "
                f"refs there need qualifying (handle:id): {shown}{more}",
                ".",
            )
        )
    drifted = sorted(
        (text, states) for text, states in claim_states.items()
        if len(states) >= 2 and len(set(states.values())) >= 2
    )
    for text, states in drifted[:10]:
        listed = ", ".join(f"{h}: {s}" for h, s in sorted(states.items()))
        findings.append(
            _warn(
                "cross-notebook-drift",
                f'the claim "{text[:80]}" is tracked in {len(states)} notebooks with '
                f"diverging statuses ({listed}); reconcile them — supersede or update, "
                "never leave the corpus disagreeing with itself",
                ".",
            )
        )
    if len(drifted) > 10:
        findings.append(
            _warn(
                "cross-notebook-drift",
                f"+{len(drifted) - 10} more claims tracked in multiple notebooks with "
                "diverging statuses",
                ".",
            )
        )
    collisions = sorted(s for s, owners in stem_owners.items() if len(owners) >= 2)
    if collisions:
        shown = "; ".join(f"{s} ({', '.join(sorted(stem_owners[s]))})" for s in collisions[:5])
        more = f"; +{len(collisions) - 5} more" if len(collisions) > 5 else ""
        findings.append(
            _warn(
                "slug-collision",
                f"{len(collisions)} page name(s) appear in more than one bound notebook "
                f"— name-based wikilinks may land in the wrong one: {shown}{more}",
                ".",
            )
        )

    if fix:
        # Strip stale qualified aliases, then (re)qualify every bound notebook.
        # ensure_qualified_aliases rewrites only pages whose alias list actually
        # changes, so a second --fix run touches nothing.
        for handle, nb_root, _rel in checked:
            for old in sorted(stale_by_handle.get(handle, set())):
                workspace.ensure_qualified_aliases(nb_root, handle, old_handle=old)
            workspace.ensure_qualified_aliases(nb_root, handle)
    return findings


# --- manifest & profile -------------------------------------------------------


def _check_manifest(root: Path, findings: list[Finding]) -> Manifest | None:
    try:
        manifest = load_manifest(root)
    except SystemExit as e:
        findings.append(_error("bad-manifest", str(e), ROOT_FILE))
        return None
    except Exception as e:  # defensive: any other corruption is still a finding
        findings.append(_error("bad-manifest", f"{ROOT_FILE} is not a valid manifest: {e}", ROOT_FILE))
        return None
    if manifest.status not in STATUSES:
        findings.append(
            _error(
                "bad-status",
                f"status '{manifest.status}' invalid (one of: {', '.join(STATUSES)})",
                ROOT_FILE,
            )
        )
    if manifest.visibility not in VISIBILITIES:
        findings.append(
            _error(
                "bad-visibility",
                f"visibility '{manifest.visibility}' invalid (one of: {', '.join(VISIBILITIES)})",
                ROOT_FILE,
            )
        )
    return manifest


def _check_uid(manifest: Manifest | None, findings: list[Finding]) -> None:
    """uid arrived with profile 0.5 (SPEC §4): WARN only when the manifest
    *declares* flip 0.5+ and still has none — un-migrated 0.4 notebooks stay
    quiet until `flip migrate` mints one."""
    if manifest is None or manifest.uid:
        return
    version = _FLIP_VERSION_RE.match(manifest.flip_version)
    if not version or (int(version.group(1)), int(version.group(2))) < (0, 5):
        return
    findings.append(
        _warn(
            "missing-uid",
            f"manifest declares flip: \"{manifest.flip_version}\" but has no uid — "
            "the stable identity that travels with exports and imports (SPEC §4); "
            "run `flip migrate` to mint one",
            ROOT_FILE,
        )
    )


def _check_profile(
    root: Path, manifest: Manifest | None, findings: list[Finding]
) -> Profile | None:
    if manifest is None:
        return None
    try:
        profile = load_profile(manifest.kind, root)
    except SystemExit:
        findings.append(
            _error(
                "unknown-kind",
                f"kind '{manifest.kind}' matches no profile; set kind to one of "
                f"{', '.join(list_profiles())} or add .flip/profiles/{manifest.kind}.toml",
                ROOT_FILE,
            )
        )
        return None
    closed = manifest.status in CLOSED_STATUSES
    detail = (
        f"required before status '{manifest.status}'"
        if closed
        else "it appears with use; required before done/published/archived"
    )
    for rel in profile.requires:
        if not (root / rel).exists():
            msg = f"profile '{profile.id}' requires {rel} ({detail}); create it"
            # Not yet closed: this is an appears-with-use notice (expected),
            # not a real finding — segregated in the CLI's output (E3).
            findings.append(
                _error("missing-required", msg, rel)
                if closed
                else _warn("missing-required", msg, rel, expected=True)
            )
    policy = manifest.policy
    for key, want in profile.forced_policy.items():
        have = policy.get(key)
        if have != want:
            findings.append(
                _error(
                    "policy-mismatch",
                    f"profile '{profile.id}' forces {key} = {want!r} but the manifest has "
                    f"{have!r}; set {key} in the {ROOT_FILE} frontmatter",
                    ROOT_FILE,
                )
            )
    return profile


def _check_beat_link(root: Path, manifest: Manifest | None, findings: list[Finding]) -> None:
    """A notebook graduated from a beat carries `links: {beat: "<slug>:<TH#>"}`
    (SPEC §14; '#' is the pre-0.5 separator, read until 0.10). Verify the link
    still resolves — a beat root above the notebook whose slug matches, holding
    the thread — and WARN when it does not: moved notebooks keep working, but
    the beat's memory has lost them."""
    if manifest is None:
        return
    link = manifest.links.get("beat")
    if not link:
        return
    link = str(link)
    if ":" in link:
        beat_slug, _, thread_id = link.partition(":")
    else:
        beat_slug, _, thread_id = link.partition("#")
        if "#" in link:
            findings.append(
                _warn(
                    "deprecated-ref-separator",
                    f"links.beat '{link}' uses '#'; the separator is now ':' — run "
                    "`flip migrate` ('#' reads are removed in 0.10)",
                    ROOT_FILE,
                )
            )
    fix = "move the notebook back under its beat or update links.beat in index.md"
    beat_root = find_beat_root(root)
    if beat_root is None:
        findings.append(
            _warn("broken-beat-link",
                  f"links.beat is '{link}' but no beat root (index.md with flip_beat "
                  f"frontmatter) exists above the notebook; {fix}", ROOT_FILE)
        )
        return
    try:
        found_slug = load_beat(beat_root).slug
    except SystemExit as e:
        findings.append(
            _warn("broken-beat-link",
                  f"links.beat is '{link}' but the beat root above is unreadable: {e}",
                  ROOT_FILE)
        )
        return
    if found_slug != beat_slug:
        findings.append(
            _warn("broken-beat-link",
                  f"links.beat names beat '{beat_slug}' but the beat above is "
                  f"'{found_slug}' ({beat_root}); {fix}", ROOT_FILE)
        )
    elif thread_id and pages.find_by_id(beat_root, thread_id) is None:
        findings.append(
            _warn("broken-beat-link",
                  f"links.beat points at thread {thread_id} but the beat at "
                  f"{beat_root} has no page with that id; {fix}", ROOT_FILE)
        )


# --- ledgers -------------------------------------------------------------------


def _check_ledgers(root: Path, findings: list[Finding]) -> list[dict]:
    """Every JSONL ledger must parse; returns the provenance rows for custody checks."""
    provenance: list[dict] = []
    for rel in LEDGERS:
        try:
            rows = read_jsonl(root / rel)
        except ValueError as e:
            findings.append(_error("bad-jsonl", f"{e}; fix or remove that line", rel))
            continue
        if rel == PROVENANCE:
            provenance = rows
    return provenance


# --- OKF conformance ------------------------------------------------------------


def _collect_pages(root: Path, findings: list[Finding]) -> dict[str, list[pages.Page]]:
    """Parse every non-reserved page under the entity dirs, analysis/, and
    notebook.md: unparseable frontmatter is an ERROR, a missing `type` a WARN
    (OKF: every concept page declares what it is)."""
    by_dir: dict[str, list[pages.Page]] = {}
    for dirname in _PAGE_DIRS:
        found, errors = pages.iter_pages_tolerant(root, dirname)
        by_dir[dirname] = found
        for path, err in errors:
            rel = path.relative_to(root).as_posix()
            findings.append(
                _error("bad-frontmatter", f"{err}; fix the YAML frontmatter", rel)
            )
        for page in found:
            if not page.fm.get("type"):
                findings.append(
                    _warn(
                        "missing-type",
                        f"page has no `type` frontmatter (OKF conformance); add e.g. "
                        f"type: {_suggested_type(dirname)}",
                        _rel(page, root),
                    )
                )
    notebook = root / "notebook.md"
    if notebook.is_file():
        try:
            fm, _body = pages.parse(notebook.read_text(encoding="utf-8"))
        except ValueError as e:
            findings.append(_error("bad-frontmatter", f"{e}; fix the YAML frontmatter", "notebook.md"))
        else:
            if not fm.get("type"):
                findings.append(
                    _warn(
                        "missing-type",
                        "notebook.md has no `type` frontmatter; add type: Notebook",
                        "notebook.md",
                    )
                )
    return by_dir


def _suggested_type(dirname: str) -> str:
    return {
        "references": "Source",
        "claims": "Claim",
        "decisions": "Decision",
        "questions": "Question",
        "forecasts": "Forecast",
        "sessions": "Work Session",
    }.get(dirname, "Note")


def _check_reserved_files(root: Path, findings: list[Finding]) -> None:
    """index.md/log.md are OKF reserved: only the root index carries frontmatter."""
    reserved = [Path(d) / "index.md" for d in _PAGE_DIRS] + [Path("log.md")]
    for rel in reserved:
        path = root / rel
        if not path.is_file():
            continue
        try:
            fm, _body = pages.parse(path.read_text(encoding="utf-8"))
        except ValueError as e:
            findings.append(_error("bad-frontmatter", f"{e}; fix the YAML frontmatter", rel.as_posix()))
            continue
        if fm:
            findings.append(
                _error(
                    "reserved-frontmatter",
                    f"{rel.as_posix()} is an OKF reserved file and must not carry frontmatter "
                    "(only the root index.md does); it is generated — remove the frontmatter "
                    "or delete the file and let flip regenerate it",
                    rel.as_posix(),
                )
            )


def _check_notebook_md(root: Path, profile: Profile | None, findings: list[Finding]) -> None:
    path = root / "notebook.md"
    if not path.is_file():
        findings.append(
            _error(
                "missing-notebook",
                "notebook.md missing; it is required for every notebook (SPEC §3)",
                "notebook.md",
            )
        )
        return
    if profile is None:
        return
    try:
        _fm, body = pages.parse(path.read_text(encoding="utf-8"))
    except ValueError:
        return  # already an ERROR from _collect_pages; headings can't be trusted
    headings = [
        line.lstrip("#").strip().lower()
        for line in body.splitlines()
        if line.lstrip().startswith("#")
    ]
    for section in profile.sections:
        heading = SECTIONS.get(section, {}).get("heading", section)
        if not any(heading.lower() in h for h in headings):
            findings.append(
                _warn(
                    "missing-section",
                    f"notebook.md has no '{heading}' heading "
                    f"(profile '{profile.id}' expects section '{section}')",
                    "notebook.md",
                )
            )


# --- id integrity ---------------------------------------------------------------


def _check_ids(root: Path, by_dir: dict[str, list[pages.Page]], findings: list[Finding]) -> None:
    seen: dict[str, str] = {}  # id -> first page rel path (across all scanned dirs)
    for dirname in _PAGE_DIRS:
        for page in by_dir.get(dirname, []):
            rel = _rel(page, root)
            entity_id = page.id
            if entity_id:
                if entity_id in seen:
                    findings.append(
                        _error(
                            "duplicate-id",
                            f"id {entity_id} is already used by {seen[entity_id]}; "
                            "ids are immutable and never reused — give this page a fresh id",
                            rel,
                        )
                    )
                else:
                    seen[entity_id] = rel
            if dirname not in _ID_DIRS:
                continue  # sessions and analysis/ pages need no id
            if not entity_id:
                findings.append(
                    _error(
                        "missing-id",
                        f"entity page has no id; add id + aliases frontmatter "
                        f"(next free {'/'.join(_DIR_PREFIXES[dirname])}#)",
                        rel,
                    )
                )
                continue
            m = _ID_RE.match(entity_id)
            if not m:
                findings.append(
                    _error(
                        "bad-id",
                        f"id '{entity_id}' is not a compact id (<PREFIX><number>, e.g. "
                        f"{_DIR_PREFIXES[dirname][0]}3)",
                        rel,
                    )
                )
                continue
            prefix = m.group(1)
            if prefix not in _DIR_PREFIXES[dirname]:
                where = pages.PREFIX_DIR.get(prefix)
                fix = f"move the page to {where}/" if where else "fix the id"
                findings.append(
                    _error(
                        "wrong-prefix",
                        f"id {entity_id} does not belong in {dirname}/ (its prefixes: "
                        f"{', '.join(_DIR_PREFIXES[dirname])}); {fix} or re-id the page",
                        rel,
                    )
                )
            aliases = pages.as_list(page.fm.get("aliases"))
            if entity_id not in [str(a) for a in aliases]:
                findings.append(
                    _warn(
                        "missing-alias",
                        f"aliases does not contain {entity_id} — aliases feed Obsidian "
                        f"autocomplete ([[{entity_id} suggests this page), they do not make "
                        f"a raw [[{entity_id}]] resolve; add aliases: [{entity_id}]",
                        rel,
                    )
                )


# --- link rot --------------------------------------------------------------------


def _check_links(root: Path, by_dir: dict[str, list[pages.Page]], findings: list[Finding]) -> None:
    """Relative markdown links to missing .md files inside the notebook: dangling
    citations are legal in OKF (SPEC §6.1) but counted, one WARN per link."""
    resolved_root = root.resolve()
    for dirname in _PAGE_DIRS:
        for page in by_dir.get(dirname, []):
            for target in _LINK_RE.findall(page.body):
                target = target.split("#", 1)[0]
                if not target.endswith(".md") or _SCHEME_RE.match(target):
                    continue
                base = resolved_root if target.startswith("/") else page.path.parent
                candidate = (base / target.lstrip("/")).resolve()
                if not candidate.is_relative_to(resolved_root):
                    continue  # points outside the notebook: not ours to judge
                if not candidate.exists():
                    findings.append(
                        _warn(
                            "dangling-citation",
                            f"link to {target} points at a missing file; capture the source "
                            "(`flip add-source`) or fix the link",
                            _rel(page, root),
                        )
                    )


# --- sources: custody, provenance, freshness --------------------------------------


def _check_sources(
    root: Path, source_pages: list[pages.Page], provenance: list[dict], findings: list[Finding]
) -> None:
    # A row that landed no bytes is a recorded *finding* — "searched, gone" is
    # deliberately distinguishable from "did not look" (L5) — so it has no page
    # by design and must not read as corruption. Excluding it here is what stops
    # orphan-provenance from nagging about an id whose whole point is the
    # absence, with hand-editing JSONL as the only way to silence it. Both
    # flavors count: `failed` (the tool broke) and `not-captured` (the tool ran
    # fine and the document was not there).
    logged_ids = {
        str(p.get("source_id"))
        for p in provenance
        if p.get("source_id")
        and str(p.get("status") or "") not in sources_mod.UNCAPTURED_STATUSES
    }
    page_ids = {p.id for p in source_pages if p.id}
    for page in source_pages:
        sid = page.id or "?"
        rel = _rel(page, root)
        local = page.fm.get("local")
        if local and not (root / str(local)).exists():
            findings.append(
                _error(
                    "orphan-custody",
                    f"source {sid}: local file {local} missing; recapture it or fix "
                    "the page's `local` path",
                    str(local),
                )
            )
        if page.id and page.id not in logged_ids:
            findings.append(
                _warn(
                    "unlogged-capture",
                    f"source {sid} has no capture event in {PROVENANCE}; log the acquisition",
                    rel,
                )
            )
        for field, valid in (
            ("grade", GRADES),
            ("independence", INDEPENDENCE),
            ("freshness", FRESHNESS),
        ):
            value = page.fm.get(field)
            if value is not None and value not in valid:
                if field == "independence" and value in sources_mod.PRE_08_INDEPENDENCE:
                    # Name the fix that actually applies. `flip migrate`
                    # translates republisher/self-interested; it CANNOT
                    # translate 'original' (custody, not epistemics) and only
                    # parks it, so telling a parked page's owner to migrate is
                    # advice that does nothing.
                    support_now = page.fm.get("support")
                    support_now = support_now if isinstance(support_now, dict) else {}
                    if support_now.get("pre_08_grade"):
                        msg = (
                            f"source {sid}: independence '{value}' is pre-0.8 vocabulary — it "
                            "encoded custody, not epistemics, so no migration can translate "
                            f"it. Derives grade '?' and corroborates nothing until re-read "
                            f"(the pre-0.8 letter was {support_now['pre_08_grade']}): "
                            f"`flip grade {sid} --independence … --basis …`"
                        )
                    else:
                        msg = (
                            f"source {sid}: independence '{value}' is pre-0.8 vocabulary and "
                            "is not a judgment flip can read — it corroborates nothing; run "
                            "`flip migrate` to adopt the support-tuple model"
                        )
                    findings.append(_warn("pre-08-vocabulary", msg, rel))
                    continue
                findings.append(
                    _error(
                        "bad-enum",
                        f"source {sid}: {field} '{value}' invalid (one of: {', '.join(valid)})",
                        rel,
                    )
                )
        pipeline = page.fm.get("pipeline")
        if pipeline is not None:
            ok_pipeline = str(pipeline) in sources_mod.PIPELINES or (
                str(pipeline).startswith("transferred:") and str(pipeline)[12:].strip()
            )
            if not ok_pipeline:
                findings.append(
                    _error(
                        "bad-enum",
                        f"source {sid}: pipeline '{pipeline}' invalid (one of: "
                        f"{', '.join(sources_mod.PIPELINES)}, or transferred:<steward>)",
                        rel,
                    )
                )
            if not str(page.fm.get("pipeline_evidence") or "").strip():
                findings.append(
                    _warn(
                        "enum-without-evidence",
                        f"source {sid}: pipeline '{pipeline}' has no pipeline_evidence "
                        "receipt — an enum alone is not self-evidencing; add one with "
                        f"`flip source pipeline {sid} {pipeline} --evidence …`",
                        rel,
                    )
                )
        state = page.fm.get("provenance_state")
        if state is not None and str(state) not in sources_mod.PROVENANCE_STATES:
            findings.append(
                _error(
                    "bad-enum",
                    f"source {sid}: provenance_state '{state}' invalid (one of: "
                    f"{', '.join(sources_mod.PROVENANCE_STATES)})",
                    rel,
                )
            )
        drifted = page.fm.get("drifted")
        if drifted:
            findings.append(
                _warn(
                    "source-drift",
                    f"source {sid}: the upstream coordinate has "
                    f"{'stopped serving' if drifted == 'gone' else 'changed'} since "
                    f"capture (rechecked {page.fm.get('last_checked', '?')}); custody "
                    "holds the cited bytes — re-capture with `flip add-source` if the "
                    "new version matters, or clear the flag with a fresh "
                    f"`flip source recheck {sid}` once resolved",
                    rel,
                )
            )
        support = page.fm.get("support") if isinstance(page.fm.get("support"), dict) else {}
        if support.get("seeded") == "legacy-grade":
            findings.append(
                _warn(
                    "seeded-grade",
                    f"source {sid}: grade {page.fm.get('grade', '?')} is a migration seed "
                    f"from a pre-0.8 authored letter; re-grade with the support tuple "
                    f"(`flip grade {sid} --independence … --basis …`) when the work next "
                    "touches it",
                    rel,
                    expected=True,
                )
            )
        elif sources_mod.judged(page.fm):
            derived = sources_mod.derive_grade(page.fm)
            stored = str(page.fm.get("grade") or "?")
            if stored != derived:
                findings.append(
                    _warn(
                        "grade-drift",
                        f"source {sid}: stored grade {stored} != derived {derived} "
                        "(grades are digests of the support tuple, never authored); "
                        f"re-run `flip grade {sid}` with any tuple field to refresh",
                        rel,
                    )
                )
    _check_capture_fidelity(root, provenance, page_ids, findings)
    for sid in sorted(logged_ids - page_ids):
        findings.append(
            _warn(
                "orphan-provenance",
                f"provenance records a capture for {sid} but references/ has no page with "
                "that id; restore the page (its id stays reserved either way)",
                PROVENANCE,
            )
        )


def _check_capture_fidelity(
    root: Path, provenance: list[dict], page_ids: set[str], findings: list[Finding]
) -> None:
    """Say what a capture actually achieved (SPEC §5.1).

    A capture that succeeded and brought back 800 bytes of consent wall
    produces the same sha256, the same ledger row, and the same page at grade
    "?" as one that brought back the article. Custody looks identical; the
    evidence is not. This is the same failure shape as a stored grade
    outliving its support tuple — something that reads as trustworthy while
    carrying nothing — so it gets named rather than left for a reader to
    notice.

    Only the LATEST successful event per source is judged: an early thin
    attempt superseded by a real capture is history, not a finding.
    """
    latest: dict[str, dict] = {}
    for event in provenance:
        sid = str(event.get("source_id") or "")
        if not sid or sid not in page_ids:
            continue
        if str(event.get("status") or "") in sources_mod.UNCAPTURED_STATUSES:
            continue
        if not event.get("sha256"):  # a recheck or failure row, not a capture
            continue
        # A multi-file capture writes one row per file. The flip.json envelope
        # is metadata, not content (it is always tiny — judging it would report
        # every enveloped capture as thin), and among the real files the
        # largest is the primary artifact, the same rule add_source uses to
        # pick the page's `local`.
        if Path(str(event.get("local_path") or "")).name == "flip.json":
            continue
        prior = latest.get(sid)
        same_capture = prior is not None and prior.get("ts") == event.get("ts")
        if same_capture and (prior.get("bytes") or 0) >= (event.get("bytes") or 0):
            continue
        latest[sid] = event
    for sid, event in sorted(latest.items()):
        fidelity = sources_mod.capture_fidelity(event)
        method = str(event.get("strategy") or "")
        if fidelity == "thin" and method == "record-only":
            # Declared, not discovered: someone said out loud that the document
            # was out of reach. Naming it anyway is the point of the check —
            # a record must never quietly read as the thing it stands for —
            # but it is expected-until-use, not a defect to chase.
            findings.append(
                _warn(
                    "thin-capture",
                    f"source {sid} is a record capture: custody holds flip's record of the "
                    "source, not the source. Honest and citable, and it corroborates "
                    "nothing — if a claim comes to rest on it, climb the ladder again or "
                    "close the search with `flip pass` (SPEC §5.1)",
                    PROVENANCE,
                    expected=True,
                )
            )
        elif fidelity == "thin":
            findings.append(
                _warn(
                    "thin-capture",
                    f"source {sid}: captured {event.get('bytes')} bytes of markup via "
                    f"'{method}' — too little to be the document. A consent wall, a "
                    "JS shell, or an error page served as 200 all look like this. "
                    "Check what landed in custody, then climb the ladder: an archive "
                    "replay, a publisher API, or a rendering fetcher (SPEC §5.1)",
                    PROVENANCE,
                )
            )
        elif fidelity == "unknown" and method:
            findings.append(
                _warn(
                    "unvocabularied-method",
                    f"source {sid}: capture strategy '{method}' is not a capture "
                    f"method (one of: {', '.join(sources_mod.CAPTURE_METHODS)}) — it "
                    "reads like a tool name. Methods travel between deployments and "
                    "tool names don't; have the fetcher report one in its envelope",
                    PROVENANCE,
                    expected=True,
                )
            )


def _check_freshness(
    root: Path, source_pages: list[pages.Page], profile: Profile | None, findings: list[Finding]
) -> None:
    """Stale freshness: a source dated past the profile threshold but still
    judged "fresh" needs a re-judgment, not silence."""
    months = profile.freshness_months if profile is not None else Profile(id="?").freshness_months
    today = datetime.now(timezone.utc).date()
    for page in source_pages:
        if page.fm.get("freshness") != "fresh":
            continue
        age = age_months(page.fm.get("date"), today)
        if age is not None and age >= months:
            sid = page.id or "?"
            findings.append(
                _warn(
                    "stale-freshness",
                    f"source {sid}: dated {page.fm.get('date')} (~{age} months old, threshold "
                    f"{months}) but freshness is still 'fresh'; re-judge it — "
                    f"`flip grade {sid} --freshness dated` or update the date",
                    _rel(page, root),
                )
            )


def _check_raw(root: Path, provenance: list[dict], findings: list[Finding]) -> None:
    raw = root / "sources" / "raw"
    if not raw.is_dir():
        return
    logged_paths = {str(p["local_path"]).rstrip("/") for p in provenance if p.get("local_path")}
    for path in sorted(raw.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        # A capture may be a directory (multi-file capture, SPEC §5.1): any file
        # under a logged local_path counts as registered.
        covered = rel in logged_paths or any(rel.startswith(p + "/") for p in logged_paths)
        if not covered:
            findings.append(
                _warn(
                    "unregistered-raw",
                    f"{rel} has no provenance record; log its capture in {PROVENANCE} "
                    "or remove the file",
                    rel,
                )
            )


# --- claims -----------------------------------------------------------------------


def _check_claims(
    root: Path,
    claim_pages: list[pages.Page],
    source_pages: list[pages.Page],
    profile: Profile | None,
    findings: list[Finding],
) -> None:
    source_fms = [p.fm for p in source_pages]
    by_id = {p.id: p.fm for p in source_pages if p.id}
    for page in claim_pages:
        cid = page.id or "?"
        rel = _rel(page, root)
        status = page.fm.get("status")
        if status is not None and status not in CLAIM_STATUSES:
            findings.append(
                _error(
                    "bad-enum",
                    f"claim {cid}: status '{status}' invalid "
                    f"(one of: {', '.join(CLAIM_STATUSES)})",
                    rel,
                )
            )
        # The two-object gate (SPEC §7): claims are verified, never scored —
        # a probability on a Claim is a Forecast wearing the wrong type.
        for key in ("probability", "confidence"):
            if key in page.fm:
                findings.append(
                    _error(
                        "two-object",
                        f"claim {cid} carries '{key}' — probabilities live on Forecast "
                        "pages, never Claims (the two-object rule, SPEC §7); move the "
                        "bet to `flip forecast add` or remove the key",
                        rel,
                    )
                )
        legacy = [
            key for key in ("supports", "verifications", "timestamp") if key in page.fm
        ]
        if not legacy and any(
            not isinstance(e, dict) for e in pages.as_list(page.fm.get("sources"))
        ):
            legacy = ["sources"]  # flat id list — the pre-0.7 shape
        if legacy:
            findings.append(
                _warn(
                    "pre-okf02-layout",
                    f"claim {cid} carries pre-0.7 frontmatter ({', '.join(legacy)}); "
                    "run `flip migrate` to adopt the OKF v0.2 layout",
                    rel,
                )
            )
        claim_sources = claim_source_ids(page.fm)
        corroboration = corroboration_count(source_fms, claim_sources)
        stored = page.fm.get("independent_corroboration")
        if stored is not None and stored != corroboration:
            findings.append(
                _warn(
                    "corroboration-drift",
                    f"claim {cid}: stored independent_corroboration {stored} != recomputed "
                    f"{corroboration}; run `flip claim status {cid} {status or 'asserted'}` "
                    "to refresh it",
                    rel,
                )
            )
        # A recomputation clears the `verified` gate on its own, so it has to be
        # locatable: `against` is where the session id, script path, or
        # derivation record goes. Without one, the claim records that a
        # recomputation happened with no way to reach the thing that did it —
        # an assertion with better manners.
        unlocatable = [
            v for v in pages.as_list(page.fm.get("verified"))
            if isinstance(v, dict) and str(v.get("method")) == "recomputation"
            and not pages.as_list(v.get("against"))
        ]
        if unlocatable:
            findings.append(
                _warn(
                    "unlocatable-recomputation",
                    f"claim {cid} rests on a recomputation with nothing cited in "
                    "`against` — name what recomputed it (a session id, script path, or "
                    f"derivation record): `flip claim verify {cid} --method recomputation "
                    "--against <ref>`",
                    rel,
                )
            )
        if not page.fm.get("load_bearing"):
            continue
        drifted_cited = sorted(
            s for s in dict.fromkeys(claim_sources)
            if s in by_id and by_id[s].get("drifted")
        )
        if drifted_cited:
            findings.append(
                _warn(
                    "drifted-evidence",
                    f"load-bearing claim {cid} rests on {', '.join(drifted_cited)} whose "
                    "upstream has drifted since capture; the cited bytes are custodied, "
                    "but review whether the claim survives the current version",
                    rel,
                )
            )
        if status == "verified" and profile is not None:
            # Recompute the bar with the shared helper (claims.corroboration_count:
            # deduped ids, judged + original only); never trust the stored count.
            # An adversarial/recomputation verification clears the gate too (A2).
            linked = [by_id[s] for s in dict.fromkeys(claim_sources) if s in by_id]
            has_grade_a = any(sources_mod.derive_grade(fm) == "A" for fm in linked)
            ok = (
                corroboration >= profile.claim_min_independent
                or (profile.claim_grade_a_suffices and has_grade_a)
                or has_gating_verification(page.fm)
            )
            if not ok:
                suffix = " or one grade-A primary" if profile.claim_grade_a_suffices else ""
                msg = (
                    f"claim {cid} is 'verified' with {corroboration} independent "
                    f"source(s); profile '{profile.id}' needs "
                    f"{profile.claim_min_independent}{suffix} — add corroboration, "
                    f"record an adversarial/recomputation check (`flip claim verify "
                    f"{cid} --method adversarial`), or set status needs-2nd"
                )
                # Never let the count stand alone as a verdict on the evidence:
                # an uncountable source drops out silently and the claim then
                # fails for a reason that has nothing to do with what it rests on.
                stale = uncountable_sources(source_fms, claim_sources)
                if stale:
                    msg += (
                        f". NOTE {', '.join(stale)} "
                        f"{'carries' if len(stale) == 1 else 'carry'} pre-0.8 "
                        "independence vocabulary and could not be counted either way, "
                        "so that count understates the evidence rather than measuring it"
                    )
                findings.append(_error("under-verified", msg, rel))
        elif status == "asserted" and corroboration == 0 and not pages.as_list(
            page.fm.get("verified")
        ):
            # A2: fire only when a load-bearing claim has *neither* corroboration
            # *nor* any verification record — ending the permanently-unsatisfiable
            # nag. Some corroboration or any recorded check silences it.
            findings.append(
                _warn(
                    "unaudited-claim",
                    f"load-bearing claim {cid} is 'asserted' with no corroboration or "
                    f"verification; link independent sources (`flip claim source add "
                    f"{cid} <src>`), record a check (`flip claim verify {cid} --method "
                    "adversarial`), or set status needs-2nd",
                    rel,
                )
            )


# --- beliefs: a claim about believers (SPEC §7.1) --------------------------------


# Keys that are verdicts on a proposition or on evidence for one. None of them
# belongs on a Belief page: the belief's own evidence is its measurements, and
# the proposition is judged on a Claim or never.
_BELIEF_FORBIDDEN = {
    "grade": "a source grade — beliefs are not sources; the survey behind a "
             "measurement is, and it is graded on its own references/ page",
    "independence": "a source judgment; grade the measurement's source instead",
    "support": "a source support tuple; it belongs to the measurement's source",
    "probability": "a forecast's scalar — a bet on the world lives on a Forecast",
    "confidence": "a forecast's scalar — a bet on the world lives on a Forecast",
    "load_bearing": "a claim's flag; what rests on evidence is the claim, and a "
                    "belief is never evidence for its own proposition",
    "independent_corroboration": "the claim key, meaning 'evidence for this "
                                 "assertion about the world' — no number on a "
                                 "belief page ever means that; the belief's own "
                                 "number is `measurement_corroboration`",
    "verified": "a claim's verification-event list; what could be verified here "
                "is the measurement, and it is counted, not attested",
    "sources": "OKF provenance, which on this page would read as 'sources for "
               "the proposition'; a belief's evidence hangs off each entry of "
               "`measurements`, never off the page as a whole",
}


def _check_beliefs(
    root: Path,
    belief_pages: list[pages.Page],
    claim_pages: list[pages.Page],
    source_pages: list[pages.Page],
    by_dir: dict[str, list[pages.Page]],
    findings: list[Finding],
) -> None:
    """Belief checks (SPEC §7.1). The separation, mechanized.

    `belief-as-evidence` is the one that matters and the only ERROR that fires
    on a *claim*: a claim whose `sources` list a `B#` is counting a fact about
    believers toward a fact about the world. The write paths refuse it
    (claims.refuse_belief_citations), so reaching doctor means it was written
    by hand or by another tool — which is exactly the case doctor exists for.

    `belief-two-object` is the mirror, from the belief side: the two-object
    rule (SPEC §7) already keeps grades off forecasts and probabilities off
    claims, and beliefs join it with a third column. A grade, a probability, a
    `load_bearing` flag or an `independent_corroboration` count on a belief
    page all say the same wrong thing — that the page's proposition has been
    weighed here.

    The rest are advisory and name the field the kind owes:
    `unfunctioned-belief` (an attributed belief with no function — prevalence
    sizes the room, function points at an intervention), `unfalsifiable-belief`
    (a working belief nothing could dislodge), `unmeasured-prevalence` (a
    measurement citing nothing judged — capture is custody, not judgment,
    SPEC §5.4), `measurement-drift` (stored count ≠ recomputed, exactly like
    `corroboration-drift`), `dangling-about`/`impure-about` (the world-side
    pointer), and `untested-belief` — a working belief the notebook holds with
    stance `unexamined` and nothing anywhere that would ever move it.
    """
    held = {p.id: p for p in belief_pages if p.id}
    # 1. The dangerous direction, checked on the claims.
    for page in claim_pages:
        cited = [s for s in dict.fromkeys(claim_source_ids(page.fm)) if s in held]
        if not cited:
            continue
        findings.append(
            _error(
                "belief-as-evidence",
                f"claim {page.id or '?'} cites {', '.join(cited)} as a source, but "
                f"{'that is a belief' if len(cited) == 1 else 'those are beliefs'} "
                "(beliefs/): a belief is evidence about BELIEVERS, never about what "
                'they believe, and counting one here is how "many people think X" '
                f"becomes \"X\". Drop it (`flip claim source rm {page.id or '<C#>'} "
                f"{cited[0]}`) and link the pair instead (`flip belief about "
                f"{cited[0]} {page.id or '<C#>'}`); if the measurement is what the "
                "claim rests on, cite the survey it rests on",
                _rel(page, root),
            )
        )
    if not belief_pages:
        return

    claim_names = {p.id for p in claim_pages if p.id}
    forecast_names = {
        p.id for p in by_dir.get("forecasts", []) if p.id and p.fm.get("type") == "Forecast"
    }
    source_fms = [p.fm for p in source_pages]
    # Every `belief:` edge a forecast declares — a bet on prevalence is a bet
    # about believers, and it counts as something that would move the belief.
    borne_on = {
        str(entry).partition(":")[2]
        for p in by_dir.get("forecasts", [])
        for entry in pages.as_list(p.fm.get("bears_on"))
        if str(entry).startswith("belief:")
    }

    for page in belief_pages:
        bid = page.id or "?"
        rel = _rel(page, root)
        fm = page.fm
        kind = fm.get("belief_kind")
        if kind is not None and kind not in beliefs_mod.BELIEF_KINDS:
            findings.append(
                _error(
                    "bad-enum",
                    f"belief {bid}: belief_kind '{kind}' invalid "
                    f"(one of: {', '.join(beliefs_mod.BELIEF_KINDS)})",
                    rel,
                )
            )
        stance = fm.get("stance")
        if stance is not None and stance not in beliefs_mod.STANCES:
            findings.append(
                _error(
                    "bad-enum",
                    f"belief {bid}: stance '{stance}' invalid "
                    f"(one of: {', '.join(beliefs_mod.STANCES)})",
                    rel,
                )
            )
        status = fm.get("status")
        if status is not None and status not in beliefs_mod.STATUSES:
            findings.append(
                _error(
                    "bad-enum",
                    f"belief {bid}: status '{status}' invalid (one of: "
                    f"{', '.join(beliefs_mod.STATUSES)}) — a belief's status is "
                    "custody of the record of WHO BELIEVES WHAT; verdicts on the "
                    "proposition ('verified', 'false-positive', 'superseded') live "
                    "on Claim pages, and the notebook's own relation to the "
                    "proposition is `stance`",
                    rel,
                )
            )
        for key, why in _BELIEF_FORBIDDEN.items():
            if key in fm:
                findings.append(
                    _error(
                        "belief-two-object",
                        f"belief {bid} carries '{key}' — {why} (the two-object rule "
                        "extended to beliefs, SPEC §7.1). A belief is a claim about "
                        "believers; nothing on its page weighs the proposition. "
                        "Remove the key, and put the proposition in claims/ if it "
                        f"needs judging (`flip claim add …`, then `flip belief about "
                        f"{bid} <C#>`)",
                        rel,
                    )
                )
        if kind == "attributed" and not str(fm.get("function") or "").strip():
            findings.append(
                _warn(
                    "unfunctioned-belief",
                    f"attributed belief {bid} names no `function` — what it explains, "
                    "protects, or licenses for the holder. Prevalence sizes the room; "
                    "function is the field an intervention is built from, and the "
                    "assumption that a wrong belief is an information shortfall "
                    "curable by supplying facts is the one that reliably fails on "
                    "identity-loaded topics. Add it to the page's frontmatter",
                    rel,
                )
            )
        if kind == "working" and not str(fm.get("falsified_by") or "").strip():
            findings.append(
                _warn(
                    "unfalsifiable-belief",
                    f"working belief {bid} names no `falsified_by` — what would make "
                    "this notebook drop it. Holding a hypothesis here costs nothing "
                    "(it corroborates nothing and gates nothing), which is exactly "
                    "why the falsifier is the price of admission: without one the "
                    "page is a commitment wearing a hypothesis's clothes (SPEC §13)",
                    rel,
                )
            )
        about = str(fm.get("about") or "")
        if about:
            if about in held or about in forecast_names:
                findings.append(
                    _error(
                        "impure-about",
                        f"belief {bid}: about '{about}' points at a "
                        f"{'belief' if about in held else 'forecast'}, not a Claim — "
                        "`about` names the record that states this proposition as a "
                        "fact about the WORLD, and only a Claim gets sources and a "
                        "verification bar (class purity, SPEC §7). Write the claim "
                        "and point here",
                        rel,
                    )
                )
            elif about not in claim_names:
                findings.append(
                    _warn(
                        "dangling-about",
                        f"belief {bid}: about '{about}' resolves to no claims/ page; "
                        "add the claim (`flip claim add`) or clear the link "
                        f"(`flip belief about {bid} --clear`)",
                        rel,
                    )
                )
        # The measurement is the only thing on this page evidence bears on, and
        # it is graded exactly like a claim's: judged, independent, deduped.
        measurements = [
            m for m in pages.as_list(fm.get("measurements")) if isinstance(m, dict)
        ]
        if measurements:
            recomputed = beliefs_mod.measurement_corroboration(source_fms, fm)
            stored = fm.get("measurement_corroboration")
            if stored is not None and stored != recomputed:
                findings.append(
                    _warn(
                        "measurement-drift",
                        f"belief {bid}: stored measurement_corroboration {stored} != "
                        f"recomputed {recomputed}; it is computed from the "
                        "measurements' sources, never hand-set — re-record the "
                        f"measurement (`flip belief measure {bid} …`) to refresh it",
                        rel,
                    )
                )
            uncountable = beliefs_mod.uncountable_measurement_sources(source_fms, fm)
            by_source = {str(s.get("id")): s for s in source_fms}
            cited = [
                sid
                for sid in beliefs_mod.measurement_source_ids(fm)
                if sid in by_source
            ]
            unjudged = [
                sid
                for sid in cited
                if not sources_mod.judged(by_source[sid])
                and not sources_mod.unmigrated(by_source[sid])
            ]
            dependent = [
                f"{sid} ({by_source[sid].get('independence')})"
                for sid in cited
                if sources_mod.judged(by_source[sid])
                and by_source[sid].get("independence") != "independent"
            ]
            if recomputed == 0 and cited:
                # Never let a zero stand alone. Zero for "nobody has judged
                # these yet" and zero for "the population is the only witness to
                # its own beliefs" are different situations with different
                # fixes, and the second one is often the honest ceiling.
                msg = (
                    f"belief {bid} records {len(measurements)} measurement(s) that no "
                    "judged, independent source supports — a prevalence number is a "
                    "measurement like any other, and the bar it clears is the claim "
                    "bar (SPEC §5.4). This is a statement about the measurement, "
                    "never about the proposition"
                )
                if unjudged:
                    msg += (
                        f". {', '.join(unjudged)} unjudged, and unjudged sources never "
                        "corroborate — judge them with `flip grade`"
                    )
                if dependent:
                    msg += (
                        f". {', '.join(dependent)} recorded as not independent, which "
                        "for a belief is frequently the honest ceiling: a population "
                        "reporting its own beliefs is primary evidence that it holds "
                        "them and self-reported evidence about everything else. Add an "
                        "independent instrument if one exists, or leave the count at 0 "
                        "knowing what it means"
                    )
                if uncountable:
                    msg += (
                        f". {', '.join(uncountable)} "
                        f"{'carries' if len(uncountable) == 1 else 'carry'} pre-0.8 "
                        "independence vocabulary and could not be counted either way, "
                        "so that count understates the evidence rather than measuring "
                        "it — run `flip migrate`, then re-judge"
                    )
                findings.append(_warn("unmeasured-prevalence", msg, rel))
        if (
            kind == "working"
            and str(fm.get("status", "active")) == "active"
            and str(fm.get("stance", "unexamined")) == "unexamined"
            and not about
            and bid not in borne_on
        ):
            since = str(fm.get("first_recorded") or "an unrecorded date")
            findings.append(
                _warn(
                    "untested-belief",
                    f"working belief {bid} has been held since {since} with stance "
                    "'unexamined', and nothing in this notebook would ever move it — "
                    "no claim it is `about`, no forecast bearing on it. That is a "
                    "legal state and it is the point of the class; it is also the "
                    "state a live hypothesis quietly dies in. Name the test: write "
                    f"the claim the proposition would become (`flip claim add`, then "
                    f"`flip belief about {bid} <C#>`), or open a dated bet "
                    f"(`flip forecast add … --bears-on belief:{bid}`)",
                    rel,
                )
            )


# --- transcripts: pinned passages (SPEC §8) --------------------------------------


def _check_transcripts(
    root: Path,
    source_pages: list[pages.Page],
    claim_pages: list[pages.Page],
    findings: list[Finding],
) -> None:
    """Excerpt integrity on transcript sources (SPEC §8).

    Three ways a pinned passage stops meaning what it said:

    `unbacked-excerpt` — the transcript's raw capture is gone, so no pin on it
    can be checked at all (ERROR: custody is the whole basis of the quote).
    `excerpt-drift` — the quote stored on the page no longer hashes to the
    recorded sha256, which on an immutable capture means the page was
    hand-edited (ERROR: a quotation flip vouches for must be one it can check).
    `dangling-excerpt` — a claim cites `T1§label` that the transcript does not
    pin (WARN, consistent with the dangling-citation policy). The citation
    still resolves to the source, which is the danger: it reads as one exchange
    and rests on the whole conversation.
    """
    from .claims import source_refs

    transcript_pages = [
        p for p in source_pages if str(p.fm.get("medium") or "") == "conversation"
    ]
    pinned: dict[str, set[str]] = {}
    for page in transcript_pages:
        records = [e for e in pages.as_list(page.fm.get("excerpts")) if isinstance(e, dict)]
        pinned[page.id] = {str(e.get("label")) for e in records}
        if not records:
            continue
        local = str(page.fm.get("local") or "")
        raw = root / local if local else None
        if not local or raw is None or not raw.is_file():
            findings.append(
                _error(
                    "unbacked-excerpt",
                    f"{page.id} pins {len(records)} passage(s) but its capture "
                    f"({local or 'no `local` recorded'}) is missing; the quotes on this "
                    "page cannot be checked against anything — restore custody or unpin",
                    _rel(page, root),
                )
            )
            continue
        lines = raw.read_text(encoding="utf-8", errors="replace").splitlines()
        for record in records:
            span = pages.as_list(record.get("lines"))
            if len(span) != 2:
                continue
            start, end = int(span[0]), int(span[1])
            quoted = "\n".join(lines[start - 1 : end])
            actual = hashlib.sha256(quoted.encode("utf-8")).hexdigest()
            if actual != str(record.get("sha256")):
                findings.append(
                    _error(
                        "excerpt-drift",
                        f"{page.id}§{record.get('label')} no longer hashes to its recorded "
                        "sha256; raw captures are immutable, so the excerpt record was "
                        "hand-edited — re-pin it rather than editing the quote",
                        _rel(page, root),
                    )
                )
    for page in claim_pages:
        for ref in source_refs(page.fm):
            base, label = split_ref(ref)
            if label and label not in pinned.get(base, set()):
                findings.append(
                    _warn(
                        "dangling-excerpt",
                        f"cites {ref} but {base} pins no passage '{label}'; the citation "
                        f"falls back to the whole of {base} while reading as one exchange "
                        f"— pin it with `flip transcript excerpt {base} --label {label} …`",
                        _rel(page, root),
                    )
                )


# --- forecasts & clusters (SPEC §7) ---------------------------------------------


def _ids_and_slugs(found: list[pages.Page]) -> set[str]:
    """Every name a page answers to: its compact id and its filename slug.
    bears_on/proxy refs may use either (the pilot convention writes slugs)."""
    out: set[str] = set()
    for page in found:
        if page.id:
            out.add(page.id)
        out.add(page.slug)
    return out


def _check_forecasts(
    root: Path, by_dir: dict[str, list[pages.Page]], findings: list[Finding]
) -> None:
    """Forecast/Cluster checks (SPEC §7): enums, the two-object gate from the
    forecast side (grade/support/independence never belong on a bet), the
    no-undated-forecasts and mandatory-annul_if rules on open forecasts,
    overdue open forecasts (WARN — resolve or void), dangling typed bears_on
    refs (WARN, consistent with the dangling-citation policy), and cluster
    class purity: probability null by construction, proxies resolving to
    Forecasts, inference_link resolving to a Claim, never a Forecast."""
    fdir = by_dir.get("forecasts", [])
    forecast_pages = [p for p in fdir if p.fm.get("type") == "Forecast"]
    cluster_pages = [p for p in fdir if p.fm.get("type") == "Cluster"]
    if not forecast_pages and not cluster_pages:
        return
    claim_names = _ids_and_slugs(
        [p for p in by_dir.get("claims", []) if p.fm.get("type") == "Claim"]
    )
    question_names = _ids_and_slugs(
        [p for p in by_dir.get("questions", []) if p.fm.get("type") == "Question"]
    )
    cluster_names = _ids_and_slugs(cluster_pages)
    forecast_names = _ids_and_slugs(forecast_pages)
    belief_names = _ids_and_slugs(
        [p for p in by_dir.get("beliefs", []) if p.fm.get("type") == "Belief"]
    )
    target_names = {
        "claim": claim_names, "cluster": cluster_names, "question": question_names,
        "belief": belief_names,
    }
    today = datetime.now(timezone.utc).date().isoformat()

    for page in forecast_pages:
        fid = page.id or "?"
        rel = _rel(page, root)
        status = str(page.fm.get("status", "open"))
        if page.fm.get("status") is not None and status not in FORECAST_STATUSES:
            findings.append(
                _error(
                    "bad-enum",
                    f"forecast {fid}: status '{status}' invalid "
                    f"(one of: {', '.join(FORECAST_STATUSES)})",
                    rel,
                )
            )
        predictability = page.fm.get("predictability")
        if predictability is not None and predictability not in PREDICTABILITY:
            findings.append(
                _error(
                    "bad-enum",
                    f"forecast {fid}: predictability '{predictability}' invalid "
                    f"(one of: {', '.join(PREDICTABILITY)})",
                    rel,
                )
            )
        # The two-object gate, forecast side (SPEC §7): grades and support
        # tuples belong to verified records, never to bets.
        for key in ("grade", "support", "independence"):
            if key in page.fm:
                findings.append(
                    _error(
                        "two-object",
                        f"forecast {fid} carries '{key}' — grades and support tuples "
                        "live on Source/Claim pages, never Forecasts (the two-object "
                        "rule, SPEC §7); a forecast earns trust through resolution — "
                        "remove the key",
                        rel,
                    )
                )
        resolves_by = str(page.fm.get("resolves_by") or "")
        if status == "open":
            if not resolves_by:
                findings.append(
                    _error(
                        "undated-forecast",
                        f"open forecast {fid} has no resolves_by — no undated "
                        "forecasts (SPEC §7): an undated bet can never be scored; "
                        "add the resolution date or void the forecast",
                        rel,
                    )
                )
            if not str(page.fm.get("annul_if") or "").strip():
                findings.append(
                    _error(
                        "missing-annul-if",
                        f"open forecast {fid} has no annul_if — annulment conditions "
                        "are mandatory (SPEC §7); state when the question stops "
                        "being askable",
                        rel,
                    )
                )
            if resolves_by and resolves_by < today:
                findings.append(
                    _warn(
                        "overdue-forecast",
                        f"forecast {fid} was due {resolves_by} and is still open — "
                        f"overdue — resolve or void (`flip forecast resolve {fid} "
                        "yes|no|void`)",
                        rel,
                    )
                )
        for entry in pages.as_list(page.fm.get("bears_on")):
            entry = str(entry)
            m = BEARS_ON_RE.match(entry)
            if not m:
                findings.append(
                    _error(
                        "untyped-ref",
                        f"forecast {fid}: bears_on entry '{entry}' is not a typed ref "
                        "(claim:<ref>, cluster:<ref>, question:<ref>, belief:<ref>) — every "
                        "cross-class edge names its class (SPEC §7)",
                        rel,
                    )
                )
                continue
            kind, _, target = entry.partition(":")
            if target not in target_names.get(kind, set()):
                findings.append(
                    _warn(
                        "dangling-bears-on",
                        f"forecast {fid}: bears_on '{entry}' resolves to no existing "
                        f"{kind} page; add the {kind} or fix the ref (dangling refs "
                        "are legal but counted, like dangling citations)",
                        rel,
                    )
                )

    for page in cluster_pages:
        cid = page.id or "?"
        rel = _rel(page, root)
        if page.fm.get("probability") is not None:
            findings.append(
                _error(
                    "scored-cluster",
                    f"cluster {cid} carries probability {page.fm.get('probability')} — "
                    "a decision question carries no probability, by construction "
                    "(SPEC §7); the numbers live on its proxy forecasts — set "
                    "probability: null",
                    rel,
                )
            )
        for proxy in pages.as_list(page.fm.get("proxies")):
            if str(proxy) not in forecast_names:
                findings.append(
                    _warn(
                        "dangling-proxy",
                        f"cluster {cid}: proxy '{proxy}' resolves to no forecasts/ "
                        "Forecast page; add the forecast or fix the ref",
                        rel,
                    )
                )
        link = page.fm.get("inference_link")
        if link is not None:
            link = str(link)
            if link in forecast_names or link in cluster_names:
                findings.append(
                    _error(
                        "impure-inference-link",
                        f"cluster {cid}: inference_link '{link}' points at a "
                        "forecasts/ page — the link is a piece of reasoning and "
                        "must be a Claim (graded, never scored; class purity, "
                        "SPEC §7); move the reasoning to claims/ and point there",
                        rel,
                    )
                )
            elif link not in claim_names:
                findings.append(
                    _warn(
                        "dangling-inference-link",
                        f"cluster {cid}: inference_link '{link}' resolves to no "
                        "claims/ page; add the link claim (`flip claim add`) or "
                        "fix the ref",
                        rel,
                    )
                )


# --- kind contract (design-outcome-kinds.md, Phase 1) ---------------------------


def _check_kind_contract(root: Path, manifest: Manifest | None, findings: list[Finding]) -> None:
    """Unmet contract requirements of the notebook's adopted kind (SPEC/design
    outcome-kinds.md): WARN while active/dormant (a gap not yet due — same
    gating as profile minimums), ERROR once done/published/archived. A kind
    that resolves with no contract (including every profile-adapter kind:
    scout, ledger, …) is a no-op — nothing to gap-check."""
    if manifest is None:
        return
    from . import kinds  # local: kinds imports profiles/manifest/registry, no cycle risk here

    try:
        kind = kinds.load_kind(manifest.kind, root)
    except (SystemExit, Exception):
        return  # unresolvable kind id is already reported by _check_profile
    if not kind.contract:
        return
    closed = manifest.status in CLOSED_STATUSES
    for row in kinds.gap_manifest(root, kind):
        if row.tier == "met":
            continue
        msg = (
            f"kind '{kind.id}' requirement '{row.requirement_id}' unmet "
            f"({row.have}/{row.min}): {row.what} — assembled by {row.assembled_by} "
            f"[{row.tier}]"
        )
        findings.append(
            _error("kind-gap", msg, ROOT_FILE)
            if closed
            else _warn("kind-gap", msg, ROOT_FILE, expected=True)
        )


# --- disciplines & slot composition (design-composition-0.14.md) ----------------


def _slot_norm(slot_id: str) -> str:
    """Slot names normalized for the near-miss advisory: case and punctuation
    stripped, so `sourcing.tier` / `sourcing-tier` / `SourcingTier` collide."""
    return re.sub(r"[^a-z0-9]", "", slot_id.lower())


def _dependency_met(dep: str, resolved: list) -> bool:
    from . import disciplines as disc_mod

    parsed = disc_mod.parse_pin(dep)
    if parsed is None:  # a bare id: met when any resolved discipline carries it
        return any(d.id == str(dep) for d in resolved)
    dep_id, major, minor = parsed
    return any(
        d.id == dep_id and disc_mod.pick_version([d.version], major, minor) is not None
        for d in resolved
    )


def _check_disciplines(root: Path, manifest: Manifest | None, findings: list[Finding]) -> None:
    """Composition checks (design-composition-0.14.md): pin resolution, slot
    ownership (one owner per slot; the manifest resolves declared conflicts),
    graceful dependencies, the slot near-miss advisory, field-predicate gates
    and checks, kind slot requirements, and owner labeling.

    Dormancy (the anti-J2EE rule): a manifest with no `disciplines:` key is
    implicitly lineage (+forecasting iff forecasts/ exists) — pure
    self-description. In that mode this function adds NO findings and NO
    labels: doctor output stays byte-identical to an undeclared notebook.
    The machinery wakes only when someone declares.
    """
    if manifest is None:
        return
    from . import disciplines as disc_mod

    declared_pins, declared = disc_mod.effective_pins(root, manifest.disciplines)
    if not declared:
        return

    resolved: list[disc_mod.Discipline] = []
    for pin in declared_pins:
        d, reason = disc_mod.resolve_pin(pin, root)
        if d is None:
            findings.append(_error("unknown-discipline", reason, ROOT_FILE))
            continue
        parsed_pin = disc_mod.parse_pin(pin)
        version = disc_mod.parse_version(d.version)
        if (
            parsed_pin is not None and parsed_pin[2] is not None
            and version is not None and version > (parsed_pin[1], parsed_pin[2])
        ):
            findings.append(
                _warn(
                    "discipline-moved",
                    f"pin '{pin}' is exact but {d.id}@{d.version} is available — "
                    "the standard moved; review the newer minor and re-pin",
                    ROOT_FILE,
                )
            )
        for problem in disc_mod.validate_discipline(d):
            findings.append(
                _error("bad-discipline", f"discipline '{d.id}': {problem}", ROOT_FILE)
            )
        resolved.append(d)

    declared_ids = {d.id for d in resolved}

    # (b) Slot ownership: one owning discipline per slot per notebook; genuine
    # collisions are resolved explicitly in [discipline_resolve], never merged.
    owners_by_slot: dict[str, list] = {}
    for d in resolved:
        for slot in d.slots:
            if slot.owns:
                owners_by_slot.setdefault(slot.id, []).append(d)
    resolve_table = {str(k): str(v) for k, v in (manifest.discipline_resolve or {}).items()}
    for slot_id, chosen in sorted(resolve_table.items()):
        if chosen not in declared_ids:
            findings.append(
                _error(
                    "unresolved-slot",
                    f"discipline_resolve names '{chosen}' for slot '{slot_id}' but "
                    "that discipline is not declared; declare it in `disciplines:` "
                    "or fix the resolution",
                    ROOT_FILE,
                )
            )
    slot_owner: dict[str, str] = {}
    for slot_id, ds in sorted(owners_by_slot.items()):
        if len(ds) == 1:
            slot_owner[slot_id] = ds[0].id
            continue
        names = ", ".join(sorted(d.id for d in ds))
        chosen = resolve_table.get(slot_id)
        if not chosen:
            findings.append(
                _error(
                    "unresolved-slot",
                    f"disciplines {names} both own slot '{slot_id}' with no "
                    f"[discipline_resolve] entry; add `discipline_resolve: "
                    f"{{{slot_id}: <one of: {names}>}}` to the manifest — "
                    "collisions are resolved explicitly, never silently merged",
                    ROOT_FILE,
                )
            )
        elif chosen not in {d.id for d in ds}:
            if chosen in declared_ids:  # declared, but not an owner of this slot
                findings.append(
                    _error(
                        "unresolved-slot",
                        f"discipline_resolve names '{chosen}' for slot '{slot_id}' "
                        f"but the disciplines owning it are {names}; pick one of those",
                        ROOT_FILE,
                    )
                )
        else:
            slot_owner[slot_id] = chosen

    # (c) depends_on: the graceful fourth relation — absent partner is a WARN,
    # never a conflict.
    for d in resolved:
        for dep in d.depends_on:
            if not _dependency_met(dep, resolved):
                findings.append(
                    _warn(
                        "discipline-dependency",
                        f"discipline '{d.id}' depends on '{dep}', which is not "
                        "declared; composition degrades gracefully — declare it "
                        "to restore the partnership",
                        ROOT_FILE,
                    )
                )

    # (d) Slot near-miss advisory: two declared disciplines whose slot names
    # differ only by case/punctuation silently never collide — the likeliest
    # silent-miss shape under open slot strings (decision C-B).
    slot_names: dict[str, dict[str, set[str]]] = {}  # norm -> raw -> discipline ids
    for d in resolved:
        for slot in d.slots:
            slot_names.setdefault(_slot_norm(slot.id), {}).setdefault(slot.id, set()).add(d.id)
    for norm in sorted(slot_names):
        raws = slot_names[norm]
        if len(raws) < 2:
            continue
        listed = "; ".join(
            f"'{raw}' ({', '.join(sorted(raws[raw]))})" for raw in sorted(raws)
        )
        findings.append(
            _warn(
                "slot-name-mismatch",
                f"slot names differing only by case/punctuation never collide — "
                f"probably the same policy area: {listed}; align on one spelling",
                ROOT_FILE,
            )
        )

    # (f) Field-predicate gates and checks (decision C-C, Form B), evaluated
    # over the class's pages. Owner enforced gate -> ERROR; non-owner ->
    # labeled advisory WARN; attested -> never errors, WARN-expected label
    # only when the check fails (decision C-D: parse + reserve + label).
    for d in resolved:
        for gate in d.gates:
            if not isinstance(gate.check, dict):
                continue
            message = str(gate.check.get("message") or "").strip()
            code = gate.id or "discipline-gate"
            owns = slot_owner.get(gate.slot) == d.id
            for rel, detail in disc_mod.evaluate_predicate(root, gate.check):
                body = f"{detail} — {message}" if message else detail
                if gate.kind == "attested":
                    findings.append(
                        _warn(
                            code,
                            f"attested ({d.id}): recorded, not enforced — {body}",
                            rel,
                            expected=True,
                        )
                    )
                elif owns:
                    findings.append(_error(code, f"{body} ({d.id})", rel))
                else:
                    findings.append(_warn(code, f"advisory ({d.id}): {body}", rel))
        for entry in d.checks:
            if "check" in entry or "class" not in entry:
                continue  # Form A codes run as doctor's own checks; labeled below
            message = str(entry.get("message") or "").strip()
            code = str(entry.get("id") or "discipline-check")
            for rel, detail in disc_mod.evaluate_predicate(root, entry):
                body = f"{detail} — {message}" if message else detail
                findings.append(_warn(code, f"advisory ({d.id}): {body}", rel))

    # Kind slot requirements (ship item 4): a kind's `requires` engages only
    # when the notebook declares disciplines; otherwise it stays informational.
    from . import kinds as kinds_mod

    try:
        kind = kinds_mod.load_kind(manifest.kind, root)
    except (SystemExit, Exception):
        kind = None
    if kind is not None:
        for req in kind.requires:
            slot_id = str(req.get("slot") or "")
            default = str(req.get("default") or "")
            if not slot_id or slot_id in owners_by_slot:
                continue
            fix = (
                f"declare '{default}' (the kind's default) in the manifest "
                "`disciplines:` list, or another discipline owning it"
                if default
                else "declare a discipline owning it in the manifest `disciplines:` list"
            )
            findings.append(
                _error(
                    "slot-unfilled",
                    f"kind '{kind.id}' requires slot '{slot_id}' but no declared "
                    f"discipline owns it; {fix}",
                    ROOT_FILE,
                )
            )

    # (e) Owner labeling, post-processed after all checks: a finding whose
    # code is claimed (gate or check) by exactly one resolved discipline gets
    # the owner label appended — "the identity of the standard travels with
    # the finding". Codes claimed by several disciplines stay unlabeled.
    claimed: dict[str, set[str]] = {}
    for d in resolved:
        for code in d.claimed_codes():
            claimed.setdefault(code, set()).add(d.id)
    for f in findings:
        owners = claimed.get(f.code)
        if owners and len(owners) == 1:
            owner = next(iter(owners))
            if f"({owner})" not in f.message:
                f.message = f"{f.message} ({owner})"
