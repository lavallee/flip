"""Claims as entity pages — claims/<slug>.md (SPEC §7).

Each claim is one markdown page: frontmatter carries what a machine needs
(id, status, load_bearing, source ids, computed corroboration), the body
carries the full assertion, any caveat notes, and a generated `# Citations`
edge list. Ids are never reused: retracted and superseded claims keep their
pages, and allocation (pages.allocate_id) also counts ids that only survive
in the ledgers or the .flip/ids reservation file.

`independent_corroboration` is computed, never hand-set: the count of a
claim's listed source ids (deduped) whose references/ page is JUDGED — grade
A/B/C, never "?" — with independence == "original" (SPEC §5.4: ungraded
sources never corroborate; capture is custody, not judgment). It is
recomputed on every status change so the number tracks the pages as gradings
evolve. `corroboration_count` is the one shared implementation; doctor's
under-verified check uses it too.

Ownership on a claim page (SPEC §6.6): flip owns the frontmatter keys it
writes plus the `# Citations` section of the body (regenerated on status
changes so links track source slugs); everything else — foreign frontmatter,
prose above the citations — round-trips untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import manifest, pages, profiles, util

STATUSES = (
    "asserted",
    "verified",
    "needs-2nd",
    "unconfirmed",
    "false-positive",
    "retracted",
    "superseded",
)

# Grades that count as a recorded judgment; "?" is custody, not judgment.
JUDGED_GRADES = ("A", "B", "C")

CITATIONS_HEADING = "# Citations"

# Frontmatter description is a one-line OKF summary; the body holds the full text.
_DESCRIPTION_MAX = 160


def _linked_fms(source_fms: list[dict], source_ids: list[str]) -> list[dict]:
    """Frontmatter dicts matching the given source ids, deduped; unknown ids
    contribute nothing (dangling citations are legal — doctor counts them)."""
    by_id = {str(fm.get("id")): fm for fm in source_fms}
    return [by_id[s] for s in dict.fromkeys(str(s) for s in source_ids) if s in by_id]


def corroboration_count(source_fms: list[dict], source_ids: list[str]) -> int:
    """Independent corroboration for a claim, per SPEC §5.4/§7.

    Counts the claim's source ids (deduped — listing a source twice never
    counts twice) whose references/ page is judged (grade A/B/C — a grade-"?"
    page counts toward nothing, whatever its capture-time defaults say) AND
    independence == "original". Shared by add_claim/set_claim_status and
    doctor's under-verified check.
    """
    return sum(
        1
        for fm in _linked_fms(source_fms, source_ids)
        if fm.get("grade") in JUDGED_GRADES and fm.get("independence") == "original"
    )


def _source_pages_by_id(root: Path) -> dict[str, pages.Page]:
    return {p.id: p for p in pages.iter_pages(root, "references") if p.id}


def _claim_pages(root: Path) -> list[pages.Page]:
    return pages.iter_pages(root, "claims")


def _description(text: str) -> str:
    if len(text) <= _DESCRIPTION_MAX:
        return text
    return text[: _DESCRIPTION_MAX - 1].rstrip() + "…"


def _citations(
    src_by_id: dict[str, pages.Page], source_ids: list[str]
) -> tuple[list[str], list[str]]:
    """(supports, citation lines) for a claim's sources, deduped, in order.

    Resolvable ids become bundle paths (`/references/<slug>`) and relative
    markdown links; unresolvable ids are cited as plain text — dangling is
    legal (SPEC §6.1), doctor counts them.
    """
    supports: list[str] = []
    lines: list[str] = []
    for n, sid in enumerate(dict.fromkeys(str(s) for s in source_ids), 1):
        page = src_by_id.get(sid)
        if page is None:
            lines.append(f"[{n}] {sid}")
        else:
            supports.append(f"/references/{page.slug}")
            label = str(page.fm.get("title") or sid)
            lines.append(f"[{n}] [{label}](../references/{page.slug}.md)")
    return supports, lines


def _citations_block(lines: list[str]) -> str:
    return CITATIONS_HEADING + "\n" + "\n".join(lines) + "\n" if lines else ""


def _replace_citations(body: str, lines: list[str]) -> str:
    """Swap the generated `# Citations` section (heading to end of body) for a
    fresh one; prose above it survives byte-for-byte modulo trailing blanks."""
    idx = body.find(CITATIONS_HEADING)
    while idx > 0 and body[idx - 1] != "\n":
        idx = body.find(CITATIONS_HEADING, idx + 1)
    head = (body if idx == -1 else body[:idx]).rstrip("\n")
    block = _citations_block(lines)
    if not block:
        return head + "\n" if head else ""
    return (head + "\n\n" + block) if head else block


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10)."""
    from . import views

    views.regenerate(root)


def add_claim(
    root: Path,
    text: str,
    sources: list[str],
    load_bearing: bool = False,
    notes: str | None = None,
) -> pages.Page:
    """Add a claim page with status "asserted", allocating the next C#."""
    root = util.require_notebook_root(root)
    text = (text or "").strip()
    if not text:
        raise SystemExit("empty claim text; state the assertion in one sentence")
    source_ids = [str(s) for s in pages.as_list(sources)]
    claim_id = pages.allocate_id(root, "C")
    src_by_id = _source_pages_by_id(root)
    supports, citation_lines = _citations(src_by_id, source_ids)

    fm: dict = {
        "type": "Claim",
        "id": claim_id,
        "aliases": [claim_id],
        "description": _description(text),
        "status": "asserted",
        "load_bearing": bool(load_bearing),
        "sources": source_ids,
        "supports": supports,
        "independent_corroboration": corroboration_count(
            [p.fm for p in src_by_id.values()], source_ids
        ),
        "first_asserted": util.today(),
        "actor": util.detect_actor(),
    }
    if notes:
        fm["notes"] = notes

    parts = [text]
    if notes:
        parts.append(f"_{notes}_")
    block = _citations_block(citation_lines)
    if block:
        parts.append(block.rstrip("\n"))
    body = "\n\n".join(parts) + "\n"

    claims_dir = root / "claims"
    slug = pages.unique_slug(claims_dir, pages.slugify(text, fallback=claim_id.lower()))
    path = pages.write_page(claims_dir / f"{slug}.md", fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=path, fm=fm, body=body)


def set_claim_status(root: Path, claim_id: str, status: str) -> pages.Page:
    """Move a claim to a new status, recomputing independent_corroboration and
    refreshing supports + the `# Citations` block against current source slugs.

    "verified" is gated by the notebook profile's verification bar: at least
    `claim_min_independent` sources with independence == "original", or — when
    `claim_grade_a_suffices` — any listed source graded A. Only judged sources
    count. Refusal writes nothing. Returns the updated page.
    """
    root = util.require_notebook_root(root)
    if status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    page = next((p for p in _claim_pages(root) if p.id == claim_id), None)
    if page is None:
        known = ", ".join(p.id for p in _claim_pages(root) if p.id) or "none yet"
        raise SystemExit(
            f"no claim '{claim_id}' in claims/ (known: {known}); add it with `flip claim add`"
        )
    source_ids = [str(s) for s in pages.as_list(page.fm.get("sources"))]
    src_by_id = _source_pages_by_id(root)
    source_fms = [p.fm for p in src_by_id.values()]
    corroboration = corroboration_count(source_fms, source_ids)
    if status == "verified":
        profile = profiles.load_profile(manifest.load_manifest(root).kind, root)
        linked = _linked_fms(source_fms, source_ids)
        has_grade_a = any(fm.get("grade") == "A" for fm in linked)
        met = corroboration >= profile.claim_min_independent or (
            profile.claim_grade_a_suffices and has_grade_a
        )
        if not met:
            msg = (
                f"cannot verify {claim_id}: {corroboration} independent original source(s) "
                f"of {profile.claim_min_independent} required"
            )
            if profile.claim_grade_a_suffices:
                msg += " and no grade-A source among its sources"
            msg += (
                f" (sources: {', '.join(source_ids) or 'none'}); add independent original "
                "sources to the claim"
            )
            if profile.claim_grade_a_suffices:
                msg += " or upgrade one to grade A via `flip grade`"
            ungraded = [
                str(fm.get("id")) for fm in linked if fm.get("grade") not in JUDGED_GRADES
            ]
            if ungraded:
                msg += (
                    f"; {', '.join(ungraded)} still graded '?' and ungraded sources "
                    "never corroborate — judge them with `flip grade` first"
                )
            raise SystemExit(msg)
    supports, citation_lines = _citations(src_by_id, source_ids)
    page.fm["status"] = status
    page.fm["independent_corroboration"] = corroboration
    page.fm["supports"] = supports
    body = _replace_citations(page.body, citation_lines)
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def _id_sort_key(fm: dict) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(fm.get("id", "")))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(fm.get("id", "")), 0)


def list_claims(root: Path, status: str | None = None) -> list[dict]:
    """All claims as frontmatter dicts (+ slug and root-relative path),
    optionally filtered by status. Read-only."""
    if status is not None and status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    out = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in _claim_pages(root)
        if status is None or p.fm.get("status") == status
    ]
    return sorted(out, key=_id_sort_key)
