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

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import pages, workspace
from .beat import find_beat_root, load_beat
from .claims import STATUSES as CLAIM_STATUSES  # claim status enum (SPEC §7)
from .claims import corroboration_count
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
)

PROVENANCE = "sources/_provenance.jsonl"
# Every JSONL ledger the format defines; each must at least parse.
LEDGERS = (PROVENANCE, "derived/_derivations.jsonl", "log/log.jsonl", "log/passed.jsonl")

# Entity directories whose pages must carry a compact id; sessions are entity
# pages too but have no id scheme (SPEC §8), so they are exempt here.
_ID_DIRS = ("references", "claims", "decisions", "questions")
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


@dataclass
class Finding:
    level: str  # "ERROR" | "WARN"
    code: str  # short slug, e.g. "orphan-custody"
    message: str  # one actionable line
    path: str  # path relative to the notebook root


def _error(code: str, message: str, path: str) -> Finding:
    return Finding("ERROR", code, message, path)


def _warn(code: str, message: str, path: str) -> Finding:
    return Finding("WARN", code, message, path)


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
    _check_claims(root, claim_pages, source_pages, profile, findings)
    return findings


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
    for handle, nb_root, rel in checked:
        # Handles binding this same notebook in an enclosing or nested
        # workspace table are that table's aliases, not stale ones — stripping
        # them here would fight the other workspace's doctor forever.
        legitimate = {handle} | workspace.other_workspace_handles(ws_root, nb_root)
        for dirname in pages.SCAN_DIRS:
            found, _errors = pages.iter_pages_tolerant(nb_root, dirname)
            for page in found:
                stem_owners.setdefault(page.path.stem, set()).add(handle)
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
    make = _error if closed else _warn
    detail = (
        f"required before status '{manifest.status}'"
        if closed
        else "it appears with use; required before done/published/archived"
    )
    for rel in profile.requires:
        if not (root / rel).exists():
            findings.append(
                make(
                    "missing-required",
                    f"profile '{profile.id}' requires {rel} ({detail}); create it",
                    rel,
                )
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
    logged_ids = {str(p.get("source_id")) for p in provenance if p.get("source_id")}
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
                findings.append(
                    _error(
                        "bad-enum",
                        f"source {sid}: {field} '{value}' invalid (one of: {', '.join(valid)})",
                        rel,
                    )
                )
    for sid in sorted(logged_ids - page_ids):
        findings.append(
            _warn(
                "orphan-provenance",
                f"provenance records a capture for {sid} but references/ has no page with "
                "that id; restore the page (its id stays reserved either way)",
                PROVENANCE,
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
        claim_sources = [str(s) for s in pages.as_list(page.fm.get("sources"))]
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
        if not page.fm.get("load_bearing"):
            continue
        if status == "asserted":
            findings.append(
                _warn(
                    "unaudited-claim",
                    f"load-bearing claim {cid} is still 'asserted'; "
                    "verify it or set status needs-2nd",
                    rel,
                )
            )
        elif status == "verified" and profile is not None:
            # Recompute the bar with the shared helper (claims.corroboration_count:
            # deduped ids, judged + original only); never trust the stored count.
            linked = [by_id[s] for s in dict.fromkeys(claim_sources) if s in by_id]
            has_grade_a = any(fm.get("grade") == "A" for fm in linked)
            ok = corroboration >= profile.claim_min_independent or (
                profile.claim_grade_a_suffices and has_grade_a
            )
            if not ok:
                suffix = " or one grade-A primary" if profile.claim_grade_a_suffices else ""
                findings.append(
                    _error(
                        "under-verified",
                        f"claim {cid} is 'verified' with {corroboration} independent "
                        f"source(s); profile '{profile.id}' needs "
                        f"{profile.claim_min_independent}{suffix} — add corroboration "
                        "or set status needs-2nd",
                        rel,
                    )
                )
