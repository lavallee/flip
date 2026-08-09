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

`status` says what is KNOWN about a claim. Two orthogonal axes say what has
been asked of it and what the notebook does with it, and both live in
`stance` (SPEC §7.1): the authored, append-only `stances:` and `tests:`
lists, and the derived `exposure` computed off the second. The write paths
are here (`set_stance`, `record_test`) because they need the claim lookup and
the view regeneration; the vocabulary and every derivation are there, so
nothing that only wants to READ an exposure has to import this module.

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

from . import manifest, pages, profiles, stance, transcripts, util
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


def _refuse_verified_against_tests(claim_id: str, fm: dict) -> None:
    """Refuse `verified` on a claim a severe test found wrong (SPEC §7.1).

    The corroboration bar counts sources; it has no way to notice that
    somebody went looking for the error and found it. A claim can clear the
    count and still be misattributed — that is precisely the shape of the
    failure this axis exists for, since a plausible citation is what makes a
    source *countable* in the first place.

    Tests can only ever CLOSE this gate, never open it: a test record is
    authored by the same hand that authored the claim, and letting a described
    test satisfy the bar would let a notebook verify itself by writing a
    sentence. Blocking is safe in a way that opening is not.
    """
    exposure = stance.derive_exposure(fm)
    if exposure not in stance.REFUTING_EXPOSURES:
        return
    failed = [
        r for r in stance.test_records(fm)
        if str(r.get("result")) == "failed" and stance.test_severity(r) == "severe"
    ]
    probes = ", ".join(dict.fromkeys(str(r.get("probe")) for r in failed))
    errors = "; ".join(str(r.get("error") or "").strip() for r in failed if r.get("error"))
    msg = (
        f"cannot verify {claim_id}: its exposure is '{exposure}' — a severe {probes} test "
        "went looking for the error and found it, and no count of independent sources "
        "outvotes that"
    )
    if errors:
        msg += f" (the error found: {errors})"
    if exposure == "misattributed":
        cited = stance.failed_attribution_sources(fm)
        msg += (
            f"; this is a citation failure, not a verdict on whether the claim is true — "
            f"restate it in {', '.join(cited) or 'the source'}'s own words, or "
            f"`flip claim source rm {claim_id} {cited[0] if cited else '<id>'}` and assert "
            "the claim the source does support"
        )
    else:
        msg += (
            f"; name the claim that survives what this one failed and concede to it "
            f"(`flip claim supersede {claim_id} --by <C#>`), or set status needs-2nd and "
            f"say what the notebook still does with it (`flip claim stance {claim_id} "
            "pursuing --because … --falsifier …`)"
        )
    msg += f". `flip claim exposure {claim_id}` shows the derivation"
    raise SystemExit(msg)


def _refuse_superseded_without_a_successor(claim_id: str, fm: dict) -> None:
    """Refuse `status: superseded` on a claim that does not say what superseded
    it (SPEC §7.1).

    Lakatos, p.69: "a degenerating problemshift is no more a sufficient reason
    to eliminate a research programme than some old-fashioned 'refutation' or a
    Kuhnian 'crisis'… such an objective reason is provided by a rival research
    programme which explains the previous success of its rival and supersedes
    it by a further display of heuristic power." Letting go is comparative. A
    bare `superseded` is the non-comparative move wearing the comparative
    word's clothes: it records that the notebook got tired of a claim, and
    getting tired is exactly what he says is not a reason.

    The practical half is just as strong. A tombstone with no forwarding
    address makes the next reader re-derive the successor from scratch, and
    the successor is the only part of the episode worth keeping.
    """
    if stance.superseded_by(fm):
        return
    raise SystemExit(
        f"cannot set {claim_id} to 'superseded' directly: superseding is comparative, and "
        "this would record only that the notebook let go, not what it let go TO. Use "
        f"`flip claim supersede {claim_id} --by <C#> --because \"<what both claims answer, "
        "and why the successor wins>\"`, which sets the status, writes the pointer and "
        "registers the two as rivals in one move. If nothing has replaced it, the honest "
        f"statuses are 'retracted' (the notebook withdraws it) or 'unconfirmed'; and if it "
        f"is wrong but still worth keeping, `flip claim stance {claim_id} rejecting "
        "--because … --falsifier …` keeps it as data"
    )


def set_claim_status(root: Path, claim_id: str, status: str) -> pages.Page:
    """Move a claim to a new status, recomputing independent_corroboration and
    refreshing the `sources` entries + footnote attribution against current
    source slugs.

    Two statuses are gated by the attitude axis (SPEC §7.1). `superseded` is
    refused unless the page already names its successor, because letting go is
    comparative (Lakatos p.69) — `flip claim supersede` is the way in.

    "verified" is gated twice. First by the claim's own test record: a claim
    whose exposure is `misattributed` or `refuted` is refused
    before the count is even taken, because a severe test that found the error
    is a stronger fact than any number of sources agreeing. Then by the
    notebook profile's verification bar: at least `claim_min_independent`
    sources with independence == "independent", or — when
    `claim_grade_a_suffices` — any listed source graded A. Only judged sources
    count, and a refusal names any cited source flip could not count at all
    (pre-0.8 vocabulary) so the number is never read as an evidence verdict.
    Refusal writes nothing. Returns the updated page.
    """
    root = util.require_notebook_root(root)
    if status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    page = _find_claim(root, claim_id)
    if status == "verified":
        _refuse_verified_against_tests(claim_id, page.fm)
    if status == "superseded":
        _refuse_superseded_without_a_successor(claim_id, page.fm)
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


def set_stance(
    root: Path,
    claim_id: str,
    stance_value: str,
    because: str,
    holder: str = stance.NOTEBOOK_HOLDER,
    falsifier: str | None = None,
    sources: list[str] | None = None,
) -> tuple[pages.Page, list[str]]:
    """Record a stance on a claim (SPEC §7.1): append a {stance, holder,
    because, falsifier?, sources?, at, by} record to the `stances:` list.

    Append-only, like `verified:` — a stance is an act with a date and an
    actor, and the fact that the notebook used to think otherwise is usually
    the most interesting thing on the page.

    `because` is always required: a stance without its reasoning is an enum
    without evidence, which is the error `pipeline` already learned. A
    `falsifier` is required for `pursuing` and `rejecting` — the two stances
    that run ahead of, or against, the evidence.

    That requirement is Peirce's verifiability condition and NOT, as an earlier
    draft of this design claimed, his economy of research. Economy cannot gate
    anything: CP 1.136, immediately after "Do not block the way of inquiry",
    says "there is no positive sin against logic in trying any theory which may
    come into our heads", and CP 7.220 makes cheapness a reason to give a
    hypothesis *precedence*, not a bar to clear. What does gate is CP 5.197 —
    a hypothesis is admissible "provided it be capable of experimental
    verification, and only insofar as it is capable of such verification" — and
    what it asks for is sharper than "what would move you": CP 2.89 wants the
    predictions "otherwise least likely to be true", CP 1.120 that "the best
    hypothesis… is the one which can be the most readily refuted if it is
    false." flip cannot check that a falsifier is any of that; it can refuse
    the stance until one is written, and it can ask for the right thing in the
    flag help and in the refusal.

    `holder` defaults to the reserved value `notebook` — the notebook's own
    position. Any other holder records that SOMEONE ELSE takes this position,
    which is how a belief the notebook rejects gets kept as data rather than
    argued with. Returns (page, warnings), where warnings name foreign holders
    with nothing cited to show they hold it: "people believe X" is an
    assertion about people and deserves a source like any other.
    """
    root = util.require_notebook_root(root)
    if stance_value not in stance.STANCES:
        raise SystemExit(
            f"invalid stance '{stance_value}' (one of: {', '.join(stance.STANCES)}); "
            "the stance says what is DONE with the claim — `status` still says what is "
            "known about it, and the two are deliberately independent"
        )
    because = (because or "").strip()
    if not because:
        raise SystemExit(
            f"a stance needs --because: '{stance_value}' on its own is an enum without "
            "evidence, and the next reader (usually you) needs the reasoning that made "
            "it the right position, not just the word"
        )
    holder = (holder or stance.NOTEBOOK_HOLDER).strip()
    if not holder:
        raise SystemExit(
            "empty --holder; name who takes this position, or omit the flag for the "
            f"notebook's own stance (the reserved holder '{stance.NOTEBOOK_HOLDER}')"
        )
    falsifier = (falsifier or "").strip()
    if stance_value in stance.PRICED_STANCES and not falsifier:
        raise SystemExit(
            f"'{stance_value}' needs --falsifier: it is a position taken ahead of, or "
            "against, the evidence, and a hypothesis is admissible only insofar as it is "
            "capable of experimental verification (Peirce, CP 5.197). Do not write down "
            "the vaguest thing that would unsettle you — write the observation this "
            "position predicts that would be LEAST likely to come out that way if the "
            "position were wrong (CP 2.89), because that is the only kind whose failure "
            f"decides anything. Then run it: `flip claim test {claim_id} …`, and the "
            "exposure will say what it found. (`holding` and `abstaining` need no "
            "falsifier: they track the evidence, so the evidence is already their exit.)"
        )
    page = _find_claim(root, claim_id)
    record: dict = {
        "stance": stance_value,
        "holder": holder,
        "because": because,
    }
    if falsifier:
        record["falsifier"] = falsifier
    refs = [str(s).strip() for s in pages.as_list(sources) if str(s).strip()]
    if refs:
        record["sources"] = refs
    record["at"] = util.utc_now()
    record["by"] = util.detect_actor()
    records = pages.as_list(page.fm.get("stances"))
    records.append(record)
    page.fm["stances"] = records
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    updated = pages.Page(path=page.path, fm=page.fm, body=page.body)
    return updated, stance.unsourced_holders(page.fm)


def record_test(
    root: Path,
    claim_id: str,
    probe: str,
    error: str,
    result: str,
    would_detect: str | None = None,
    if_absent: str | None = None,
    against: list[str] | None = None,
    note: str | None = None,
) -> pages.Page:
    """Record a test against a claim (SPEC §7.1): append a {probe, error,
    would_detect?, if_absent?, result, against?, note?, at, by} record to
    `tests:`.

    This is the axis `verified:` cannot carry. `verified:` is OKF v0.2 §5.2's
    key and OKF defines its entries as *verification* events — a test that
    found the error is not a verification, and writing one there would make
    every OKF consumer read a refutation as a confirmation. So failures live
    in flip's own `tests:` list, append-only, and the two keys stay honest.

    `probe` names WHICH error class was looked for, and that is the whole
    reason the axis exists: an attribution failure ("the paper does not say
    this") and a substance failure ("the world is not like this") are
    different findings with different repairs, and a notebook that renders
    them identically will read one as the other.

    `error`, `would_detect`, `if_absent` and `against` are what make a test
    severe — see `stance.severity_gaps` for which sentence of Mayo's each one
    is. Only `error` is required at the write path, because a bent test
    honestly recorded is worth more than no record and because refusing the
    write would just get the fields filled in with noise. The other three are
    what a survival needs before it means anything, and `flip claim exposure`
    names every one that is missing, on every test that is missing it.

    `if_absent` is the field an earlier draft of this design did not have, and
    its absence was a real hole: severity's capability condition is "a very
    high capability of signaling the error, **if and only if** it is present"
    (SIST p.16), and a probe with no answer to "what would this have shown had
    the error not been there?" may well be one that fires either way — which
    discriminates nothing, however carefully it was run.
    """
    root = util.require_notebook_root(root)
    if probe not in stance.TEST_PROBES:
        raise SystemExit(
            f"invalid probe '{probe}' (one of: {', '.join(stance.TEST_PROBES)}); the probe "
            "names the class of error the test went looking for, and failing one says "
            "nothing about the others"
        )
    if result not in stance.TEST_RESULTS:
        raise SystemExit(
            f"invalid test result '{result}' (one of: {', '.join(stance.TEST_RESULTS)})"
        )
    error = (error or "").strip()
    if not error:
        raise SystemExit(
            "a test needs --error naming what it went looking for. A test with no stated "
            "error is not a test — it is a reading, and it cannot be severe, because "
            "severity is always severity FOR a particular way of being wrong"
        )
    page = _find_claim(root, claim_id)
    record: dict = {"probe": probe, "error": error}
    detect = (would_detect or "").strip()
    if detect:
        record["would_detect"] = detect
    absent = (if_absent or "").strip()
    if absent:
        record["if_absent"] = absent
    record["result"] = result
    refs = [str(a).strip() for a in pages.as_list(against) if str(a).strip()]
    if refs:
        record["against"] = refs
    if note:
        record["note"] = note
    record["at"] = util.utc_now()
    record["by"] = util.detect_actor()
    records = pages.as_list(page.fm.get("tests"))
    records.append(record)
    page.fm["tests"] = records
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


def _append_rival(page: pages.Page, other_id: str, because: str) -> bool:
    """Add `other_id` to one page's `rivals:` list unless it is already there.
    Returns whether anything changed. Caller writes the page."""
    if other_id in stance.rival_ids(page.fm):
        return False
    records = pages.as_list(page.fm.get("rivals"))
    records.append(
        {
            "claim": other_id,
            "because": because,
            "at": util.utc_now(),
            "by": util.detect_actor(),
        }
    )
    page.fm["rivals"] = records
    return True


def declare_rivals(root: Path, claim_id: str, other_id: str, because: str) -> list[pages.Page]:
    """Declare two claims rivals — they answer the same question (SPEC §7.1).

    This is the unit of comparison the design otherwise lacks. A stance sits on
    one claim, so "C7 is doing worse than C12" means nothing until something
    says the two are answering the same question, and no tool can infer that:
    two claims can share every source and answer different questions, or share
    none and answer the same one. So it is authored, and `because` carries the
    question in the operator's words.

    Written to BOTH pages. A comparison only one side can see is not a
    comparison — and the practical failure of a one-way link is that the
    incumbent claim, which is the page anyone worried about the incumbent
    opens, is the one that stays silent about its challenger.

    Lakatos, p.69, is the reason this exists at all: an objective reason to let
    go of a programme "is provided by a rival research programme which explains
    the previous success of its rival and supersedes it by a further display of
    heuristic power." Elimination is comparative. flip cannot check the
    "explains the previous success" half — that is a judgment about content —
    so doctor reports the comparison and never makes the call.
    """
    root = util.require_notebook_root(root)
    because = (because or "").strip()
    if not because:
        raise SystemExit(
            "declaring two claims rivals needs --because naming the question they both "
            "answer. Without it the link is unreadable six months later and unfalsifiable "
            "now: two claims can share every source and answer different questions, so "
            "flip cannot work the question out and will not guess at it"
        )
    if claim_id == other_id:
        raise SystemExit(
            f"{claim_id} cannot be its own rival; name the other claim that answers the "
            "same question (`flip claim list` to find it, `flip claim add` if it does not "
            "exist yet — an unwritten alternative is the one that never wins)"
        )
    page = _find_claim(root, claim_id)
    other = _find_claim(root, other_id)
    changed = [p for p in (page, other) if _append_rival(
        p, other_id if p is page else claim_id, because)]
    if not changed:
        raise SystemExit(
            f"{claim_id} and {other_id} are already declared rivals; `flip claim exposure "
            f"{claim_id}` shows how the two compare on the evidence"
        )
    for p in changed:
        pages.write_page(p.path, p.fm, p.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return [pages.Page(path=p.path, fm=p.fm, body=p.body) for p in (page, other)]


def supersede_claim(
    root: Path, claim_id: str, successor_id: str, because: str
) -> tuple[pages.Page, str]:
    """Concede a claim to its successor: write `superseded_by`, register the
    two as rivals, and set `status: superseded` (SPEC §7.1).

    The only route to `superseded`, because Lakatos's elimination criterion is
    comparative (p.69) and a bare status change is the non-comparative move
    wearing the comparative word. You do not let go because a claim has been
    embarrassing for long enough; you let go when you can name what beats it.

    Returns (page, note) where `note` is a warning about the comparison when
    there is one to make — most usefully when the successor is no better tested
    than the claim it is replacing, which is a swap rather than a supersession
    and is worth seeing before it is written rather than after. It is a note
    and not a refusal: Lakatos's criterion also requires that the successor
    explain the predecessor's successes, which flip has no access to, so the
    operator may perfectly well know something the exposure comparison does
    not.
    """
    root = util.require_notebook_root(root)
    if claim_id == successor_id:
        raise SystemExit(f"{claim_id} cannot supersede itself")
    page = _find_claim(root, claim_id)
    successor = _find_claim(root, successor_id)
    because = (because or "").strip()
    if not because:
        raise SystemExit(
            f"superseding needs --because saying what {claim_id} and {successor_id} both "
            "answer and why the successor wins. That sentence is the whole content of the "
            "move — the status change is just bookkeeping — and it is what tells the next "
            "reader whether to trust the swap or reopen it"
        )
    old = stance.superseded_by(page.fm)
    if old and old != successor_id:
        raise SystemExit(
            f"{claim_id} already records {old} as its successor. Superseding twice would "
            f"lose the chain; supersede {old} with {successor_id} instead, so the notebook "
            "keeps the order the positions were let go of in"
        )
    _append_rival(page, successor_id, because)
    if _append_rival(successor, claim_id, because):
        pages.write_page(successor.path, successor.fm, successor.body)
    page.fm["superseded_by"] = successor_id
    pages.write_page(page.path, page.fm, page.body)
    updated = set_claim_status(root, claim_id, "superseded")

    mine = stance.derive_exposure(page.fm)
    theirs = stance.derive_exposure(successor.fm)
    note = ""
    if theirs != "severely-tested":
        note = (
            f"note: {successor_id}'s exposure is '{theirs}', so nothing on record says it "
            f"survives what {claim_id} ('{mine}') failed. That is a swap, not yet a "
            "supersession — a degenerating problemshift is no more a sufficient reason to "
            "eliminate a claim than an old-fashioned refutation (Lakatos p.69); the "
            f"objective reason is a rival that wins. Test it: `flip claim test "
            f"{successor_id} --probe … --error … --would-detect … --if-absent … --against "
            "… --result …`"
        )
    return updated, note


def _id_sort_key(fm: dict) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(fm.get("id", "")))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(fm.get("id", "")), 0)


def list_claims(
    root: Path,
    status: str | None = None,
    stance_value: str | None = None,
    exposure: str | None = None,
) -> list[dict]:
    """All claims as frontmatter dicts (+ slug, root-relative path, and the
    derived `exposure`), optionally filtered by status, by the notebook's own
    stance, or by exposure. Read-only.

    `exposure` rides along as a computed view field, next to `slug` and
    `path` and for the same reason: it is not on the page and must never be
    written back to one (SPEC §7.1 — verdicts are derived, never stored), but
    every caller that lists claims wants it, and recomputing it in four places
    is how the four drift apart.
    """
    if status is not None and status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    if stance_value is not None and stance_value not in stance.STANCES:
        raise SystemExit(
            f"invalid stance '{stance_value}' (one of: {', '.join(stance.STANCES)})"
        )
    if exposure is not None and exposure not in stance.EXPOSURES:
        raise SystemExit(
            f"invalid exposure '{exposure}' (one of: {', '.join(stance.EXPOSURES)})"
        )
    out = []
    for p in _claim_pages(root):
        if status is not None and p.fm.get("status") != status:
            continue
        derived = stance.derive_exposure(p.fm)
        if exposure is not None and derived != exposure:
            continue
        own = stance.notebook_stance(p.fm)
        if stance_value is not None and (own or {}).get("stance") != stance_value:
            continue
        row = {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        row["exposure"] = derived
        if own:
            row["stance"] = str(own.get("stance"))
        out.append(row)
    return sorted(out, key=_id_sort_key)
