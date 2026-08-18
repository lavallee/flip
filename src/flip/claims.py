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

**Citation roles** are that same lesson in a second place. Every entry in a
claim's `sources:` carries a `role` (SPEC §7): `evidence` — the default, and
what every citation written before 0.16 is — says the source is a WITNESS to
what the claim asserts, and only witnesses corroborate. `subject` says the
claim is ABOUT this source: the source is what makes the claim true or false,
not evidence for it, and a second source could only ever be a second READING
of the same document. That is an independent reader, not an independent
causal path; it addresses reader error, and corroboration is a check on
source error. The two are not interchangeable, so a subject citation is
excluded from the count.

And a claim whose every citation is a subject has NO
`independent_corroboration` key at all — not a zero (`corroboration_applies`,
`claim_corroboration`). Zero would be the same wrong number: it reads as "the
evidence is thin" when the truth is "this axis does not apply here". A claim
citing nothing at all keeps its 0, because there the question does apply and
nobody has answered it — the absent key means *inapplicable*, never *unmet*.

The audit that IS available on a subject citation is an `attribution` test
(SPEC §7.1): anyone can re-run it against the same custody, which is exactly
what makes it the right check where a second source is impossible in
principle. A severe, surviving one is what the `verified` gate accepts in the
bar's place for a subject-only claim, and doctor names a subject citation
that has never had one. flip checks that the test is on record, never that it
is true — the same limit the stance layer already declares.

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

# What a citation DOES for the claim that makes it (SPEC §7). The role lives
# on the ENTRY, not on the claim and not on the source page, because the same
# source is constitutive for one claim and evidential for another: a rebuttal
# paper is what one claim is about and a witness for the next one.
#
# Two values, and each earns its place the way flip's other enums do — it must
# name a situation the other cannot, and it must change what happens next.
#
#   evidence  a witness to what the claim asserts. Counts toward corroboration
#             when its page is judged and independent. THE DEFAULT, and the
#             role every citation written before 0.16 has: agreement between
#             causally independent paths to the same fact is evidence, and
#             that is what the count was always measuring.
#   subject   the claim is ABOUT this source — it is the fact-maker, not
#             evidence for the fact. Cannot corroborate itself, so it is
#             excluded from the count. What it can have instead is an
#             `attribution` test (SPEC §7.1), which anyone can re-run against
#             the same custody: the applicable audit where a second source is
#             impossible in principle rather than merely absent.
CITATION_ROLES = ("evidence", "subject")
DEFAULT_CITATION_ROLE = "evidence"

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


def citation_role(entry: object) -> str:
    """The role of one `sources:` entry — `evidence` or `subject` (SPEC §7).

    Anything unreadable reads as `evidence`: a bare string (hand edits,
    pre-0.7 pages), a missing key, and — deliberately — a typo'd value. A
    misspelled role must never be the thing that quietly excused a claim from
    the corroboration bar, so the unknown value counts as a witness and
    doctor's `bad-enum` names it.
    """
    if not isinstance(entry, dict):
        return DEFAULT_CITATION_ROLE
    role = str(entry.get("role") or "").strip()
    return role if role in CITATION_ROLES else DEFAULT_CITATION_ROLE


def source_citations(fm: dict) -> list[tuple[str, str]]:
    """A claim's citations as `(ref, role)` pairs, in order — the shape the
    write paths plumb through, since regenerating a page from ids alone would
    drop both the pinned passage and the role.

    `source_ids` and `source_refs` stay exactly what they were: everything
    that only wants to know WHICH sources, or which words, goes on asking that
    and gets the same answer whatever the roles are.
    """
    out: list[tuple[str, str]] = []
    for entry in pages.as_list(fm.get("sources")):
        role = citation_role(entry)
        if not isinstance(entry, dict):
            sid = str(entry).strip()
            if sid:
                out.append((sid, role))
            continue
        sid = str(entry.get("id", "")).strip()
        if not sid:
            continue
        labels = [str(x) for x in pages.as_list(entry.get("excerpts")) if str(x).strip()]
        if labels:
            out.extend((util.format_excerpt_ref(sid, label), role) for label in labels)
        else:
            out.append((sid, role))
    return out


def _roles_by_id(fm: dict) -> dict[str, str]:
    """Base source id → its role on this claim, first-seen order.

    One source gets one role per claim, and `subject` wins any disagreement: a
    document the claim is about cannot also be an independent witness to what
    it says about that document. So a page citing the same id both ways — a
    hand edit, or `--source P18 --about P18` — collapses to `subject` rather
    than quietly keeping the id in the count.
    """
    roles: dict[str, str] = {}
    for ref, role in source_citations(fm):
        base = util.split_ref(ref)[0]
        if role == "subject" or base not in roles:
            roles[base] = role
    return roles


def _ids_with_role(fm: dict, role: str) -> list[str]:
    return [sid for sid, sid_role in _roles_by_id(fm).items() if sid_role == role]


def evidence_ids(fm: dict) -> list[str]:
    """The claim's cited source ids that are witnesses to what it asserts —
    the only ones the corroboration bar counts. Deduped, in order."""
    return _ids_with_role(fm, "evidence")


def subject_ids(fm: dict) -> list[str]:
    """The claim's cited source ids that the claim is ABOUT. Deduped, in order.

    These are the fact-makers. They cannot corroborate the claim they make
    true or false, and what stands in for corroboration on them is an
    `attribution` test (`unaudited_subjects`).
    """
    return _ids_with_role(fm, "subject")


def corroboration_applies(fm: dict) -> bool:
    """Whether "how many independent witnesses agree?" is a question this
    claim can be asked at all.

    False in exactly one situation: the claim cites something, and everything
    it cites is a `subject`. There the question has no answer rather than the
    answer zero — the only possible second source would be a second reading of
    the same document, which is not a second path to the fact.

    True when a claim cites nothing, which is the distinction the whole thing
    turns on. "Nobody has cited anything" is a real zero: the question applies
    and no one has answered it, and that number is exactly the one that should
    prompt a look. Only a subject citation says the axis itself is the wrong
    instrument.
    """
    return not source_ids(fm) or bool(evidence_ids(fm))


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
    `derivative` never satisfy the bar.

    The pure counter: it answers "how many of THESE sources are independent
    witnesses" and nothing else. Callers holding a claim's frontmatter want
    `claim_corroboration` instead, which asks the roles whether the question
    applies before it asks this one how many.
    """
    return sum(
        1
        for fm in _linked_fms(source_fms, source_ids)
        if sources_mod.judged(fm) and fm.get("independence") == "independent"
    )


def claim_corroboration(source_fms: list[dict], fm: dict) -> int | None:
    """A claim's independent corroboration — or None when the axis does not
    apply to it. The claim-level entry point every caller with a frontmatter
    dict goes through (add_claim, set_claim_status, doctor, views, export).

    None means the claim cites only `subject` sources: there is no count to
    take, because the only conceivable second source is a second reading of
    the document the claim is about. Callers must render that as absent —
    omit the key, print `n/a` — and never as 0. A number nobody can act on is
    worse than a blank somebody asks about.
    """
    if not corroboration_applies(fm):
        return None
    return corroboration_count(source_fms, evidence_ids(fm))


def _set_corroboration(fm: dict, source_fms: list[dict]) -> int | None:
    """Write `independent_corroboration` onto a claim's frontmatter — or
    REMOVE it when the axis no longer applies. Returns what it decided.

    The removal is the half that is easy to forget: a claim re-cited from
    evidence to subject would otherwise keep a stale count that now reads as a
    verdict on evidence nobody claims to have.
    """
    count = claim_corroboration(source_fms, fm)
    if count is None:
        fm.pop("independent_corroboration", None)
    else:
        fm["independent_corroboration"] = count
    return count


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


def unaudited_subjects(fm: dict) -> list[str]:
    """The claim's `subject` citations that no severe attribution test has
    survived against, in order. Empty when every subject has been read for the
    error and the error was not found.

    This is the whole answerable half of the citation-role design. A subject
    citation cannot be corroborated — nothing about the world could witness
    what a document says — so the ask that replaces corroboration is the one
    audit that IS available, and this names the ones nobody has taken. Refs
    are compared by base id: a test run against `T1§relevance-null` audits the
    passage of T1 the claim rests on, and the grouping that makes one source
    one source everywhere else makes it one source here.

    What flip can see is that a test is on record. Whether the reading was any
    good is beyond it, exactly as with `support.method` and every field of a
    test record (SPEC §7.1). A `subject` role is authored and can therefore be
    used to duck the corroboration bar; the honest defences are that the role
    is legible on the page and that this list is what doctor reports.
    """
    audited = {util.split_ref(ref)[0] for ref in stance.survived_attribution_sources(fm)}
    return [sid for sid in subject_ids(fm) if sid not in audited]


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


def _group_refs(cited: list[tuple[str, str]]) -> dict[str, tuple[list[str], str]]:
    """Citations grouped base-id → (pinned excerpt labels, role), everything
    deduped and in first-seen order. `[("T1§a","evidence"), ("A2","evidence"),
    ("T1§b","evidence")]` → `{"T1": (["a","b"], "evidence"), "A2": ([], …)}`.

    Grouping is what keeps one source one source: a claim resting on two
    passages of the same conversation has two citations and one piece of
    evidence, and only the second number may reach corroboration. The role
    rides along because it belongs to the citation and would otherwise be lost
    the first time a page was regenerated — `subject` wins a disagreement, for
    the reason `_roles_by_id` gives.
    """
    grouped: dict[str, tuple[list[str], str]] = {}
    for ref, role in cited:
        base, label = util.split_ref(str(ref))
        labels, current = grouped.get(base, ([], role))
        if role == "subject":
            current = role
        if label and label not in labels:
            labels.append(label)
        grouped[base] = (labels, current)
    return grouped


def _attribution(
    src_by_id: dict[str, pages.Page], cited: list[tuple[str, str]]
) -> tuple[list[dict], list[str]]:
    """(OKF `sources` entries, footnote-definition lines) for a claim's
    `(ref, role)` citations, deduped, in order.

    Resolvable ids get a followable bundle-absolute `resource`, the page
    title, and a relative-linked definition; dangling ids keep just the id
    and a plain-text definition — dangling is legal (SPEC §6.1), doctor
    counts them.

    A ref pinning a transcript passage (`T1§relevance-null`) contributes its
    label to the entry's `excerpts` list and deep-links `resource` at the
    passage anchor. Footnote labels stay base-id-shaped (`[^T1]`) whatever is
    pinned: they are markdown labels, and one source keeps one marker.

    `role` is written only when it is `subject`. The default is the meaning of
    the key's absence, so every citation ever written stays byte-identical
    through a regeneration and no notebook needs migrating — the same reason
    OKF's own optional keys are optional.
    """
    entries: list[dict] = []
    defs: list[str] = []
    for sid, (labels, role) in _group_refs(cited).items():
        page = src_by_id.get(sid)
        entry: dict = {"id": sid}
        if role != DEFAULT_CITATION_ROLE:
            entry["role"] = role
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


def _apply_attribution(body: str, cited: list[tuple[str, str]], defs: list[str]) -> str:
    """Regenerate the two body parts flip owns — the id-shaped footnote
    markers ending the lead paragraph and the definition lines — leaving the
    prose itself untouched (SPEC §6.6).

    The role never reaches the body. A footnote is a citation link, and a
    marker that read `[^P18 subject]` would put a piece of flip's frontmatter
    vocabulary into published prose, where it means nothing to a reader and
    breaks the label shape that keeps hand-authored footnotes safe.
    """
    text = _FOOT_DEF_RE.sub("", body).strip("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    head, sep, rest = text.partition("\n\n")
    head = _MARKER_TAIL_RE.sub("", head.rstrip())
    head += "".join(f"[^{sid}]" for sid in _group_refs(cited))
    text = head + sep + rest if rest else head
    if defs:
        text = (text + "\n\n" if text else "") + "\n".join(defs)
    return text + "\n" if text else ""


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10).

    Every mutation in this module writes claims/ pages and nothing else —
    citing a source annotates the claim page, never the source page, and
    rivals/supersede touch two pages that are both claims — so the narrowed
    refresh is honest for the whole module.
    """
    from . import views

    views.regenerate(root, changed=("claims",))


def add_claim(
    root: Path,
    text: str,
    sources: list[str],
    load_bearing: bool = False,
    notes: str | None = None,
    value: str | None = None,
    unit: str | None = None,
    subjects: list[str] | None = None,
    absent_from: str | None = None,
    surfaces: list[str] | None = None,
    derives_from: list[str] | None = None,
) -> pages.Page:
    """Add a claim page with status "asserted", allocating the next C#.

    A quantitative claim's number travels as data (`value`/`unit`), not only
    as prose — the format's own export can't fix a free-text number
    downstream. `value` stays a string (a range or "~42" is a legal value).

    `sources` are cited as evidence — witnesses to what the claim asserts.
    `subjects` are cited as what the claim is ABOUT (SPEC §7): the claim is
    made true or false by that document, so it never counts toward
    corroboration, and a claim citing subjects only carries no
    `independent_corroboration` key at all rather than a zero.

    `absent_from` marks an ABSENCE claim — "looked and found nothing" as an
    assertion the work leans on — and scopes it (SPEC §7): `corpus` speaks
    only for what the notebook holds; anything wider must name the
    `surfaces` searched, because the null's evidentiary weight IS its
    search coverage. The claim then lives the full claim life: cited,
    graded through its sources, probed (`flip claim test` against a
    searched surface is "re-run the search"), superseded when the thing is
    later found.

    `derives_from` records that this claim RESTS ON other claims (SPEC §7):
    a derivation edge, not a citation — doctor walks these so an
    unsupported ancestor surfaces on every load-bearing claim built on it
    instead of contaminating them silently.
    """
    root = util.require_notebook_root(root)
    text = (text or "").strip()
    if not text:
        raise SystemExit("empty claim text; state the assertion in one sentence")
    named_surfaces = [str(s).strip() for s in (surfaces or []) if str(s).strip()]
    if absent_from is not None:
        if absent_from not in util.ABSENT_FROM:
            raise SystemExit(
                f"invalid absent_from '{absent_from}' "
                f"(one of: {', '.join(util.ABSENT_FROM)})"
            )
        if absent_from != "corpus" and not named_surfaces:
            raise SystemExit(
                f"absent_from '{absent_from}' asserts more than this corpus; name the "
                "surfaces searched (--surface, repeatable) or scope it to 'corpus'"
            )
    elif named_surfaces:
        raise SystemExit("--surface given without --absent-from; pass both or neither")
    if unit and value is None:
        # Refused before allocate_id like every other validation: a refusal
        # after allocation burns a C# forever (reservations are never freed).
        raise SystemExit("--unit given without --value; pass both or neither")
    ancestors = list(dict.fromkeys(
        str(s).strip() for s in pages.as_list(derives_from) if str(s).strip()
    ))
    for ancestor in ancestors:
        anc = pages.find_by_id(root, ancestor)
        if anc is None or str(anc.fm.get("type", "")) != "Claim":
            raise SystemExit(
                f"unknown claim id '{ancestor}' for derives_from; a claim can only "
                "derive from another claim page in this notebook"
            )
    cited = [(str(s), "evidence") for s in pages.as_list(sources)]
    cited += [(str(s), "subject") for s in pages.as_list(subjects)]
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
    }
    # Built in key order, which is why this is not `_set_corroboration`: on a
    # subject-only claim the key is simply never written, and a reader of the
    # page sees no count rather than a zero they would have to interpret.
    corroboration = claim_corroboration([p.fm for p in src_by_id.values()], fm)
    if corroboration is not None:
        fm["independent_corroboration"] = corroboration
    if absent_from is not None:
        absence: dict = {"scope": absent_from}
        if named_surfaces:
            absence["surfaces"] = named_surfaces
        fm["absence"] = absence
    if ancestors:
        fm["derives_from"] = ancestors
    fm["first_asserted"] = util.today()
    fm["generated"] = util.generated_now()
    if value is not None:
        fm["value"] = str(value)
        if unit:
            fm["unit"] = str(unit)
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
    slug = pages.unique_slug(
        claims_dir, pages.slugify(text, fallback=claim_id.lower()), entity_id=claim_id
    )
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


def _refuse_verified_subject_claim(claim_id: str, fm: dict) -> None:
    """Gate `verified` on a claim that cites only its subject (SPEC §7).

    The corroboration bar cannot be applied here, and that is a fact about the
    claim rather than a shortfall in its evidence: "the rebuttal does not
    mention Persson" is made true or false by the rebuttal, and a second
    source could only ever be a second READING of it. So the bar is replaced,
    not waived — by a severe, surviving `attribution` test against every cited
    subject, which is the audit the situation actually admits and the one any
    reader can re-run against the same custody.

    Passing needs the test on the page; it does not need the test to have been
    a good one, which flip cannot tell (SPEC §7.1, departure 3). The defence
    against writing one to order is the same defence the whole stance layer
    runs on: the record is legible, dated, attributed, and re-runnable by
    someone who disagrees.
    """
    missing = unaudited_subjects(fm)
    if not missing:
        return
    subjects = subject_ids(fm)
    first = missing[0]
    raise SystemExit(
        f"cannot verify {claim_id}: it cites {', '.join(subjects)} as the source(s) it is "
        f"ABOUT, so the corroboration bar has nothing to count — a second independent "
        "witness to what one document says is not a thing that can exist, and the count "
        "would be a comment on the claim's evidence rather than on this. What stands in "
        f"for it is an attribution test that went looking for the error and did not find "
        f"it: no severe, surviving one is on record against {', '.join(missing)}. Run it "
        f"and record what it found — `flip claim test {claim_id} --probe attribution "
        '--error "<the specific thing the claim could be getting wrong about what '
        f'{first} says>" --would-detect "<how that would have shown up in the text>" '
        '--if-absent "<what you would have seen instead, had the claim been right>" '
        f"--against {first} --result survived|failed`. Do not add a second source to "
        "clear this; there is no second source to add. (A2's other path still stands: "
        f"`flip claim verify {claim_id} --method adversarial|recomputation` clears the "
        "gate here as it does anywhere else — but on a claim about a document, the "
        "attribution test is the same work with the error named)"
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

    A claim citing only `subject` sources (SPEC §7) meets a different bar,
    because that one is unsatisfiable in principle rather than merely unmet:
    it asks for a second independent witness to what one document says, and no
    such witness can exist. What it asks for instead is a **severe, surviving
    `attribution` test against every cited subject** — the audit that is
    actually available, and one any reader can re-run against the same
    custody. Nothing else is loosened: the substitution is offered only where
    the count itself has no meaning.

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
    # Refs drive regeneration (they carry the pinned passages and the roles);
    # ids drive the evidence bar. Regenerating from ids alone silently
    # unpinned every excerpt the moment a claim changed status.
    cited_refs = source_citations(page.fm)
    src_by_id = _source_pages_by_id(root)
    source_fms = [p.fm for p in src_by_id.values()]
    corroboration = claim_corroboration(source_fms, page.fm)
    if status == "verified" and corroboration is None:
        # A2's other path is untouched: an adversarial/recomputation record
        # still clears the gate here exactly as it does anywhere else. What
        # changes is only what stands in for the count that cannot be taken.
        if not has_gating_verification(page.fm):
            _refuse_verified_subject_claim(claim_id, page.fm)
    elif status == "verified":
        profile = profiles.load_profile(manifest.load_manifest(root).kind, root)
        counted = evidence_ids(page.fm)
        linked = _linked_fms(source_fms, counted)
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
                f" (evidence: {', '.join(counted) or 'none'}); add sources whose "
                "independence is 'independent' to the claim"
            )
            if profile.claim_grade_a_suffices:
                msg += " or upgrade one to grade A via `flip grade`"
            # A subject citation is not missing from the count by accident, so
            # say so where the count is being read as a verdict: the operator
            # who cited it deliberately should not spend an afternoon
            # wondering why their source vanished.
            subjects = subject_ids(page.fm)
            if subjects:
                msg += (
                    f"; {', '.join(subjects)} "
                    f"{'is' if len(subjects) == 1 else 'are'} cited as what this claim is "
                    "ABOUT and never counted — a document cannot corroborate a claim about "
                    "itself"
                )
            # Lead with the cause when there is one: an uncountable source is a
            # vocabulary problem wearing an evidence problem's clothes, and the
            # count above understates the evidence rather than measuring it.
            stale = uncountable_sources(source_fms, counted)
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
    page.fm["sources"] = entries
    _set_corroboration(page.fm, source_fms)
    page.fm.pop("supports", None)  # pre-0.7 key; the entries carry the paths now
    body = _apply_attribution(page.body, cited_refs, defs)
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def _write_sources(
    root: Path, page: pages.Page, cited: list[tuple[str, str]]
) -> pages.Page:
    """Persist a claim's new citation list: regenerate the OKF `sources`
    entries + footnote attribution against current source slugs and recompute
    independent_corroboration. Takes `(ref, role)` pairs — refs so the pinned
    passages survive, roles so the count knows which citations are witnesses.
    The prose round-trips (SPEC §6.6).

    The recompute goes through `_set_corroboration`, so a claim whose last
    evidence citation was just removed loses the key rather than dropping to a
    zero that would read as a verdict on evidence it never claimed to have.
    """
    refs = [(str(ref), role) for ref, role in cited]
    src_by_id = _source_pages_by_id(root)
    entries, defs = _attribution(src_by_id, refs)
    page.fm["sources"] = entries
    page.fm.pop("supports", None)
    _set_corroboration(page.fm, [p.fm for p in src_by_id.values()])
    body = _apply_attribution(page.body, refs, defs)
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def add_claim_sources(
    root: Path, claim_id: str, new_ids: list[str], subjects: list[str] | None = None
) -> tuple[pages.Page, list[str], list[str], list[tuple[str, str]]]:
    """Link one or more citations to a claim (A1): append to `sources:`,
    regenerate the footnote attribution, recompute corroboration.

    `new_ids` are cited as evidence, `subjects` as what the claim is ABOUT
    (SPEC §7). A ref already cited in the OTHER role is **re-roled** rather
    than refused: the role is a property of the citation, so `--about P18` on
    a claim that already cites P18 says something unambiguous about that
    citation, and making the operator delete and re-add it would regenerate
    the page twice to express one correction. Re-roling to `subject` can
    remove the corroboration key entirely, which is the point of doing it.

    Unknown ids — no references/ page carries them — are refused before any
    write; this is the post-hoc linker, not a place to invent dangling cites.
    Returns (page, newly-linked refs, re-roled refs, warnings), where warnings
    are `(source_id, reason)` pairs for any linked source that won't count
    toward the bar: `"unjudged"` (graded "?" — capture is custody, not
    judgment, D12/§5.4) or `"unmigrated"` (pre-0.8 `independence` vocabulary,
    which needs re-reading rather than first-time judging — a different fix,
    so a different word). Refuses when nothing given would change anything.
    """
    root = util.require_notebook_root(root)
    refs = [(str(s), "evidence") for s in pages.as_list(new_ids)]
    refs += [(str(s), "subject") for s in pages.as_list(subjects)]
    if not refs:
        raise SystemExit(
            "no source ids given; pass at least one references/ id as evidence (e.g. A3), "
            "or as the source the claim is about (`--about P18`)"
        )
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
    for sid, (labels, _role) in grouped.items():
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
    current = source_citations(page.fm)
    known_roles = dict(current)
    wanted = list(dict.fromkeys(refs))
    added = [ref for ref, role in wanted if ref not in known_roles]
    rerolled = [ref for ref, role in wanted if known_roles.get(ref, role) != role]
    if not added and not rerolled:
        cited = ", ".join(dict.fromkeys(ref for ref, _ in wanted))
        raise SystemExit(
            f"claim {claim_id} already cites {cited} in the role given; nothing to add. "
            f"To change what a citation is FOR, pass it the other way "
            f"(`--about <id>` for the source the claim is about, a bare id for a witness); "
            f"to drop it, `flip claim source rm {claim_id} <id>`"
        )
    roles = dict(wanted)
    keep = [(ref, roles.get(ref, role)) for ref, role in current]
    updated = _write_sources(root, page, keep + [(ref, roles[ref]) for ref in added])
    # Only evidence earns the grading warning. "It won't count toward the bar"
    # is not news about a citation whose whole declaration is that the bar
    # does not apply to it, and a warning that fires where its advice is
    # meaningless is how operators learn to skim warnings.
    warnings = [
        (ref, "unmigrated" if sources_mod.unmigrated(src_by_id[base].fm) else "unjudged")
        for ref in added
        if roles[ref] == "evidence"
        for base in [util.split_ref(ref)[0]]
        if not sources_mod.judged(src_by_id[base].fm)
    ]
    return updated, added, rerolled, warnings


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
    current = source_citations(page.fm)
    if label:
        keep = [(s, role) for s, role in current if s != ref]
    else:
        keep = [(s, role) for s, role in current if util.split_ref(s)[0] != base]
    if len(keep) == len(current):
        cites = ", ".join(s for s, _ in current) or "none"
        raise SystemExit(f"claim {claim_id} does not cite {ref} (cites: {cites})")
    return _write_sources(root, page, keep)


def derivation_ids(fm: dict) -> list[str]:
    """The claim ids this claim declares it rests on (`derives_from:`)."""
    return [str(s) for s in pages.as_list(fm.get("derives_from"))]


def unsupported_reason(fm: dict) -> str | None:
    """Why this claim cannot support a claim derived from it, or None.

    The DRIFT rule: an unsupported link contaminates everything built on it,
    so the doctor walks derivation chains and needs one word for what it
    finds. Discredited outright: status false-positive/retracted, or a
    refuting exposure (misattributed/refuted). Unsupported: nothing backs it
    — no evidence citations, no gating verification — and no severe test has
    survived against it (a subject-only claim whose attribution probe
    survived IS supported; the probe is its evidence).
    """
    status = str(fm.get("status", ""))
    if status in ("false-positive", "retracted"):
        return f"status {status}"
    exposure = stance.derive_exposure(fm)
    if exposure in stance.REFUTING_EXPOSURES:
        return f"exposure {exposure}"
    if exposure == "severely-tested":
        return None
    # evidence_ids, not a raw role scan: on a dual-role citation (same id as
    # evidence and subject) the subject reading wins everywhere else, and the
    # walk must agree with the count the corroboration machinery takes.
    if not evidence_ids(fm) and not has_gating_verification(fm):
        return "no evidence sources and no surviving verification"
    return None


def add_claim_derivation(
    root: Path, claim_id: str, ancestor_ids: list[str]
) -> tuple[pages.Page, list[str]]:
    """Declare that a claim rests on others (post-hoc `derives_from` linker).

    Refuses unknown ids, non-claims, self-derivation, and cycles — a
    derivation loop would make every claim in it its own support. Returns
    (page, newly-linked ids); refuses when nothing would change.
    """
    root = util.require_notebook_root(root)
    wanted = list(dict.fromkeys(
        str(s).strip() for s in pages.as_list(ancestor_ids) if str(s).strip()
    ))
    if not wanted:
        raise SystemExit("no claim ids given; pass at least one C# to derive from")
    page = _find_claim(root, claim_id)
    current = derivation_ids(page.fm)
    added = [a for a in wanted if a not in current]
    if not added:
        raise SystemExit(
            f"claim {claim_id} already derives from {', '.join(wanted)}; nothing to add"
        )
    for ancestor in added:
        if ancestor == page.id:
            raise SystemExit(f"claim {claim_id} cannot derive from itself")
        anc = pages.find_by_id(root, ancestor)
        if anc is None or str(anc.fm.get("type", "")) != "Claim":
            raise SystemExit(
                f"unknown claim id '{ancestor}'; a claim can only derive from "
                "another claim page in this notebook"
            )
        # Walk the ancestor's own chain: reaching this claim from it means the
        # new edge would close a loop.
        seen: set[str] = set()
        frontier = [ancestor]
        while frontier:
            node = frontier.pop()
            if node in seen:
                continue
            seen.add(node)
            if node == page.id:
                raise SystemExit(
                    f"deriving {claim_id} from {ancestor} would close a cycle "
                    f"({ancestor} already rests on {claim_id})"
                )
            node_page = pages.find_by_id(root, node)
            if node_page is not None:
                frontier.extend(derivation_ids(node_page.fm))
    page.fm["derives_from"] = current + added
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body), added


def remove_claim_derivation(root: Path, claim_id: str, ancestor_id: str) -> pages.Page:
    """Drop a `derives_from` edge. Refuses when the edge isn't there."""
    root = util.require_notebook_root(root)
    page = _find_claim(root, claim_id)
    current = derivation_ids(page.fm)
    ancestor_id = str(ancestor_id).strip()
    if ancestor_id not in current:
        rests = ", ".join(current) or "nothing"
        raise SystemExit(
            f"claim {claim_id} does not derive from {ancestor_id} "
            f"(derives from: {rests})"
        )
    keep = [a for a in current if a != ancestor_id]
    if keep:
        page.fm["derives_from"] = keep
    else:
        page.fm.pop("derives_from", None)
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


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
