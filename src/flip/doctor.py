"""flip doctor — lint a notebook against the spec and its profile (SPEC §15).

Every check is independent and tolerant: a missing optional file is simply
skipped unless the profile requires it, and one broken file never stops the
other checks from running. `run_doctor` only reports; exiting non-zero on
ERROR findings is the CLI's job.

v0.4 check surface: OKF conformance (every entity/concept page parses and
carries a type; reserved index.md/log.md files stay frontmatter-free),
id integrity (prefix routing, aliases, duplicates), link rot (dangling
relative citations — legal in OKF, counted here), corroboration drift and
under-verified claims (recomputed via claims.claim_corroboration; ungraded
sources never count, and a claim citing only what it is ABOUT is measured
against the attribution test that replaces the bar there — SPEC §7), stale
freshness, orphan custody (pages ↔ raw bytes ↔
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
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import integrations, pages, stance, util, workspace
from . import sources as sources_mod
from .beat import find_beat_root, load_beat
from .claims import STATUSES as CLAIM_STATUSES  # claim status enum (SPEC §7)
from .commissions import STATUSES as COMMISSION_STATUSES  # lifecycle enum (SPEC §7.4)
from .ledgers import CLOSED_REASONS, QUESTION_STATUSES  # question journey (SPEC §7)
from .claims import (
    CITATION_ROLES,
    claim_corroboration,
    derivation_ids,
    evidence_ids,
    has_gating_verification,
    unsupported_reason,
    subject_ids,
    unaudited_subjects,
    uncountable_sources,
)
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
    append_jsonl,
    detect_actor,
    find_workspace_root,
    is_notebook_root,
    new_uid,
    read_jsonl,
    require_notebook_root,
    sha256_file,
    split_ref,
    utc_now,
)

PROVENANCE = "sources/_provenance.jsonl"
DERIVATIONS = sources_mod.DERIVATIONS.as_posix()
# Every JSONL ledger the format defines; each must at least parse.
LEDGERS = (PROVENANCE, DERIVATIONS, "log/log.jsonl", "log/passed.jsonl")

# Entity directories whose pages must carry a compact id; sessions are entity
# pages too but have no id scheme (SPEC §8), so they are exempt here.
_ID_DIRS = ("references", "claims", "decisions", "questions", "forecasts",
            "commissions")
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

# notebook.md is prose synthesis; ledgered entities are cited by id and never
# re-listed (SPEC §3). Above this, some section is almost certainly mirroring a
# ledger — the measured outlier ran 63.5KB, its "Decisions" section duplicating
# 25 decision pages line by line.
NOTEBOOK_MD_CAP = 24 * 1024

# binary-in-envelope reads only this much of each sources/raw/**/*.json — the
# offending files are the multi-MB ones (627 MB of PDF bytes sat in JSON
# strings across one measured corpus), and json-parsing them on every doctor
# run is exactly the cost this check must not incur. In the raw text, a stuffed
# document is a payload field opening with a binary magic, either verbatim
# ("%PDF") or \u-escaped ("PK", what json.dumps makes of control
# bytes); a rescued field opens with flip's own breadcrumb and matches neither.
_ENVELOPE_HEAD_BYTES = 64 * 1024
_BINARY_PAYLOAD_RE = re.compile(
    '"(?P<field>' + "|".join(integrations._PAYLOAD_FIELDS) + ')"\\s*:\\s*"(?:'
    + "|".join(
        sorted(
            {re.escape(m) for m in integrations._PAYLOAD_MAGIC}
            | {re.escape(json.dumps(m)[1:-1]) for m in integrations._PAYLOAD_MAGIC}
        )
    )
    + ")"
)

# Custody tracked as plain git objects above this many bytes gets named: every
# capture lands in history forever, and the measured failure was a 931 MB .git
# grown from committed sources/raw/. Below it, the repo can absorb the habit.
_CUSTODY_TRACKED_CAP = 50 * 1024 * 1024

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
    "unreported-method", "capture-method-drift",
    "binary-in-envelope", "duplicate-custody",
    "truncated-title", "machine-title", "ungraded-cited",
    # scale hardening (0.19): what a 1.66 GB, 682-source corpus taught
    "notebook-md-bloat", "next-steps-bloat", "custody-in-git", "workspace-nudge",
    # sources: text derivatives (SPEC §5.5)
    "thin-derivative", "missing-derivative", "unlogged-derivative",
    "unvocabularied-extraction",
    # claims
    "two-object", "pre-okf02-layout", "corroboration-drift", "under-verified",
    "unaudited-claim", "provenance-open", "unlocatable-recomputation",
    "world-absence", "inherited-unsupported", "dangling-derivation",
    "unscoped-absence",
    # questions: the journey vocabulary
    "undated-dormant",
    # stance & exposure (SPEC §7.1)
    "unpriced-stance", "unsourced-holder", "stored-exposure",
    "misattributed-citation", "unexamined-position",
    "losing-to-a-rival", "no-declared-rival",
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
    _check_titles(root, source_pages, findings)
    _check_freshness(root, source_pages, profile, findings)
    _check_raw(root, provenance, findings)
    _check_envelopes(root, findings)
    _check_duplicate_custody(provenance, findings)
    _check_custody_in_git(root, findings)
    _check_derivatives(root, source_pages, findings)
    claim_pages = [p for p in by_dir.get("claims", []) if p.fm.get("type") == "Claim"]
    _check_claims(root, claim_pages, source_pages, profile, findings)
    _check_ungraded_cited(root, claim_pages, source_pages, findings)
    _check_stance(root, manifest, claim_pages, findings)
    _check_transcripts(root, source_pages, claim_pages, findings)
    _check_forecasts(root, by_dir, findings)
    _check_questions(root, by_dir, findings)
    _check_commissions(root, by_dir, findings)
    _check_provenance_open(root, manifest, claim_pages, source_pages, findings)
    _check_workspace_nudge(root, findings)
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
    (SPEC §5.4): once the notebook is done/published/archived, a load-bearing
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


def fix_notebook(root: Path) -> list[str]:
    """Repair what can be repaired without judgment; return what was done.

    Only one repair so far, and it is mechanical: a document stuffed into a
    capture envelope's string field is written out as its own file and the
    field is replaced with a breadcrumb (the same act `run_capture` now
    performs at capture time, so old and new captures end up in the same
    shape). Every rescued file gets its own provenance row — the repair is a
    custody event and the ledger is where custody events go — and the source
    page's `local` follows if the document is now its largest real artifact.

    A field whose bytes cannot round-trip (a lossy decode upstream) is LEFT
    ALONE: the recoverable thing is gone, and overwriting the evidence of that
    with a breadcrumb would destroy the only remaining record of what
    happened. Nothing here judges, renames, or deletes.
    """
    root = require_notebook_root(root)
    raw = root / "sources" / "raw"
    if not raw.is_dir():
        return []
    done: list[str] = []
    for source_dir in sorted(p for p in raw.iterdir() if p.is_dir()):
        before = {p for p in source_dir.rglob("*") if p.is_file()}
        rescued = integrations.materialize_binary_payloads(sorted(before), source_dir)
        new = [p for p in rescued if p not in before]
        if not new:
            continue
        sid = source_dir.name
        for path in sorted(new):
            rel = path.relative_to(root).as_posix()
            append_jsonl(
                root / "sources" / "_provenance.jsonl",
                {
                    "ts": utc_now(),
                    "source_id": sid,
                    "local_path": rel,
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                    "tool": "builtin:doctor-fix",
                    "actor": detect_actor(),
                    "note": (
                        "re-materialized from a capture envelope field; the bytes "
                        "were already in custody, wrapped in a JSON string"
                    ),
                },
            )
            done.append(f"rescued {rel} from its envelope")
        _repoint_local(root, sid)
    if done:
        from . import views

        views.regenerate(root, changed=("references",))
    return done


def _repoint_local(root: Path, source_id: str) -> None:
    """Point a source page's `local` at the document once it exists as a file.

    The page pointed at the envelope because the envelope WAS the biggest
    artifact while it held the document inside it; after the rescue the
    document is, and `local` has to mean the same thing it means everywhere
    else — the primary artifact (SPEC §5.1).
    """
    for page in pages.iter_pages(root, "references"):
        if page.id != source_id or str(page.fm.get("type") or "") != "Source":
            continue
        capture_dir = root / "sources" / "raw" / source_id
        if not capture_dir.is_dir():
            return
        files = [p for p in capture_dir.rglob("*") if p.is_file()]
        if not files:
            return
        primary = sources_mod._primary_file(files)
        rel = primary.relative_to(root).as_posix()
        if str(page.fm.get("local") or "") != rel:
            page.fm["local"] = rel
            pages.write_page(page.path, page.fm, page.body)
        return


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
        "commissions": "Commission",
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


def _check_prose_size(root: Path, name: str, code: str, findings: list[Finding]) -> None:
    """Warn when a synthesis file has grown past the size where it is plausibly
    still synthesis (SPEC §3).

    The measured failure: a notebook.md at 63.5 KB whose `## Decisions` section
    restated 25 decision pages and whose `## Sources` section restated 301
    reference listings — an index wearing the costume of thought, charging
    every reader (agents most of all) the whole ledger's tokens on every open
    while saying nothing the ledgers didn't already hold, and drifting from
    them the moment either side changed.
    """
    path = root / name
    if not path.is_file():
        return
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size <= NOTEBOOK_MD_CAP:
        return
    findings.append(
        _warn(
            code,
            f"{name} is {size // 1024}KB (the norm is under "
            f"{NOTEBOOK_MD_CAP // 1024}KB): a synthesis file is prose, and "
            "ledgered entities are cited by id, never re-listed — a section that "
            "mirrors a ledger restates what the pages and generated views already "
            "hold, and drifts from them; cut it back to citations",
            name,
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
    _check_prose_size(root, "notebook.md", "notebook-md-bloat", findings)
    # NEXT_STEPS.md is synthesis under the same rule, and drifted the same way
    # in the wild: one measured file reached 24.7 KB of forward-looking work
    # nobody could act on in one reading.
    _check_prose_size(root, "NEXT_STEPS.md", "next-steps-bloat", findings)
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
    unvocabularied: list[tuple[str, str]] = []  # (sid, the word that isn't a method)
    unreported: list[str] = []
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
            unvocabularied.append((sid, method))
        elif fidelity == "unknown":
            # No `strategy` key at all: the fetcher made no claim about its
            # method, and add_source recorded that absence honestly rather than
            # minting a word. Distinct from unvocabularied-method — nothing here
            # drifted from the vocabulary, nothing was ever said.
            unreported.append(sid)
    # The teaching happens once, on a cause line ahead of the group — the full
    # explanation used to ride every row (494 B × 243 rows in one measured
    # notebook), and the repetition is what made the run unreadable, not the
    # finding. Per-row lines carry only the fact; `_collapse_findings` caps them.
    if unvocabularied or unreported:
        bits = []
        if unvocabularied:
            bits.append(f"{len(unvocabularied)} record a tool name where the method belongs")
        if unreported:
            bits.append(f"{len(unreported)} record no method at all")
        findings.append(
            _warn(
                "capture-method-drift",
                f"{len(unvocabularied) + len(unreported)} capture row(s) can't say how "
                f"the bytes were obtained: {'; '.join(bits)}. The method is one of: "
                f"{', '.join(sources_mod.CAPTURE_METHODS)} — the ledger already records "
                "the tool, and a method is what makes two notebooks comparable across "
                "deployments. Have each fetcher report one in its envelope; until then "
                "capture fidelity stays 'unknown'",
                PROVENANCE,
                expected=True,
            )
        )
    if unvocabularied:
        for sid, method in unvocabularied:
            findings.append(
                _warn(
                    "unvocabularied-method",
                    f"source {sid}: capture strategy '{method}' is a tool name, "
                    "not a method",
                    PROVENANCE,
                    expected=True,
                )
            )
    if unreported:
        for sid in unreported:
            findings.append(
                _warn(
                    "unreported-method",
                    f"source {sid}: no capture method on record",
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


def _check_titles(
    root: Path, source_pages: list[pages.Page], findings: list[Finding]
) -> None:
    """A source page's title is canonical frontmatter AND the seed of its slug,
    so a title that was never a title costs the page its identity permanently.

    Two shapes, both measured on one corpus: 326 of 682 reference pages carried
    a title ending in a display ellipsis (a fetcher handing back a truncated
    listing string), and eight distinct sources ended up slugged `index-3`
    through `index-10`. `_plausible_title` refuses both at capture now; these
    findings are for the pages already on disk, which are repairable but not
    self-repairing.
    """
    for page in source_pages:
        title = str(page.fm.get("title") or "").strip()
        if not title:
            continue
        rel = _rel(page, root)
        if title.endswith(("…", "...")):
            findings.append(
                _warn(
                    "truncated-title",
                    f"source {page.id or '?'}: title ends mid-word — a display "
                    "truncation was stored as the canonical title, and the slug "
                    f"was derived from it: `flip source retitle {page.id or '<id>'} "
                    '"<full title>"`',
                    rel,
                )
            )
        elif _machine_title(title):
            findings.append(
                _warn(
                    "machine-title",
                    f"source {page.id or '?'}: title {title[:40]!r} is machine "
                    "output (a bibtex/JSON fragment, or a placeholder like "
                    "'index'), not a name a reader can recognize — several such "
                    "sources collide on one meaningless slug: `flip source "
                    f'retitle {page.id or "<id>"} "<full title>"`',
                    rel,
                )
            )


def _machine_title(title: str) -> bool:
    """True for a title that is structured output rather than a name."""
    if title.strip().lower() == "index":
        return True
    if title.lstrip().startswith(("{", "@", "inproceedings", "article{")):
        return True
    return '": "' in title


def _check_envelopes(root: Path, findings: list[Finding]) -> None:
    """A capture envelope carries metadata; the document lands as its own file.

    A fetcher that decodes a document and hands the bytes back inside a JSON
    string produces a capture that is ~2.5× the size of the document (escaping)
    and a text derivative made of mojibake — one measured corpus held 627 MB of
    PDFs this way, the largest a 104 MB `capture.json` around a 41.6 MB PDF.
    Nothing about the page or its ledger row says so; the hash is honest about
    a file whose CONTENT is a wrapper.

    Reads only the head of each JSON (`_ENVELOPE_HEAD_BYTES`): the offending
    files are the multi-MB ones, and parsing those on every run is exactly the
    cost this check exists to avoid paying twice.
    """
    raw = root / "sources" / "raw"
    if not raw.is_dir():
        return
    for path in sorted(raw.rglob("*.json")):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(_ENVELOPE_HEAD_BYTES)
        except OSError:
            continue
        m = _BINARY_PAYLOAD_RE.search(head)
        if not m:
            continue
        rel = path.relative_to(root).as_posix()
        findings.append(
            _warn(
                "binary-in-envelope",
                f"{rel} holds a document's bytes in its '{m.group('field')}' "
                "field — the envelope is metadata, and a document belongs in a "
                "file of its own (as a JSON string it costs ~2.5× its size and "
                "extracts as mojibake): `flip doctor --fix` writes the payload "
                "out and leaves a breadcrumb in its place",
                rel,
            )
        )


def _check_duplicate_custody(provenance: list[dict], findings: list[Finding]) -> None:
    """The same bytes in custody under two source ids: one document, two
    identities, two grades to keep in step, and a `--stale` roster that counts
    it twice. Measured: four PDF pairs inside a single notebook.

    Envelope sidecars are excluded — every `flip.json` in a notebook plausibly
    shares a hash, and that is not this finding.
    """
    by_hash: dict[str, set[str]] = {}
    for row in provenance:
        sha = str(row.get("sha256") or "")
        sid = str(row.get("source_id") or "")
        if not sha or not sid:
            continue
        if str(row.get("status") or "") in sources_mod.UNCAPTURED_STATUSES:
            continue
        if Path(str(row.get("local_path") or "")).name == sources_mod.ENVELOPE_FILENAME:
            continue
        by_hash.setdefault(sha, set()).add(sid)
    for sha, sids in sorted(by_hash.items()):
        if len(sids) < 2:
            continue
        named = ", ".join(sorted(sids))
        findings.append(
            _warn(
                "duplicate-custody",
                f"sources {named} hold identical bytes (sha256 {sha[:12]}…): one "
                "document captured twice under two identities — cite one and "
                "supersede the other, or keep both deliberately if they are "
                "genuinely different editions that happen to match",
                PROVENANCE,
            )
        )


def _check_custody_in_git(root: Path, findings: list[Finding]) -> None:
    """Custody committed as plain git objects is a decision that cannot be
    cheaply unmade: one measured repo carried a 931 MB `.git` with a 104 MB
    blob in history, and by the time anyone notices, rewriting it is the only
    remedy. SPEC §5.6 names git-LFS as the default and the alternatives.

    Deliberately quiet unless it already matters (`_CUSTODY_TRACKED_CAP`), and
    fully tolerant of git being absent, failing, or refusing — a notebook is
    not required to live in a repository, and doctor never depends on one.
    """
    raw = root / "sources" / "raw"
    if not raw.is_dir():
        return
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-s", "--", "sources/raw"],
            cwd=root, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if proc.returncode != 0 or not proc.stdout.strip():
        return
    tracked = [
        line.split("\t", 1)[1]
        for line in proc.stdout.splitlines()
        if "\t" in line
    ]
    if not tracked:
        return
    total = 0
    for rel in tracked:
        try:
            total += (root / rel).stat().st_size
        except OSError:
            continue
    if total <= _CUSTODY_TRACKED_CAP:
        return
    if _lfs_tracked(root):
        return
    findings.append(
        _warn(
            "custody-in-git",
            f"{len(tracked)} custody file(s) totalling {total // (1024 * 1024)}MB are "
            "tracked as plain git objects, so every capture is in history forever "
            "(a measured corpus reached a 931MB .git this way). flip's default is "
            "git-LFS for `sources/raw/`; gitignoring it and committing the "
            "provenance ledger keeps custody local with integrity still provable "
            "(SPEC §5.6). History cannot be cheaply unwritten — decide now",
            "sources/raw",
        )
    )


def _lfs_tracked(root: Path) -> bool:
    """True when a .gitattributes at or above the notebook puts custody through
    the LFS filter — the default stance being followed, so nothing to say."""
    for directory in [root, *root.parents]:
        path = directory / ".gitattributes"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if "filter=lfs" in line and ("sources/raw" in line or line.strip().startswith("*")):
                return True
        if (directory / ".git").exists():
            break
    return False


def _check_ungraded_cited(
    root: Path,
    claim_pages: list[pages.Page],
    source_pages: list[pages.Page],
    findings: list[Finding],
) -> None:
    """A source at grade '?' cited as EVIDENCE corroborates nothing (SPEC §5.4)
    — it is in custody, and nobody has judged it yet. The claim reads as
    supported on the page and is not, which is the quiet version of the failure
    the whole grading lane exists to make loud. 62 such sources sat uncounted in
    one measured corpus, none of them mentioned by doctor.

    Subject citations (`--about`) are exempt: a source you are writing ABOUT
    owes an attribution test, not a grade.
    """
    ungraded = {
        p.id: p
        for p in source_pages
        if p.id and str(p.fm.get("grade") or "?") == "?"
    }
    if not ungraded:
        return
    citing: dict[str, set[str]] = {}
    for page in claim_pages:
        for sid in evidence_ids(page.fm):
            if str(sid) in ungraded:
                citing.setdefault(str(sid), set()).add(page.id or "?")
    for sid, claim_ids in sorted(citing.items()):
        findings.append(
            _warn(
                "ungraded-cited",
                f"source {sid} is cited as evidence by {', '.join(sorted(claim_ids))} "
                "but carries no grade, so it corroborates nothing — judge it: "
                f"`flip grade {sid} --independence … --basis …` "
                f"(`flip grade {sid} --explain` shows what moves the letter)",
                _rel(ungraded[sid], root),
            )
        )


def _check_workspace_nudge(root: Path, findings: list[Finding]) -> None:
    """Sibling notebooks in one repo with no workspace binding: every id space
    overlaps invisibly (`A3` names a different document in each), and the
    checks that would catch it — ambiguous ids, slug collisions, duplicate uids
    — only run at the workspace layer. Seven notebooks sat this way in one
    measured repo, `flip doctor --workspace` refusing on all of them.

    An expected-until-use notice: nothing is wrong until you follow a
    cross-notebook reference.
    """
    if find_workspace_root(root) is not None:
        return
    parent = root.parent
    if parent == root:
        return
    siblings = []
    try:
        candidates = sorted(p for p in parent.iterdir() if p.is_dir())
    except OSError:
        return
    for candidate in candidates:
        if candidate.resolve() == root.resolve():
            continue
        if is_notebook_root(candidate):
            siblings.append(candidate.name)
    if not siblings:
        return
    shown = ", ".join(siblings[:3]) + (f" and {len(siblings) - 3} more" if len(siblings) > 3 else "")
    findings.append(
        _warn(
            "workspace-nudge",
            f"{len(siblings)} sibling notebook(s) share this directory ({shown}) with "
            "no workspace binding, so their id spaces overlap unchecked — `flip ws "
            "init` here binds them under handles, makes `handle:id` refs resolvable, "
            "and lets `flip doctor --workspace` see ambiguous ids and slug collisions",
            ROOT_FILE,
            expected=True,
        )
    )


def _check_derivatives(
    root: Path, source_pages: list[pages.Page], findings: list[Finding]
) -> None:
    """The text-derivative lane (SPEC §5.5): four ways `sources/text/` and
    `derived/_derivations.jsonl` can stop meaning what they say.

    `thin-derivative`          — a .txt on disk with too few words to be the
                                 document's text, which looks exactly like a
                                 real one until someone opens it.
    `unvocabularied-extraction`— a derivation that doesn't say HOW, so a
                                 quotation drawn from it can't say whether it
                                 came from a text layer or from OCR.
    `unlogged-derivative`      — a .txt whose sha256 matches no row. The
                                 append-only log is what lets flip tell its own
                                 output from someone's hand-written work, and
                                 an unlogged file makes `flip extract` refuse.
    `missing-derivative`       — a captured document, a lane configured that
                                 could read it, and no derivative. An
                                 expected-until-use notice, not a defect.
    """
    try:
        rows = read_jsonl(root / DERIVATIONS)
    except ValueError:
        return  # _check_ledgers already reported it as bad-jsonl
    page_ids = {p.id for p in source_pages if p.id}

    latest: dict[str, dict] = {}
    attempted: set[str] = set()
    logged_hashes: set[str] = set()
    for row in rows:
        sid = str(row.get("source_id") or "")
        for out in row.get("outputs") or []:
            if isinstance(out, dict) and out.get("sha256"):
                logged_hashes.add(str(out["sha256"]))
        if not sid or sid not in page_ids:
            continue
        # Only a row that SETTLES the question stops the missing-derivative
        # notice: outputs (there is a derivative) or `not-extracted` (the tool
        # ran clean and there was no text in the document — a finding about the
        # document, and the honest end of the matter).
        #
        # A `failed` row settles nothing. The extraction never happened; the
        # toolchain broke. Counting it as an attempt let a misconfigured lane
        # silence the notice permanently — observed on a real notebook, where a
        # bad html lane failed twice and doctor then reported nothing missing
        # while nothing had been extracted.
        if row.get("outputs") or str(row.get("status") or "") == "not-extracted":
            attempted.add(sid)
        if str(row.get("kind") or "") != "text" or not row.get("outputs"):
            continue
        prior = latest.get(sid)
        if prior is None or str(row.get("ts") or "") >= str(prior.get("ts") or ""):
            latest[sid] = row

    for sid, row in sorted(latest.items()):
        fidelity = sources_mod.derivative_fidelity(row)
        out = (row.get("outputs") or [{}])[0]
        rel = str(out.get("path") or DERIVATIONS)
        if fidelity == "thin":
            findings.append(
                _warn(
                    "thin-derivative",
                    f"source {sid}: {rel} holds {out.get('words')} words from a "
                    f"{row.get('pages')}-page document ({row.get('words_per_page')} "
                    f"words/page) — too little to be its text. An image-only scan, a "
                    "text layer the tool declined to trust, and an extractor silently "
                    "skipping pages all look like this. Read it before quoting it, then "
                    f"re-extract through an OCR lane (`flip extract {sid} --via … "
                    "--method ocr`) — raw custody is untouched either way",
                    rel,
                )
            )
        method = str(row.get("method") or "")
        if not method:
            findings.append(
                _warn(
                    "unvocabularied-extraction",
                    f"source {sid}: the derivation of {rel} records no extraction method, "
                    "so a quotation taken from it cannot say whether it came from the "
                    "document's own text layer or from an OCR engine reading a picture "
                    f"of it — and those are not the same evidence. Re-run with "
                    f"`flip extract {sid} --method "
                    + "|".join(sources_mod.EXTRACTION_METHODS) + "`",
                    rel,
                    expected=True,
                )
            )
        elif method not in sources_mod.EXTRACTION_METHODS:
            findings.append(
                _warn(
                    "unvocabularied-extraction",
                    f"source {sid}: extraction method '{method}' is not a method (one of: "
                    f"{', '.join(sources_mod.EXTRACTION_METHODS)}) — it reads like a tool "
                    "name. Methods travel between deployments and tool names don't, and "
                    "`tool`/`tool_version` already record the actor",
                    rel,
                )
            )

    text_dir = root / "sources" / "text"
    if text_dir.is_dir():
        for path in sorted(text_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if sha256_file(path) in logged_hashes:
                continue
            findings.append(
                _warn(
                    "unlogged-derivative",
                    f"{rel} matches no row in {DERIVATIONS} — flip did not write these "
                    "bytes, so a person did. That is allowed and it is not tracked: no "
                    "row says what it was derived from, by what tool, or by what method. "
                    "Log it, or let `flip extract --force` replace it (which discards it)",
                    rel,
                )
            )

    # Deliberately NOT gated on whether this machine has a lane configured.
    #
    # Gating it there was tried and reverted: it made doctor's output a function
    # of the machine it ran on, so two people linting the same committed
    # notebook got different findings — and the one seeing nothing was the one
    # with no extractor configured, i.e. exactly the person who most needed to
    # know the text was missing. Every other check reads only the notebook, and
    # this one now does too.
    #
    # "This capture has no readable derivative" is a fact about the notebook,
    # true whatever is installed, and it does not presume a tool exists that
    # could read it (which §16 would forbid): reading the bytes yourself is a
    # legitimate answer, and so is deciding this source never needed text. It
    # stays `expected=True` so it sits with the appears-with-use notices rather
    # than reading as breakage.
    for page in source_pages:
        sid = page.id or ""
        if not sid or sid in attempted:
            continue
        local = str(page.fm.get("local") or "")
        if not local or not (root / local).is_file():
            continue
        family = sources_mod.media_family(local)
        if family not in sources_mod.DOCUMENT_FAMILIES:
            continue
        lanes = integrations.extraction_lanes()
        how = (
            f"`flip extract {sid}` derives it and logs how"
            if family in lanes
            else f"no [extractors].{family} lane is configured here — add one, or read the "
            f"bytes yourself; a source with no text derivative is still a source"
        )
        findings.append(
            _warn(
                "missing-derivative",
                f"source {sid}: {local} is a {family} in custody, but "
                f"sources/text/{sid}.txt does not exist — nothing here can be read or "
                f"quoted without opening the binary. {how}",
                _rel(page, root),
                expected=True,
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
    claims_by_id = {p.id: p.fm for p in claim_pages if p.id}
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
        # A role flip cannot read is a claim whose citations do not mean what
        # they say. It reads as `evidence` (claims.citation_role) so a typo can
        # never quietly excuse a claim from the bar — and it is named here, so
        # the operator who meant `subject` finds out.
        for entry in pages.as_list(page.fm.get("sources")):
            role = str(entry.get("role") or "").strip() if isinstance(entry, dict) else ""
            if role and role not in CITATION_ROLES:
                findings.append(
                    _error(
                        "bad-enum",
                        f"claim {cid}: citation role '{role}' invalid "
                        f"(one of: {', '.join(CITATION_ROLES)}); it is being read as "
                        "'evidence', so the claim is being held to the corroboration bar "
                        "whether or not that was the intent",
                        rel,
                    )
                )
        claim_sources = claim_source_ids(page.fm)
        counted = evidence_ids(page.fm)
        subjects = subject_ids(page.fm)
        corroboration = claim_corroboration(source_fms, page.fm)
        stored = page.fm.get("independent_corroboration")
        if stored is not None and corroboration is None:
            findings.append(
                _warn(
                    "corroboration-drift",
                    f"claim {cid} stores independent_corroboration {stored}, but every "
                    f"source it cites ({', '.join(subjects)}) is cited as what the claim "
                    "is ABOUT — there is nothing for the count to count, and a stored "
                    "number here reads as a verdict on evidence the claim never claimed "
                    f"to have. Run `flip claim status {cid} {status or 'asserted'}` to "
                    "drop the key; the axis that applies is an attribution test",
                    rel,
                )
            )
        elif stored is not None and stored != corroboration:
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
        # A dangling edge is reported only where it lives — on the claim whose
        # own derives_from carries the unknown id — so the message states a
        # true fact and the suggested `derives rm` actually works. (Reporting
        # it transitively re-asserted the edge on every descendant and
        # prescribed a command those claims refuse.) Every direct edge gets
        # its turn when its owning claim's iteration comes around.
        direct = derivation_ids(page.fm)
        for ancestor in dict.fromkeys(direct):
            if ancestor != cid and ancestor not in claims_by_id:
                findings.append(
                    _warn(
                        "dangling-derivation",
                        f"claim {cid} derives from '{ancestor}', which no claims/ "
                        "page carries; fix the id or drop the edge "
                        f"(`flip claim derives rm {cid} {ancestor}`)",
                        rel,
                    )
                )
        # The DRIFT rule: an unsupported ancestor contaminates every claim
        # built on it. Walk the whole derivation chain (hand-edited cycles
        # must not hang the doctor, hence the visited set) and name each
        # offending ancestor once — on the load-bearing descendant, where the
        # operator deciding whether to lean on it is looking.
        if page.fm.get("load_bearing"):
            seen_ancestors: set[str] = set()
            frontier = list(direct)
            while frontier:
                ancestor = frontier.pop()
                if ancestor in seen_ancestors or ancestor == cid:
                    continue
                seen_ancestors.add(ancestor)
                if ancestor not in claims_by_id:
                    continue  # named above by the claim that owns the edge
                frontier.extend(derivation_ids(claims_by_id[ancestor]))
                reason = unsupported_reason(claims_by_id[ancestor])
                if reason:
                    findings.append(
                        _warn(
                            "inherited-unsupported",
                            f"load-bearing claim {cid} rests on {ancestor}, which cannot "
                            f"carry it ({reason}); support {ancestor}, or cut the "
                            f"derivation and let {cid} stand on its own evidence",
                            rel,
                        )
                    )
        # The absence key's own vocabulary, audited on ANY claim (the write
        # path refuses these; doctor is the validator for hand edits). A
        # scope nothing can read means the null's coverage cannot be read
        # either — worse than no absence mark at all.
        absence = page.fm.get("absence")
        if absence is not None:
            scope = absence.get("scope") if isinstance(absence, dict) else None
            surfaces_named = (
                [s for s in pages.as_list(absence.get("surfaces")) if str(s).strip()]
                if isinstance(absence, dict) else []
            )
            if scope not in util.ABSENT_FROM:
                findings.append(
                    _error(
                        "bad-enum",
                        f"claim {cid}: absence scope '{scope}' invalid "
                        f"(one of: {', '.join(util.ABSENT_FROM)}); until it reads, "
                        "the null's coverage is unreadable",
                        rel,
                    )
                )
            elif scope != "corpus" and not surfaces_named:
                findings.append(
                    _warn(
                        "unscoped-absence",
                        f"claim {cid} asserts an absence beyond this corpus "
                        f"(scope '{scope}') naming no searched surfaces — the "
                        "null's evidentiary weight IS its coverage; add "
                        "absence.surfaces or narrow the scope to 'corpus'",
                        rel,
                    )
                )
        if not page.fm.get("load_bearing"):
            continue
        # An absence claim scoped to `world` asserts more than any search can
        # witness — no surface list, however long, covers the world. The
        # honest scope is the surfaces actually searched; `world` stays legal
        # (the operator may take responsibility for the reach) but a
        # load-bearing one gets named, because the wider the claimed reach
        # the less the recorded coverage supports it.
        absence = page.fm.get("absence")
        if isinstance(absence, dict) and str(absence.get("scope")) == "world":
            findings.append(
                _warn(
                    "world-absence",
                    f"load-bearing absence claim {cid} is scoped to 'world' — no "
                    "search can witness a world-absence; narrow it to the surfaces "
                    "actually checked (scope 'named_surfaces') or say in the claim "
                    "text why world-scope is defensible here",
                    rel,
                )
            )
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
        # The audit a subject citation CAN have, and hasn't. Reported wherever
        # the claim sits in its lifecycle, because unlike the corroboration
        # nags this one is not waiting on evidence to arrive: the document is
        # already in custody and the reading is already available. It is also
        # the anti-abuse half of the citation-role design — a `subject` role
        # is authored, so it can be used to duck a bar the claim should have
        # faced, and naming the untaken audit is what makes that visible
        # rather than merely possible.
        unaudited = unaudited_subjects(page.fm)
        if unaudited:
            findings.append(
                _warn(
                    "unaudited-claim",
                    f"load-bearing claim {cid} cites {', '.join(unaudited)} as the "
                    f"source(s) it is ABOUT, and no severe attribution test has survived "
                    f"against {'it' if len(unaudited) == 1 else 'them'}. A second source is "
                    "not the ask here and never will be — nothing in the world can witness "
                    "what a document says except the document. What can be asked is whether "
                    "the claim is right about it, and anyone can re-run that against the "
                    f"same bytes: `flip claim test {cid} --probe attribution --error "
                    f'"<what the claim could be getting wrong about {unaudited[0]}>" '
                    '--would-detect "<how that would have shown up>" --if-absent "<what '
                    'you would have seen instead>" '
                    f"--against {unaudited[0]} --result survived|failed`",
                    rel,
                )
            )
        if status == "verified" and profile is not None and corroboration is None:
            # The doctor mirror of `_refuse_verified_subject_claim`: a
            # subject-only claim can never satisfy a bar that counts witnesses,
            # so demanding one of it would be a finding nobody can clear, and a
            # lint nobody can clear is one everybody learns to skip. The claim
            # is under-verified here only when the audit it COULD have is
            # missing — and the `unaudited-claim` above already says how to
            # take it, so this one says what the status costs.
            if unaudited and not has_gating_verification(page.fm):
                findings.append(
                    _error(
                        "under-verified",
                        f"claim {cid} is 'verified' and cites only what it is ABOUT "
                        f"({', '.join(subjects)}), with no severe attribution test "
                        "surviving against it. The corroboration bar is not unmet here, it "
                        "is inapplicable — so do not add a source to clear this. Record "
                        f"the test that WAS available (`flip claim test {cid} --probe "
                        "attribution …`), or set status needs-2nd until somebody has read "
                        "the document against the claim",
                        rel,
                    )
                )
        elif status == "verified" and profile is not None:
            # Recompute the bar with the shared helper (claims.claim_corroboration:
            # deduped evidence ids, judged + original only); never trust the stored
            # count. An adversarial/recomputation verification clears the gate too (A2).
            linked = [by_id[s] for s in dict.fromkeys(counted) if s in by_id]
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
                if subjects:
                    msg += (
                        f". NOTE {', '.join(subjects)} "
                        f"{'is' if len(subjects) == 1 else 'are'} cited as what the claim "
                        "is ABOUT and is deliberately not in that count"
                    )
                # Never let the count stand alone as a verdict on the evidence:
                # an uncountable source drops out silently and the claim then
                # fails for a reason that has nothing to do with what it rests on.
                stale = uncountable_sources(source_fms, counted)
                if stale:
                    msg += (
                        f". NOTE {', '.join(stale)} "
                        f"{'carries' if len(stale) == 1 else 'carry'} pre-0.8 "
                        "independence vocabulary and could not be counted either way, "
                        "so that count understates the evidence rather than measuring it"
                    )
                findings.append(_error("under-verified", msg, rel))
        elif (
            status == "asserted"
            and corroboration == 0
            # One unaudited-claim per claim: the subject branch above has
            # already named the audit this page owes, and repeating the code
            # with the generic "link independent sources" advice would offer a
            # cheaper exit than the one that actually applies.
            and not unaudited
            and not pages.as_list(page.fm.get("verified"))
            # A severe test IS an audit — it went looking for a specific error and
            # either found it or didn't. Reading only corroboration and `verified`
            # meant this fired on a claim carrying a severe attribution test and
            # told its author to "record a check", which they had. What the result
            # WAS is not this check's business: a refuted claim held in the open is
            # `flip claim exposure`'s to talk about, and silence here is not
            # approval, only the absence of the thing this check is about.
            and stance.derive_exposure(page.fm) == "bent"
        ):
            findings.append(
                _warn(
                    "unaudited-claim",
                    f"load-bearing claim {cid} is 'asserted' with no corroboration, no "
                    f"verification, and nothing on record that went looking for the error; "
                    f"link independent sources (`flip claim source add {cid} <src>`), test "
                    f"it (`flip claim test {cid} --probe attribution|substance|scope …`), "
                    f"record a check (`flip claim verify {cid} --method adversarial`), or "
                    "set status needs-2nd",
                    rel,
                )
            )


# --- stance & exposure (SPEC §7.1) ------------------------------------------------


def _check_stance(
    root: Path,
    manifest: Manifest | None,
    claim_pages: list[pages.Page],
    findings: list[Finding],
) -> None:
    """Lint the attitude axis (SPEC §7.1) — and lint it only where it is used.

    Every check here is silent on a claim carrying neither `stances:` nor
    `tests:`, which is most claims in most notebooks. That is deliberate:
    the axis is opt-in, and a lint that fires the moment a feature EXISTS
    teaches operators to tune doctor out (E3) — the thing that makes the
    findings that matter unreadable. A notebook that never records a stance
    sees nothing new here.

    Seven findings, in the order they cost you something:

    - `stored-exposure` — a page storing the derived verdict. ERROR always:
      an exposure at rest is a verdict frozen out of the record it summarizes,
      and it will be wrong the day the next test lands (the same reason a
      letter grade is derived, §5.4).
    - `unpriced-stance` — `pursuing` or `rejecting` with no falsifier. flip
      refuses to WRITE one, so finding one means the page was hand-edited or
      arrived from elsewhere, and the notebook is holding a position with no
      stated way out.
    - `misattributed-citation` — a claim a severe attribution test found wrong
      about a source, still citing that source. This is the muse failure as a
      lint, and the only one here that hardens to ERROR when the notebook
      closes: shipping a claim whose own record says it misquotes its source
      is the failure a reader can neither see nor forgive.
    - `unexamined-position` — the notebook taking a position on a load-bearing
      claim whose exposure is `bent`. **Both `holding` and `pursuing` count**,
      and an earlier draft of this check is the reason that has to be said
      twice: it fired on `holding` only, so switching the stance to `pursuing`
      silenced the notebook's only warning about untested belief — and
      `pursuing` was, at the time, a state with no exit. The design had a
      gradient running downhill toward the one place nothing could reach it.
      Now the stance changes only the advice, never whether the finding fires,
      and the single way to clear it is to record a test.
    - `losing-to-a-rival` — the notebook is still working from a claim a severe
      test found wrong, while a claim it has itself declared a rival is
      severely tested. Lakatos's criterion (p.69), reported and never enforced.
    - `no-declared-rival` — a load-bearing claim being pursued with nothing on
      record that could have beaten it. The honest limits of this one are in
      its own message.
    - `unsourced-holder` — a belief attributed to someone with nothing cited
      to show they hold it.
    """
    closed = manifest is not None and manifest.status in CLOSED_STATUSES
    exposures = {
        str(p.fm.get("id")): stance.derive_exposure(p.fm)
        for p in claim_pages if p.fm.get("id")
    }
    for page in claim_pages:
        fm = page.fm
        records = stance.stance_records(fm)
        tests = stance.test_records(fm)
        if not records and not tests and not stance.rival_records(fm):
            continue
        cid = page.id or "?"
        rel = _rel(page, root)

        for key in ("exposure", "severity"):
            if key in fm:
                findings.append(
                    _error(
                        "stored-exposure",
                        f"claim {cid} stores '{key}' — exposure and severity are DERIVED "
                        "from the `tests:` record and never written to a page (SPEC §7.1, "
                        "the rule that makes `grade` a summary rather than an opinion); "
                        f"drop the key and read it with `flip claim exposure {cid}`",
                        rel,
                    )
                )
        for record in records:
            value = str(record.get("stance") or "")
            if value not in stance.STANCES:
                findings.append(
                    _error(
                        "bad-enum",
                        f"claim {cid}: stance '{value}' invalid "
                        f"(one of: {', '.join(stance.STANCES)})",
                        rel,
                    )
                )
        for record in tests:
            for name, value, allowed in (
                ("probe", str(record.get("probe") or ""), stance.TEST_PROBES),
                ("result", str(record.get("result") or ""), stance.TEST_RESULTS),
            ):
                if value not in allowed:
                    findings.append(
                        _error(
                            "bad-enum",
                            f"claim {cid}: test {name} '{value}' invalid "
                            f"(one of: {', '.join(allowed)})",
                            rel,
                        )
                    )

        unpriced = stance.unpriced_stances(fm)
        if unpriced:
            words = ", ".join(dict.fromkeys(str(r.get("stance")) for r in unpriced))
            msg = (
                f"claim {cid} is '{words}' with no falsifier — that is a position taken "
                "ahead of, or against, the evidence, and the licence to hold one costs a "
                "written account of what would move you off it. Re-record it: "
                f"`flip claim stance {cid} {unpriced[0].get('stance')} --because … "
                "--falsifier …`"
            )
            findings.append(
                _error("unpriced-stance", msg, rel) if fm.get("load_bearing")
                else _warn("unpriced-stance", msg, rel)
            )

        exposure = stance.derive_exposure(fm)
        if exposure == "misattributed":
            cited = set(claim_source_ids(fm))
            still = sorted(s for s in stance.failed_attribution_sources(fm) if s in cited)
            about = set(subject_ids(fm))
            if still:
                msg = (
                    f"claim {cid} failed a severe attribution test against "
                    f"{', '.join(still)} and still cites {'it' if len(still) == 1 else 'them'}"
                    " — the claim is not what that source says. "
                )
                if about.issuperset(still):
                    # Unlinking is the wrong repair when the source is what the
                    # claim is ABOUT: drop the citation and the claim stops
                    # being about anything. Only the wording can go.
                    msg += (
                        f"Do NOT unlink {'it' if len(still) == 1 else 'them'}: the claim "
                        "is ABOUT that source, so a claim without it is not a repaired "
                        "claim, it is a claim with nothing left to be true of. Restate it "
                        "in the source's own words, or open the claim the source does "
                        f"support and concede to it (`flip claim supersede {cid} --by <C#>"
                        '`). '
                    )
                else:
                    msg += (
                        "Restate the claim in the "
                        f"source's own words, or unlink it (`flip claim source rm {cid} "
                        f"{still[0]}`) and assert the claim the source does support. "
                    )
                msg += (
                    "This is a citation failure and says nothing about whether the claim "
                    "is true"
                )
                findings.append(
                    _error("misattributed-citation", msg, rel) if closed
                    else _warn("misattributed-citation", msg, rel)
                )

        own = stance.notebook_stance(fm)
        own_stance = str((own or {}).get("stance") or "")
        unexamined = (
            own_stance in ("holding", "pursuing")
            and exposure == "bent"
            and bool(fm.get("load_bearing"))
        )
        if unexamined:
            # The two stances get the same finding and different advice. That
            # is the whole point: an operator who reads "switch to pursuing"
            # as the fix has been handed a way to make the warning go away
            # without asking anything of the claim, and a warning with a
            # cheaper exit than the work it asks for is a warning that trains
            # people to take the exit.
            if own_stance == "pursuing":
                tail = (
                    "You have written a falsifier for it; run a test that could have come "
                    "out the other way and record what it found: "
                    f"`flip claim test {cid} --probe … --error … --would-detect … "
                    "--if-absent … --against … --result …`. Pursuing a claim with no reading "
                    "on it is legitimate and is exactly what this axis exists to let you "
                    "say; pursuing one indefinitely without ever getting a reading is the "
                    "thing that looks identical from the outside"
                )
            else:
                tail = (
                    f"Holding is a defended position. Either test it (`flip claim test "
                    f"{cid} --probe … --error … --would-detect … --if-absent … --against … "
                    f"--result …`) or say plainly that the evidence has not reached it yet "
                    f"(`flip claim stance {cid} pursuing --because … --falsifier …`) — "
                    "which changes the wording of this finding and nothing else, because "
                    "the claim is exactly as untested either way"
                )
            findings.append(
                _warn(
                    "unexamined-position",
                    f"the notebook is '{own_stance}' load-bearing claim {cid} and its "
                    f"exposure is 'bent' — {stance.bent_reason(fm)}. {tail}",
                    rel,
                )
            )

        rivals = stance.rival_ids(fm)
        beating = [r for r in rivals if exposures.get(r) == "severely-tested"]
        if own_stance in ("holding", "pursuing") and exposure in stance.REFUTING_EXPOSURES \
                and beating:
            findings.append(
                _warn(
                    "losing-to-a-rival",
                    f"the notebook is '{own_stance}' claim {cid} (exposure: {exposure} — a "
                    f"severe test found the error), while {', '.join(beating)}, declared to "
                    f"answer the same question, {'is' if len(beating) == 1 else 'are'} "
                    "severely tested. That is the comparison Lakatos says a decision to let "
                    "go actually rests on: 'a degenerating problemshift is no more a "
                    "sufficient reason to eliminate a research programme than some "
                    "old-fashioned refutation… such an objective reason is provided by a "
                    "rival research programme which explains the previous success of its "
                    f"rival' (p.69). Concede if that is what happened (`flip claim supersede "
                    f"{cid} --by {beating[0]} --because …`), or say what {cid} still "
                    f"explains that {beating[0]} does not — flip cannot check the second "
                    "half of his criterion and is not making this call for you",
                    rel,
                )
            )

        # Q3, the open problem: rival comparison relocates the burden onto
        # declaring your own competition, and the operator most likely to be
        # stuck is the least likely to name a rival. This check is the honest
        # part of what a tool can do about that — it reports a fact about the
        # RECORD ("you have never named anything that could win"), never a
        # fact about the world ("there is no alternative"), and its own message
        # says so. It is a WARN forever and it is suppressed when
        # `unexamined-position` already fired, because a claim nobody has
        # tested has a nearer problem than a claim nobody has a challenger for,
        # and two findings on one line is how a doctor run stops being read.
        if own_stance == "pursuing" and fm.get("load_bearing") and not rivals \
                and not unexamined:
            findings.append(
                _warn(
                    "no-declared-rival",
                    f"the notebook is pursuing load-bearing claim {cid} and has never "
                    "named a claim that answers the same question. This is a fact about "
                    "the notebook, not about the world: it does not say no alternative "
                    "exists, only that nothing on record could ever have won, so no "
                    f"amount of evidence can make {cid} lose to anything. Write the best "
                    "alternative you can state — even one you think is wrong — and link "
                    f"it (`flip claim add \"…\"` then `flip claim rival {cid} <C#> "
                    "--because \"<the question both answer>\"`). If you genuinely cannot "
                    "state one, that is worth knowing on its own, and the honest place to "
                    f"put it is the `--because` on the stance",
                    rel,
                )
            )

        for holder in stance.unsourced_holders(fm):
            findings.append(
                _warn(
                    "unsourced-holder",
                    f"claim {cid} records a stance held by '{holder}' with nothing cited "
                    "to show they hold it. That someone believes something is an "
                    "assertion about them and needs evidence like any other; cite it "
                    f"(`flip claim stance {cid} … --holder \"{holder}\" --source <id>`), or "
                    "assert the prevalence as its own claim and cite that",
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
    target_names = {
        "claim": claim_names, "cluster": cluster_names, "question": question_names,
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
                        "(claim:<ref>, cluster:<ref>, question:<ref>) — every "
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


# --- questions: the journey vocabulary (SPEC §7) --------------------------------


def _check_questions(root: Path, by_dir: dict, findings: list[Finding]) -> None:
    """The question journey's enums and dates, auditable after hand edits.

    The views deliberately keep unknown-status questions on the roster (a
    typo degrades to visible); this is the check that NAMES the typo. A
    dormant page's `review_by` is what resurfacing keys off, so an
    unreadable or missing date gets its own finding — the question would
    otherwise sit on the roster marked due forever with nobody told why.
    """
    for page in by_dir.get("questions", []):
        if str(page.fm.get("type", "")) != "Question":
            continue
        qid = page.id or "?"
        rel = _rel(page, root)
        status = page.fm.get("status")
        if status is not None and status not in QUESTION_STATUSES:
            findings.append(
                _error(
                    "bad-enum",
                    f"question {qid}: status '{status}' invalid "
                    f"(one of: {', '.join(QUESTION_STATUSES)}); the roster shows "
                    "it as needing work until the status reads",
                    rel,
                )
            )
        reason = page.fm.get("closed_reason")
        if reason is not None and reason not in CLOSED_REASONS:
            findings.append(
                _error(
                    "bad-enum",
                    f"question {qid}: closed_reason '{reason}' invalid "
                    f"(one of: {', '.join(CLOSED_REASONS)})",
                    rel,
                )
            )
        if status == "dormant":
            review_by = str(page.fm.get("review_by", ""))
            try:
                datetime.strptime(review_by, "%Y-%m-%d")
            except ValueError:
                findings.append(
                    _warn(
                        "undated-dormant",
                        f"question {qid} is dormant with "
                        + (f"an unreadable review_by '{review_by}'" if review_by
                           else "no review_by")
                        + " — parking means a YYYY-MM-DD date to resurface on; "
                        "until one reads, the question stays on the roster as due",
                        rel,
                    )
                )


# --- commissions: lifecycle vocabulary (SPEC §7.4) -------------------------------


def _check_commissions(root: Path, by_dir: dict, findings: list[Finding]) -> None:
    """Commission status stays inside its lifecycle vocabulary after hand edits."""
    for page in by_dir.get("commissions", []):
        if str(page.fm.get("type", "")) != "Commission":
            continue
        kid = page.id or "?"
        rel = _rel(page, root)
        status = page.fm.get("status")
        if status is not None and status not in COMMISSION_STATUSES:
            findings.append(
                _error(
                    "bad-enum",
                    f"commission {kid}: status '{status}' invalid "
                    f"(one of: {', '.join(COMMISSION_STATUSES)})",
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
