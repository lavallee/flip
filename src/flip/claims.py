"""Claims as entity pages — claims/<slug>.md (SPEC §7).

Each claim is one markdown page: frontmatter carries what a machine needs
(id, status, load_bearing, OKF v0.2 `sources` entries, computed
corroboration), the body carries the full assertion — footnote-marked per
the OKF per-claim attribution idiom — any caveat notes, and a generated
block of footnote definitions whose relative links keep the citation edges
visible to link-graph tools. Ids are never reused: retracted and superseded
claims keep their pages, and allocation (pages.allocate_id) also counts ids
that only survive in the ledgers or the .flip/ids reservation file.

`independent_corroboration` is computed, never hand-set: the count of a
claim's listed source ids (deduped) whose references/ page is JUDGED — grade
A/B/C, never "?" — with independence == "original" (SPEC §5.4: ungraded
sources never corroborate; capture is custody, not judgment). It is
recomputed on every status change so the number tracks the pages as gradings
evolve. `corroboration_count` is the one shared implementation; doctor's
under-verified check uses it too.

Ownership on a claim page (SPEC §6.6): flip owns the frontmatter keys it
writes plus two generated body parts — the footnote-marker cluster ending
the lead paragraph and the footnote-definition lines (both regenerated on
status/source changes so links track source slugs; labels are always
id-shaped, `[^A3]`, so hand-authored footnotes are never touched).
Everything else — foreign frontmatter, the prose itself — round-trips
untouched.
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

# Verification methods a claim can carry (SPEC §7, A2). The vocabulary widens
# the ways a claim earns `verified`, but the corroboration bar itself is
# unchanged: `independent-sources` records the corroboration *reasoning* and
# never satisfies the gate by itself; only `adversarial` and `recomputation`
# — the two below — clear the gate on their own.
VERIFICATION_METHODS = ("adversarial", "independent-sources", "recomputation")
GATING_VERIFICATION_METHODS = ("adversarial", "recomputation")

# Generated attribution, OKF v0.2 style: footnote labels are the claim's
# source ids. Both patterns are id-shaped on purpose — flip only ever edits
# markers/definitions it could have written itself.
_FOOT_DEF_RE = re.compile(r"^\[\^[A-Z]+\d+\]: .*$\n?", re.M)
_MARKER_TAIL_RE = re.compile(r"(?:\s*\[\^[A-Z]+\d+\])+\s*$")

# Frontmatter description is a one-line OKF summary; the body holds the full text.
_DESCRIPTION_MAX = 160


def source_ids(fm: dict) -> list[str]:
    """A claim's cited source ids, in order. Entries are OKF v0.2 `sources`
    maps ({id, resource, title}); bare strings (hand edits, pre-0.7 pages)
    are tolerated as ids. The one accessor every reader goes through."""
    out: list[str] = []
    for entry in pages.as_list(fm.get("sources")):
        sid = str(entry.get("id", "")) if isinstance(entry, dict) else str(entry)
        if sid.strip():
            out.append(sid.strip())
    return out


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


def has_gating_verification(fm: dict) -> bool:
    """True when a claim's `verified:` list (OKF v0.2 §5.2 events, each
    {by, at} plus flip's `method` extension key) records at least one whose
    method clears the `verified` gate on its own (adversarial/recomputation).
    Shared by set_claim_status's gate and doctor's under-verified check."""
    return any(
        isinstance(v, dict) and str(v.get("method")) in GATING_VERIFICATION_METHODS
        for v in pages.as_list(fm.get("verified"))
    )


def _source_pages_by_id(root: Path) -> dict[str, pages.Page]:
    return {p.id: p for p in pages.iter_pages(root, "references") if p.id}


def _claim_pages(root: Path) -> list[pages.Page]:
    return pages.iter_pages(root, "claims")


def _find_claim(root: Path, claim_id: str) -> pages.Page:
    """The claims/ page carrying `claim_id`, or an actionable refusal."""
    page = next((p for p in _claim_pages(root) if p.id == claim_id), None)
    if page is None:
        known = ", ".join(p.id for p in _claim_pages(root) if p.id) or "none yet"
        raise SystemExit(
            f"no claim '{claim_id}' in claims/ (known: {known}); add it with `flip claim add`"
        )
    return page


def _description(text: str) -> str:
    if len(text) <= _DESCRIPTION_MAX:
        return text
    return text[: _DESCRIPTION_MAX - 1].rstrip() + "…"


def _attribution(
    src_by_id: dict[str, pages.Page], cited: list[str]
) -> tuple[list[dict], list[str]]:
    """(OKF `sources` entries, footnote-definition lines) for a claim's cited
    ids, deduped, in order.

    Resolvable ids get a followable bundle-absolute `resource`, the page
    title, and a relative-linked definition; dangling ids keep just the id
    and a plain-text definition — dangling is legal (SPEC §6.1), doctor
    counts them.
    """
    entries: list[dict] = []
    defs: list[str] = []
    for sid in dict.fromkeys(str(s) for s in cited):
        page = src_by_id.get(sid)
        entry: dict = {"id": sid}
        if page is None:
            defs.append(f"[^{sid}]: {sid} (not captured)")
        else:
            entry["resource"] = f"/references/{page.slug}.md"
            title = str(page.fm.get("title") or "")
            if title:
                entry["title"] = title
            defs.append(f"[^{sid}]: [{title or sid}](../references/{page.slug}.md)")
        entries.append(entry)
    return entries, defs


def _apply_attribution(body: str, cited: list[str], defs: list[str]) -> str:
    """Regenerate the two body parts flip owns — the id-shaped footnote
    markers ending the lead paragraph and the definition lines — leaving the
    prose itself untouched (SPEC §6.6)."""
    text = _FOOT_DEF_RE.sub("", body).strip("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    head, sep, rest = text.partition("\n\n")
    head = _MARKER_TAIL_RE.sub("", head.rstrip())
    head += "".join(f"[^{sid}]" for sid in dict.fromkeys(str(s) for s in cited))
    text = head + sep + rest if rest else head
    if defs:
        text = (text + "\n\n" if text else "") + "\n".join(defs)
    return text + "\n" if text else ""


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
    cited = [str(s) for s in pages.as_list(sources)]
    claim_id = pages.allocate_id(root, "C")
    src_by_id = _source_pages_by_id(root)
    entries, defs = _attribution(src_by_id, cited)

    fm: dict = {
        "type": "Claim",
        "id": claim_id,
        "aliases": [claim_id],
        "description": _description(text),
        "status": "asserted",
        "load_bearing": bool(load_bearing),
        "sources": entries,
        "independent_corroboration": corroboration_count(
            [p.fm for p in src_by_id.values()], cited
        ),
        "first_asserted": util.today(),
        "generated": util.generated_now(),
    }
    if notes:
        fm["notes"] = notes

    markers = "".join(f"[^{sid}]" for sid in dict.fromkeys(cited))
    parts = [text + markers]
    if notes:
        parts.append(f"_{notes}_")
    if defs:
        parts.append("\n".join(defs))
    body = "\n\n".join(parts) + "\n"

    claims_dir = root / "claims"
    slug = pages.unique_slug(claims_dir, pages.slugify(text, fallback=claim_id.lower()))
    path = pages.write_page(claims_dir / f"{slug}.md", fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=path, fm=fm, body=body)


def set_claim_status(root: Path, claim_id: str, status: str) -> pages.Page:
    """Move a claim to a new status, recomputing independent_corroboration and
    refreshing the `sources` entries + footnote attribution against current
    source slugs.

    "verified" is gated by the notebook profile's verification bar: at least
    `claim_min_independent` sources with independence == "original", or — when
    `claim_grade_a_suffices` — any listed source graded A. Only judged sources
    count. Refusal writes nothing. Returns the updated page.
    """
    root = util.require_notebook_root(root)
    if status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    page = _find_claim(root, claim_id)
    cited = source_ids(page.fm)
    src_by_id = _source_pages_by_id(root)
    source_fms = [p.fm for p in src_by_id.values()]
    corroboration = corroboration_count(source_fms, cited)
    if status == "verified":
        profile = profiles.load_profile(manifest.load_manifest(root).kind, root)
        linked = _linked_fms(source_fms, cited)
        has_grade_a = any(fm.get("grade") == "A" for fm in linked)
        bar_met = corroboration >= profile.claim_min_independent or (
            profile.claim_grade_a_suffices and has_grade_a
        )
        # A2: the gate passes on the corroboration bar OR a recorded adversarial/
        # recomputation verification — the two paths the refusal names.
        if not (bar_met or has_gating_verification(page.fm)):
            msg = (
                f"cannot verify {claim_id}: {corroboration} independent original source(s) "
                f"of {profile.claim_min_independent} required"
            )
            if profile.claim_grade_a_suffices:
                msg += " and no grade-A source among its sources"
            msg += (
                f" (sources: {', '.join(cited) or 'none'}); add independent original "
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
            msg += (
                f"; or record a skeptic/recompute pass with `flip claim verify {claim_id} "
                "--method adversarial|recomputation`"
            )
            raise SystemExit(msg)
    entries, defs = _attribution(src_by_id, cited)
    page.fm["status"] = status
    page.fm["independent_corroboration"] = corroboration
    page.fm["sources"] = entries
    page.fm.pop("supports", None)  # pre-0.7 key; the entries carry the paths now
    body = _apply_attribution(page.body, cited, defs)
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def _write_sources(root: Path, page: pages.Page, cited: list[str]) -> pages.Page:
    """Persist a claim's new cited-source list: regenerate the OKF `sources`
    entries + footnote attribution against current source slugs and recompute
    independent_corroboration. The prose round-trips (SPEC §6.6)."""
    ids = [str(s) for s in cited]
    src_by_id = _source_pages_by_id(root)
    entries, defs = _attribution(src_by_id, ids)
    page.fm["sources"] = entries
    page.fm.pop("supports", None)
    page.fm["independent_corroboration"] = corroboration_count(
        [p.fm for p in src_by_id.values()], ids
    )
    body = _apply_attribution(page.body, ids, defs)
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def add_claim_sources(
    root: Path, claim_id: str, new_ids: list[str]
) -> tuple[pages.Page, list[str], list[str]]:
    """Link one or more source ids to a claim (A1): append to `sources:`,
    regenerate the footnote attribution, recompute corroboration.

    Unknown ids — no references/ page carries them — are refused before any
    write; this is the post-hoc linker, not a place to invent dangling cites.
    Returns (page, newly-added ids, warnings) where warnings name any linked
    source still graded "?" (ungraded sources never count toward the bar,
    D12/§5.4). Refuses when every given id is already linked.
    """
    root = util.require_notebook_root(root)
    ids = [str(s) for s in pages.as_list(new_ids)]
    if not ids:
        raise SystemExit("no source ids given; pass at least one references/ id, e.g. A3")
    page = _find_claim(root, claim_id)
    src_by_id = _source_pages_by_id(root)
    unknown = [s for s in dict.fromkeys(ids) if s not in src_by_id]
    if unknown:
        known = ", ".join(sorted(src_by_id)) or "none captured yet"
        raise SystemExit(
            f"unknown source id(s) {', '.join(unknown)}: no references/ page carries them "
            f"(known: {known}); capture the source with `flip add-source` first"
        )
    current = source_ids(page.fm)
    added = [s for s in dict.fromkeys(ids) if s not in current]
    if not added:
        raise SystemExit(
            f"claim {claim_id} already cites {', '.join(dict.fromkeys(ids))}; nothing to add"
        )
    updated = _write_sources(root, page, current + added)
    warnings = [s for s in added if src_by_id[s].fm.get("grade") not in JUDGED_GRADES]
    return updated, added, warnings


def remove_claim_source(root: Path, claim_id: str, source_id: str) -> pages.Page:
    """Unlink a source id from a claim (A1): drop it from `sources:`, regenerate
    the footnote attribution, recompute corroboration. Refuses when the claim
    does not cite that id."""
    root = util.require_notebook_root(root)
    sid = str(source_id)
    page = _find_claim(root, claim_id)
    current = source_ids(page.fm)
    if sid not in current:
        raise SystemExit(
            f"claim {claim_id} does not cite {sid} (sources: {', '.join(current) or 'none'})"
        )
    return _write_sources(root, page, [s for s in current if s != sid])


def verify_claim(
    root: Path,
    claim_id: str,
    method: str,
    against: list[str] | None = None,
    note: str | None = None,
) -> pages.Page:
    """Record a verification on a claim (A2): append a {by, at, method,
    against, note} event to the `verified:` frontmatter list — OKF v0.2 §5.2
    verification events (by/at drive consumer trust tiers), with flip's
    method/against/note riding along as extension keys. Append-only — records
    are added, never edited — and never touches sources or corroboration.

    `adversarial` and `recomputation` clear the `verified` gate on their own
    (see set_claim_status); `independent-sources` records the corroboration
    reasoning but never substitutes for the recomputed source count.
    """
    root = util.require_notebook_root(root)
    if method not in VERIFICATION_METHODS:
        raise SystemExit(
            f"invalid verification method '{method}' "
            f"(one of: {', '.join(VERIFICATION_METHODS)})"
        )
    page = _find_claim(root, claim_id)
    record: dict = {"by": util.detect_actor(), "at": util.utc_now(), "method": method}
    refs = [str(a) for a in pages.as_list(against)]
    if refs:
        record["against"] = refs
    if note:
        record["note"] = note
    records = pages.as_list(page.fm.get("verified"))
    records.append(record)
    page.fm["verified"] = records
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


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
