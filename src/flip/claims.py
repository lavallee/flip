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
A/B/C, never "?" — with independence == "independent" (SPEC §5.4: ungraded
sources never corroborate; capture is custody, not judgment). It is
recomputed on every status change so the number tracks the pages as gradings
evolve. `corroboration_count` is the one shared implementation; doctor's
under-verified check uses it too.

`uncountable_sources` is its companion, and every surface that shows the
count must show it too: a cited source carrying pre-0.8 `independence`
vocabulary can be counted neither for nor against, and reporting it as a
plain 0 reads as "the evidence is thin" when the truth is "flip cannot read
this judgment". A wrong number is worse than a missing one — only the missing
one prompts a look.

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

from . import manifest, pages, profiles, transcripts, util
from . import sources as sources_mod

STATUSES = (
    "asserted",
    "verified",
    "needs-2nd",
    "unconfirmed",
    "false-positive",
    "retracted",
    "superseded",
)

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
    are tolerated as ids. The one accessor every reader goes through.

    Ids are always BASE ids — an entry pinning transcript passages carries
    them in its own `excerpts` key, so corroboration, grading and every
    downstream consumer keep counting sources rather than citations. Use
    `source_refs` when the passage matters.
    """
    out: list[str] = []
    for entry in pages.as_list(fm.get("sources")):
        sid = str(entry.get("id", "")) if isinstance(entry, dict) else str(entry)
        if sid.strip():
            out.append(sid.strip())
    return out


def source_refs(fm: dict) -> list[str]:
    """A claim's citations as refs, in order — `T1§relevance-null` where a
    transcript passage was pinned, a bare id everywhere else.

    The counterpart to `source_ids`: that answers "which sources does this
    rest on", this answers "which words". A source cited with two pinned
    passages yields two refs and one id.
    """
    out: list[str] = []
    for entry in pages.as_list(fm.get("sources")):
        if not isinstance(entry, dict):
            sid = str(entry).strip()
            if sid:
                out.append(sid)
            continue
        sid = str(entry.get("id", "")).strip()
        if not sid:
            continue
        labels = [str(x) for x in pages.as_list(entry.get("excerpts")) if str(x).strip()]
        if labels:
            out.extend(util.format_excerpt_ref(sid, label) for label in labels)
        else:
            out.append(sid)
    return out


def _linked_fms(source_fms: list[dict], source_ids: list[str]) -> list[dict]:
    """Frontmatter dicts matching the given source ids, deduped; unknown ids
    contribute nothing (dangling citations are legal — doctor counts them)."""
    by_id = {str(fm.get("id")): fm for fm in source_fms}
    return [by_id[s] for s in dict.fromkeys(str(s) for s in source_ids) if s in by_id]


def corroboration_count(source_fms: list[dict], source_ids: list[str]) -> int:
    """Independent corroboration for a claim, per SPEC §5.4/§7 (design D-A).

    Counts the claim's source ids (deduped — listing a source twice never
    counts twice) whose references/ page is judged (support tuple recorded,
    or a migration seed — an unjudged capture counts toward nothing) AND
    independence == "independent". `corroborated`/`self-reported`/
    `derivative` never satisfy the bar. Shared by add_claim/set_claim_status
    and doctor's under-verified check.
    """
    return sum(
        1
        for fm in _linked_fms(source_fms, source_ids)
        if sources_mod.judged(fm) and fm.get("independence") == "independent"
    )


def uncountable_sources(source_fms: list[dict], source_ids: list[str]) -> list[str]:
    """The claim's cited source ids that cannot be counted either way, in
    order: pages still carrying pre-0.8 `independence` vocabulary.

    `corroboration_count` returns a number; this returns the reason that
    number may understate the evidence. Report them together — an unmigrated
    source silently dropping out of the count is how four claims failed the
    `verified` gate for a reason that had nothing to do with their evidence.
    """
    return [
        str(fm.get("id"))
        for fm in _linked_fms(source_fms, source_ids)
        if sources_mod.unmigrated(fm)
    ]


def has_gating_verification(fm: dict) -> bool:
    """True when a claim's `verified:` list (OKF v0.2 §5.2 events, each
    {by, at} plus flip's `method` extension key) records at least one whose
    method clears the `verified` gate on its own (adversarial/recomputation).
    Shared by set_claim_status's gate and doctor's under-verified check."""
    return any(
        isinstance(v, dict) and str(v.get("method")) in GATING_VERIFICATION_METHODS
        for v in pages.as_list(fm.get("verified"))
    )


def refuse_belief_citations(root: Path, cited_ids: list[str]) -> None:
    """Refuse any cited id that resolves to a beliefs/ page (SPEC §7.1).

    A belief is a claim about *believers*: "38% of X hold P" is measurable and
    checkable, and its truth is entirely independent of P's. Citing the belief
    as evidence for P is the category error in the direction that does damage
    — a true fact about believing quietly becoming a claim about the world.
    Every other guard against it runs late (doctor's `belief-as-evidence`);
    this one runs before anything is written, so nothing has to be un-done.

    Dangling citations stay legal (SPEC §6.1): an id no page carries is a
    counted dangling cite, not a refusal. Only an id flip can *see* is a
    belief is refused, because only then does it know the mistake was made.
    """
    from . import beliefs as beliefs_mod

    held = beliefs_mod.belief_ids(root)
    offenders = [s for s in dict.fromkeys(cited_ids) if s in held]
    if not offenders:
        return
    listed = ", ".join(offenders)
    is_are = "is a belief" if len(offenders) == 1 else "are beliefs"
    raise SystemExit(
        f"cannot cite {listed} as a source: that {is_are} (beliefs/), and a belief is "
        "evidence about BELIEVERS, never about what they believe. Counting one toward "
        'a claim is how "many people think X" becomes "X". Cite the survey the '
        "measurement rests on if the measurement is what you want; to link the two "
        f"records instead, run `flip belief about {offenders[0]} <C#>` — the belief "
        "points at the claim and corroborates nothing"
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


def _group_refs(cited: list[str]) -> dict[str, list[str]]:
    """Citation refs grouped base-id → pinned excerpt labels, both deduped and
    in first-seen order. `["T1§a", "A2", "T1§b"]` → `{"T1": ["a","b"], "A2": []}`.

    Grouping is what keeps one source one source: a claim resting on two
    passages of the same conversation has two citations and one piece of
    evidence, and only the second number may reach corroboration.
    """
    grouped: dict[str, list[str]] = {}
    for ref in cited:
        base, label = util.split_ref(str(ref))
        labels = grouped.setdefault(base, [])
        if label and label not in labels:
            labels.append(label)
    return grouped


def _attribution(
    src_by_id: dict[str, pages.Page], cited: list[str]
) -> tuple[list[dict], list[str]]:
    """(OKF `sources` entries, footnote-definition lines) for a claim's cited
    refs, deduped, in order.

    Resolvable ids get a followable bundle-absolute `resource`, the page
    title, and a relative-linked definition; dangling ids keep just the id
    and a plain-text definition — dangling is legal (SPEC §6.1), doctor
    counts them.

    A ref pinning a transcript passage (`T1§relevance-null`) contributes its
    label to the entry's `excerpts` list and deep-links `resource` at the
    passage anchor. Footnote labels stay base-id-shaped (`[^T1]`) whatever is
    pinned: they are markdown labels, and one source keeps one marker.
    """
    entries: list[dict] = []
    defs: list[str] = []
    for sid, labels in _group_refs(cited).items():
        page = src_by_id.get(sid)
        entry: dict = {"id": sid}
        if labels:
            entry["excerpts"] = list(labels)
        if page is None:
            defs.append(f"[^{sid}]: {sid} (not captured)")
        else:
            anchor = f"#{transcripts.anchor_for(labels[0])}" if len(labels) == 1 else ""
            entry["resource"] = f"/references/{page.slug}.md{anchor}"
            title = str(page.fm.get("title") or "")
            if title:
                entry["title"] = title
            link = f"[{title or sid}](../references/{page.slug}.md{anchor})"
            passages = f" — {', '.join(labels)}" if labels else ""
            defs.append(f"[^{sid}]: {link}{passages}")
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
    head += "".join(f"[^{sid}]" for sid in _group_refs([str(s) for s in cited]))
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
    value: str | None = None,
    unit: str | None = None,
) -> pages.Page:
    """Add a claim page with status "asserted", allocating the next C#.

    A quantitative claim's number travels as data (`value`/`unit`), not only
    as prose — the format's own export can't fix a free-text number
    downstream. `value` stays a string (a range or "~42" is a legal value).
    """
    root = util.require_notebook_root(root)
    text = (text or "").strip()
    if not text:
        raise SystemExit("empty claim text; state the assertion in one sentence")
    cited = [str(s) for s in pages.as_list(sources)]
    cited_ids = list(_group_refs(cited))  # excerpt refs collapse to their source
    refuse_belief_citations(root, cited_ids)
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
            [p.fm for p in src_by_id.values()], cited_ids
        ),
        "first_asserted": util.today(),
        "generated": util.generated_now(),
    }
    if value is not None:
        fm["value"] = str(value)
        if unit:
            fm["unit"] = str(unit)
    elif unit:
        raise SystemExit("--unit given without --value; pass both or neither")
    if notes:
        fm["notes"] = notes

    markers = "".join(f"[^{sid}]" for sid in cited_ids)
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
    `claim_min_independent` sources with independence == "independent", or —
    when `claim_grade_a_suffices` — any listed source graded A. Only judged
    sources count, and a refusal names any cited source flip could not count
    at all (pre-0.8 vocabulary) so the number is never read as an evidence
    verdict. Refusal writes nothing. Returns the updated page.
    """
    root = util.require_notebook_root(root)
    if status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    page = _find_claim(root, claim_id)
    # Refs drive regeneration (they carry the pinned passages); ids drive the
    # evidence bar. Regenerating from ids alone silently unpinned every
    # excerpt the moment a claim changed status.
    cited_refs = source_refs(page.fm)
    cited = source_ids(page.fm)
    src_by_id = _source_pages_by_id(root)
    source_fms = [p.fm for p in src_by_id.values()]
    corroboration = corroboration_count(source_fms, cited)
    if status == "verified":
        profile = profiles.load_profile(manifest.load_manifest(root).kind, root)
        linked = _linked_fms(source_fms, cited)
        has_grade_a = any(sources_mod.derive_grade(fm) == "A" for fm in linked)
        bar_met = corroboration >= profile.claim_min_independent or (
            profile.claim_grade_a_suffices and has_grade_a
        )
        # A2: the gate passes on the corroboration bar OR a recorded adversarial/
        # recomputation verification — the two paths the refusal names.
        if not (bar_met or has_gating_verification(page.fm)):
            msg = (
                f"cannot verify {claim_id}: {corroboration} independent source(s) "
                f"of {profile.claim_min_independent} required"
            )
            if profile.claim_grade_a_suffices:
                msg += " and no grade-A source among its sources"
            msg += (
                f" (sources: {', '.join(cited) or 'none'}); add sources whose "
                "independence is 'independent' to the claim"
            )
            if profile.claim_grade_a_suffices:
                msg += " or upgrade one to grade A via `flip grade`"
            # Lead with the cause when there is one: an uncountable source is a
            # vocabulary problem wearing an evidence problem's clothes, and the
            # count above understates the evidence rather than measuring it.
            stale = uncountable_sources(source_fms, cited)
            if stale:
                msg += (
                    f"; {', '.join(stale)} {'carries' if len(stale) == 1 else 'carry'} "
                    "pre-0.8 independence vocabulary and cannot be counted either way "
                    "— that count is not a verdict on the evidence; run `flip migrate`, "
                    "then re-judge with `flip grade`"
                )
            ungraded = [
                str(fm.get("id"))
                for fm in linked
                if not sources_mod.judged(fm) and not sources_mod.unmigrated(fm)
            ]
            if ungraded:
                msg += (
                    f"; {', '.join(ungraded)} still unjudged and unjudged sources "
                    "never corroborate — judge them with `flip grade` first"
                )
            msg += (
                f"; or record a skeptic/recompute pass with `flip claim verify {claim_id} "
                "--method adversarial|recomputation`"
            )
            raise SystemExit(msg)
    entries, defs = _attribution(src_by_id, cited_refs)
    page.fm["status"] = status
    page.fm["independent_corroboration"] = corroboration
    page.fm["sources"] = entries
    page.fm.pop("supports", None)  # pre-0.7 key; the entries carry the paths now
    body = _apply_attribution(page.body, cited_refs, defs)
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def _write_sources(root: Path, page: pages.Page, cited: list[str]) -> pages.Page:
    """Persist a claim's new citation list: regenerate the OKF `sources`
    entries + footnote attribution against current source slugs and recompute
    independent_corroboration. Takes refs (`T1§label` or bare ids); the
    evidence bar counts the base ids behind them. The prose round-trips
    (SPEC §6.6)."""
    refs = [str(s) for s in cited]
    src_by_id = _source_pages_by_id(root)
    entries, defs = _attribution(src_by_id, refs)
    page.fm["sources"] = entries
    page.fm.pop("supports", None)
    page.fm["independent_corroboration"] = corroboration_count(
        [p.fm for p in src_by_id.values()], list(_group_refs(refs))
    )
    body = _apply_attribution(page.body, refs, defs)
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
    Returns (page, newly-added ids, warnings), where warnings are
    `(source_id, reason)` pairs for any linked source that won't count toward
    the bar: `"unjudged"` (graded "?" — capture is custody, not judgment,
    D12/§5.4) or `"unmigrated"` (pre-0.8 `independence` vocabulary, which
    needs re-reading rather than first-time judging — a different fix, so a
    different word). Refuses when every given id is already linked.
    """
    root = util.require_notebook_root(root)
    refs = [str(s) for s in pages.as_list(new_ids)]
    if not refs:
        raise SystemExit("no source ids given; pass at least one references/ id, e.g. A3")
    page = _find_claim(root, claim_id)
    src_by_id = _source_pages_by_id(root)
    grouped = _group_refs(refs)
    # Beliefs first: "unknown source id" would be true and useless here — the
    # id resolves perfectly, to a page that must never count as evidence.
    refuse_belief_citations(root, list(grouped))
    unknown = [s for s in grouped if s not in src_by_id]
    if unknown:
        known = ", ".join(sorted(src_by_id)) or "none captured yet"
        raise SystemExit(
            f"unknown source id(s) {', '.join(unknown)}: no references/ page carries them "
            f"(known: {known}); capture the source with `flip add-source` first"
        )
    # An unpinned label is refused here for the same reason an unknown id is:
    # this is the post-hoc linker, and a ref that resolves to nothing would
    # read as a passage citation while resting on the whole conversation.
    for sid, labels in grouped.items():
        for label in labels:
            if transcripts.find_excerpt(root, sid, label) is None:
                pinned = ", ".join(
                    str(e.get("label")) for e in pages.as_list(src_by_id[sid].fm.get("excerpts"))
                    if isinstance(e, dict)
                ) or "none pinned"
                raise SystemExit(
                    f"{sid} pins no excerpt '{label}' (pinned: {pinned}); "
                    f"pin it with `flip transcript excerpt {sid} --label {label} --lines A-B`"
                )
    current = source_refs(page.fm)
    added = [s for s in dict.fromkeys(refs) if s not in current]
    if not added:
        raise SystemExit(
            f"claim {claim_id} already cites {', '.join(dict.fromkeys(refs))}; nothing to add"
        )
    updated = _write_sources(root, page, current + added)
    warnings = [
        (ref, "unmigrated" if sources_mod.unmigrated(src_by_id[base].fm) else "unjudged")
        for ref in added
        for base in [util.split_ref(ref)[0]]
        if not sources_mod.judged(src_by_id[base].fm)
    ]
    return updated, added, warnings


def remove_claim_source(root: Path, claim_id: str, source_id: str) -> pages.Page:
    """Unlink a citation from a claim (A1): drop it from `sources:`, regenerate
    the footnote attribution, recompute corroboration.

    Takes a ref or a bare id, and the two mean different things on a source
    cited by passage: `T1§relevance-null` drops that one pin and leaves the
    claim's other passages standing, while `T1` drops the source and every
    passage of it at once. Refuses when the claim cites neither.
    """
    root = util.require_notebook_root(root)
    ref = str(source_id)
    base, label = util.split_ref(ref)
    page = _find_claim(root, claim_id)
    current = source_refs(page.fm)
    if label:
        keep = [s for s in current if s != ref]
    else:
        keep = [s for s in current if util.split_ref(s)[0] != base]
    if len(keep) == len(current):
        raise SystemExit(
            f"claim {claim_id} does not cite {ref} (cites: {', '.join(current) or 'none'})"
        )
    return _write_sources(root, page, keep)


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
