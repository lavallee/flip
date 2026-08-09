"""Beliefs as entity pages — beliefs/<slug>.md, ids B# (SPEC §7.1).

**A belief is a claim about believers, not about the world.** "38% of school
board members think test scores fell" is measurable, checkable, and gradeable
like any other fact; whether test scores actually fell is a different fact,
established by different evidence, and its answer changes nothing about the
first. flip's claim vocabulary could not say this. Everything not-yet-verified
landed in one undifferentiated non-verified state, so "a source we captured
does not contain the proposition we attributed to it" and "nobody has ever
tested this" wore the same badge — and a notebook whose citations failed an
audit read as a notebook whose thesis had failed.

The Belief class separates the two axes that were collapsed, and keeps them
separate mechanically:

- **`status`** is custody of the *record of who believes what* — `active`,
  `dormant`, `retracted`. `retracted` is the only value that says something is
  wrong, and what it says is wrong is our record of the believing, never the
  proposition. There is deliberately no `verified`, `false-positive` or
  `superseded` here: those are verdicts on the proposition, they live on
  Claims, and letting them onto a belief page is the category error this class
  exists to prevent.
- **`stance`** is the notebook's own relation to the proposition —
  `unexamined` (the default, and the honest one: nobody here has tested it) ·
  `contested` · `supported` · `contradicted` · `mixed`. Stance moves
  append-only through `stance_history`, so a belief that was held before the
  evidence landed still shows that it was, and holding a belief the record now
  cuts against costs nothing but a stance value.

Two kinds share the class, and their required fields are where they differ:

- **`attributed`** — somebody else holds it. It must name a **`function`**:
  what the belief explains, protects, or licenses for the holder. Prevalence
  is not the actionable field. The deficit model — wrong beliefs are
  information shortfalls, curable by supplying facts — is the assumption that
  makes a percentage look like the useful number, and on identity-loaded
  topics better-informed people are frequently *more* polarized rather than
  less. What a belief does for the person holding it is what points at an
  intervention; how many people hold it only sizes the room.
- **`working`** — this notebook holds it, as a live hypothesis. It must name a
  **`falsified_by`**: what would make us drop it. Same object, opposite
  obligation, and the asymmetry is honest — an attributed belief needs no
  falsifier because we are not the ones betting on it, and a working belief
  needs no function because we already know why we are entertaining it.

**A belief never corroborates anything.** `claims.add_claim` and
`claim source add` refuse a `B#` citation before writing, and doctor's
`belief-as-evidence` catches what was hand-edited in. This is the direction
that matters: a true fact about believing drifting into a claim about the
world is how "many people think X" becomes "X".

What *is* graded, unchanged, is the **measurement**: a survey is a source like
any other, so `flip belief measure` records `{value, of, as_of, sources}` and
`measurement_corroboration` is computed by `claims.corroboration_count` — the
one shared implementation, counting judged, independent sources and nothing
else. The key is named apart from the claim's `independent_corroboration` on
purpose: nothing on this page counts toward the proposition, and the field
names should make that unreadable as anything else.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import claims as claims_mod
from . import manifest, pages, util

# The kinds, and the field each one owes (see the module docstring).
BELIEF_KINDS = ("attributed", "working")
REQUIRED_FIELD = {"attributed": "function", "working": "falsified_by"}

# The notebook's relation to the proposition — never a verdict recorded twice.
# `unexamined` is the default because it is usually the true one, and because
# it is the value flip had no way to say.
STANCES = ("unexamined", "contested", "supported", "contradicted", "mixed")

# Custody of the record of the believing. Three values, none of them a verdict
# on the proposition.
STATUSES = ("active", "dormant", "retracted")

_DESCRIPTION_MAX = 160
_ID_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _description(text: str) -> str:
    s = " ".join(str(text).split())
    if len(s) <= _DESCRIPTION_MAX:
        return s
    return s[: _DESCRIPTION_MAX - 1].rstrip() + "…"


def _require_text(value: str | None, what: str, hint: str) -> str:
    value = (value or "").strip()
    if not value:
        raise SystemExit(f"{what}; {hint}")
    return value


def belief_pages(root: Path) -> list[pages.Page]:
    """Every beliefs/ page carrying `type: Belief`, filename order."""
    return [p for p in pages.iter_pages(root, "beliefs") if p.fm.get("type") == "Belief"]


def belief_ids(root: Path) -> set[str]:
    """The ids beliefs/ currently holds. Used by claims.py to refuse a `B#`
    citation before it is written — the one place the separation is cheapest
    to enforce, because nothing has to be un-done afterwards."""
    return {p.id for p in belief_pages(root) if p.id}


def _find_belief(root: Path, belief_id: str) -> pages.Page:
    """The beliefs/ page carrying `belief_id`, or an actionable refusal."""
    found = belief_pages(root)
    page = next((p for p in found if p.id == belief_id), None)
    if page is None:
        known = ", ".join(p.id for p in found if p.id) or "none yet"
        raise SystemExit(
            f"no belief '{belief_id}' in beliefs/ (known: {known}); record it with "
            "`flip belief add`"
        )
    return page


def _claim_ids(root: Path) -> set[str]:
    return {
        p.id
        for p in pages.iter_pages(root, "claims")
        if p.id and p.fm.get("type") == "Claim"
    }


def _check_about(root: Path, about: str) -> str:
    """Validate an `about:` target: it must be an existing Claim id.

    `about` points at the Claim that states this proposition as a fact about
    the world — the other half of the pair, so a reader can see both at once.
    It is a pointer and nothing else: linking a belief to a claim never moves
    the claim's status, never touches its corroboration, and never adds the
    belief's measurement sources to the claim's evidence. Pointing it at a
    Belief or a Forecast is refused, because then the pair would be two
    records of the same side.
    """
    about = str(about).strip()
    known = _claim_ids(root)
    if about in known:
        return about
    if about in belief_ids(root):
        raise SystemExit(
            f"about '{about}' is a belief, not a claim; `about` names the Claim that "
            "states this proposition as a fact about the WORLD — pointing one belief "
            "at another records the same side twice and leaves the proposition "
            "unstated. Write the claim with `flip claim add`, then point here"
        )
    listed = ", ".join(sorted(known, key=_id_sort_key_str)) or "none yet"
    raise SystemExit(
        f"about '{about}' is not an existing claim id (known: {listed}); the "
        "proposition's world-side lives in claims/ where it gets sources and a "
        "verification bar — add it with `flip claim add`, then point the belief at it"
    )


def _id_sort_key_str(entity_id: str) -> tuple:
    m = _ID_RE.match(str(entity_id))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(entity_id), 0)


def _id_sort_key(fm: dict) -> tuple:
    return _id_sort_key_str(str(fm.get("id", "")))


def _set_before(fm: dict, key: str, value, before: str) -> dict:
    """`fm` with `key` set, placed just before `before` when it is new.

    Both of a belief's after-the-fact keys — `about` (the claim usually exists
    first) and `measurements` (a number arrives long after the belief was
    noticed) — would otherwise land at the bottom of the frontmatter, below
    the stance history and the generation stamp, which is where a human
    reading the page in Obsidian's properties panel meets them last. An
    existing key keeps its place; foreign keys keep their relative order.
    """
    if key in fm:
        fm[key] = value
        return fm
    out: dict = {}
    for existing, current in fm.items():
        if existing == before:
            out[key] = value
        out[existing] = current
    if key not in out:
        out[key] = value
    return out


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10)."""
    from . import views

    views.regenerate(root)


def _finish(root: Path) -> None:
    manifest.touch_updated(root)
    _regenerate_views(root)


def _source_fms(root: Path) -> list[dict]:
    return [p.fm for p in pages.iter_pages(root, "references")]


def measurement_source_ids(fm: dict) -> list[str]:
    """Every references/ id cited by any of a belief's measurements, deduped,
    in first-seen order. The measurement is what carries evidence on a belief
    page, so this is the only list on it that reaches the grading machinery."""
    out: list[str] = []
    for record in pages.as_list(fm.get("measurements")):
        if not isinstance(record, dict):
            continue
        for sid in pages.as_list(record.get("sources")):
            sid = str(sid).strip()
            if sid and sid not in out:
                out.append(sid)
    return out


def measurement_corroboration(source_fms: list[dict], fm: dict) -> int:
    """Independent corroboration of a belief's *measurements* — the same bar,
    the same counter (`claims.corroboration_count`), applied to the only thing
    on the page that evidence bears on.

    A survey is a source like any other: it is captured, graded, and counted
    exactly as a filing or a dataset is. What it corroborates is that people
    hold the proposition, never the proposition. That is why this number lives
    under its own key rather than `independent_corroboration` — the claim key
    means "the evidence for this assertion about the world", and no number on
    a belief page ever means that.
    """
    return claims_mod.corroboration_count(source_fms, measurement_source_ids(fm))


def uncountable_measurement_sources(source_fms: list[dict], fm: dict) -> list[str]:
    """The measurement sources flip can count neither for nor against: pages
    still carrying pre-0.8 `independence` vocabulary (SPEC §5.4).

    Reported wherever the count is reported, for the reason it always is: a
    wrong number is worse than a missing one, because only the missing one
    prompts a look.
    """
    return claims_mod.uncountable_sources(source_fms, measurement_source_ids(fm))


def add_belief(
    root: Path,
    proposition: str,
    belief_kind: str,
    *,
    holders: str | None = None,
    function: str | None = None,
    falsified_by: str | None = None,
    about: str | None = None,
    stance: str = "unexamined",
    notes: str | None = None,
) -> pages.Page:
    """Record a belief page at status "active", allocating the next B#.

    Refusals before any write, each naming the field the kind owes:

    - an `attributed` belief with no `function` — what the belief explains,
      protects or licenses for the holder. Refused rather than defaulted
      because the field is the whole reason to keep the record: a prevalence
      number tells you the size of the room, and the deficit model (wrong
      beliefs are information shortfalls, curable by supplying facts) is what
      makes that look like the actionable number when it is not.
    - a `working` belief with no `falsified_by` — what would make us drop it.
      Refused because a hypothesis nothing could dislodge is not a hypothesis;
      flip's scout profile has demanded a named falsifier per hypothesis since
      §13, and this is the same rule with a page to live on.
    - an `about` that is not an existing Claim id (see `_check_about`).

    `holders` defaults to the acting actor for a `working` belief — the
    notebook is holding it, and saying so twice is ceremony — and is required
    for an `attributed` one, because a belief with no believer named is an
    assertion with a disclaimer attached.
    """
    root = util.require_notebook_root(root)
    proposition = _require_text(
        proposition,
        "empty belief proposition",
        "state what is believed, in the believer's terms and in one sentence",
    )
    if belief_kind not in BELIEF_KINDS:
        raise SystemExit(
            f"invalid belief kind '{belief_kind}' (one of: {', '.join(BELIEF_KINDS)}); "
            "`attributed` records what someone else holds and must name its "
            "function, `working` records what this notebook holds and must name "
            "its falsifier"
        )
    if stance not in STANCES:
        raise SystemExit(
            f"invalid stance '{stance}' (one of: {', '.join(STANCES)}); stance is "
            "this notebook's relation to the proposition, never a verdict on the "
            "believing — the default 'unexamined' is usually the true one"
        )
    if belief_kind == "attributed":
        holders = _require_text(
            holders,
            "an attributed belief has no --holders",
            "name who holds it (a population, a role, a named person) — a belief "
            "with no believer named is an assertion with a disclaimer attached",
        )
        function = _require_text(
            function,
            "an attributed belief has no --function (what the belief explains, "
            "protects, or licenses for the holder)",
            "state it; prevalence sizes the room but function is what points at an "
            "intervention — on identity-loaded topics better-informed holders are "
            "frequently more polarized, not less, so 'they lack the facts' is the "
            "one explanation that reliably fails",
        )
        if falsified_by:
            raise SystemExit(
                "an attributed belief carries --falsified-by; a falsifier is what "
                "would make US drop a belief, and we are not the ones holding this "
                "one. Record what would change the HOLDERS' minds in --function, or "
                "record the notebook's own position as a separate `working` belief"
            )
    else:
        falsified_by = _require_text(
            falsified_by,
            "a working belief has no --falsified-by (what would make this notebook "
            "drop it)",
            "state it; holding a hypothesis costs nothing here — it corroborates "
            "nothing and gates nothing — but a hypothesis nothing could dislodge is "
            "a commitment wearing a hypothesis's clothes (SPEC §13: a named "
            "falsifier per hypothesis)",
        )
        holders = (holders or "").strip() or util.detect_actor()

    belief_id = pages.allocate_id(root, "B")
    now = util.utc_now()
    actor = util.detect_actor()
    fm: dict = {
        "type": "Belief",
        "id": belief_id,
        "aliases": [belief_id],
        "description": _description(proposition),
        "belief_kind": belief_kind,
        "holders": holders,
        "proposition": " ".join(proposition.split()),
    }
    if function:
        fm["function"] = function
    if falsified_by:
        fm["falsified_by"] = falsified_by
    if about is not None:
        fm["about"] = _check_about(root, about)
    fm["stance"] = stance
    fm["stance_history"] = [{"stance": stance, "at": now, "by": actor}]
    fm["status"] = "active"
    if notes:
        fm["notes"] = notes
    fm["first_recorded"] = util.today()
    fm["generated"] = util.generated_now()

    parts = [" ".join(proposition.split())]
    parts.append(f"_Held by {holders}._")
    parts.append(
        f"_Function: {function}_" if function else f"_Falsified by: {falsified_by}_"
    )
    if notes:
        parts.append(f"_{notes}_")
    body = "\n\n".join(parts) + "\n"

    directory = root / "beliefs"
    slug = pages.unique_slug(
        directory, pages.slugify(proposition, fallback=belief_id.lower())
    )
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    _finish(root)
    return pages.Page(path=path, fm=fm, body=body)


def measure_belief(
    root: Path,
    belief_id: str,
    value: str,
    *,
    of: str | None = None,
    as_of: str | None = None,
    sources: list[str] | None = None,
    note: str | None = None,
) -> tuple[pages.Page, list[str]]:
    """Append a prevalence measurement to a belief, append-only.

    Records `{at, by, value, of?, as_of?, sources, note?}` on `measurements:`
    and recomputes `measurement_corroboration` over every measurement's
    sources with the shared counter. Returns (page, uncountable source ids) —
    the count and the reason it may understate the evidence always travel
    together (SPEC §5.4).

    `value` stays a string for the reason a claim's does: "38%", "roughly a
    third", "3 of 11 board members" are all legal values, and an integer that
    silently became the base is how a measurement stops being one. Sources
    must already be captured — a measurement with no source is a number
    someone remembered, and `flip belief measure` is not the place to invent a
    dangling citation.
    """
    root = util.require_notebook_root(root)
    value = _require_text(
        value,
        "empty measurement value",
        "pass the number AS STATED — '38%', '3 of 11 board members', 'roughly a "
        "third'; a string, because an integer masquerades as the base",
    )
    page = _find_belief(root, belief_id)
    cited = [str(s).strip() for s in pages.as_list(sources) if str(s).strip()]
    if not cited:
        raise SystemExit(
            f"measurement on {belief_id} cites no source; a prevalence number with "
            "nothing behind it is a number someone remembered. A survey is a source "
            "like any other — capture it (`flip add-source`), judge it (`flip grade`), "
            "then pass --source"
        )
    known = {p.id: p.fm for p in pages.iter_pages(root, "references") if p.id}
    unknown = [s for s in cited if s not in known]
    if unknown:
        listed = ", ".join(sorted(known, key=_id_sort_key_str)) or "none captured yet"
        raise SystemExit(
            f"unknown source id(s) {', '.join(unknown)}: no references/ page carries "
            f"them (known: {listed}); capture the measurement with `flip add-source` "
            "first — what is measured here is the believing, and it is evidence like "
            "any other"
        )

    record: dict = {"at": util.utc_now(), "by": util.detect_actor(), "value": value}
    if of:
        record["of"] = str(of)
    if as_of:
        record["as_of"] = str(as_of)
    record["sources"] = cited
    if note:
        record["note"] = str(note)
    records = pages.as_list(page.fm.get("measurements"))
    records.append(record)
    page.fm = _set_before(page.fm, "measurements", records, "status")
    source_fms = _source_fms(root)
    page.fm = _set_before(
        page.fm,
        "measurement_corroboration",
        measurement_corroboration(source_fms, page.fm),
        "status",
    )
    pages.write_page(page.path, page.fm, page.body)
    _finish(root)
    return (
        pages.Page(path=page.path, fm=page.fm, body=page.body),
        uncountable_measurement_sources(source_fms, page.fm),
    )


def set_stance(
    root: Path,
    belief_id: str,
    stance: str,
    *,
    because: list[str] | None = None,
    note: str | None = None,
) -> pages.Page:
    """Move the notebook's stance on the proposition, append-only.

    Appends `{stance, at, by, because?, note?}` to `stance_history` and writes
    a dated body section, so the page shows that the belief was held before
    the evidence landed rather than quietly reading as though it always had
    the current stance. Nothing about the belief record changes: the holders
    still hold it, the measurements still stand, and `status` — which is
    custody of the record — is untouched.

    That is the point of the split. A belief the record now contradicts is not
    retracted and not demoted; it is a belief with a stance. If people define
    situations as real, they are real in their consequences, so a belief the
    evidence cuts against is a live cause in the world and worth exactly as
    much custody as one the evidence supports — arguably more, since it is the
    one an intervention has to address.

    `because` names what moved it — claim ids, source ids, a session, a
    forecast. Refused when it points at nothing resolvable: a stance change
    with an unreachable reason is the stance change we most need to audit.
    """
    root = util.require_notebook_root(root)
    if stance not in STANCES:
        raise SystemExit(
            f"invalid stance '{stance}' (one of: {', '.join(STANCES)}); stance is "
            "the notebook's relation to the PROPOSITION — to change the standing of "
            f"the record of the believing, use `flip belief status {belief_id} "
            "active|dormant|retracted`"
        )
    page = _find_belief(root, belief_id)
    reasons = [str(r).strip() for r in pages.as_list(because) if str(r).strip()]
    for ref in reasons:
        base, _label = util.split_ref(ref)
        if _ID_RE.match(base) and pages.find_by_id(root, base) is None:
            raise SystemExit(
                f"--because {ref} resolves to no page in this notebook; a stance "
                "change with an unreachable reason is the one most worth auditing "
                "later. Cite a claim, source, session or forecast that exists, or "
                "record the reasoning in --note"
            )
    record: dict = {"stance": stance, "at": util.utc_now(), "by": util.detect_actor()}
    if reasons:
        record["because"] = reasons
    if note:
        record["note"] = str(note)
    history = pages.as_list(page.fm.get("stance_history"))
    history.append(record)
    page.fm["stance"] = stance
    page.fm["stance_history"] = history

    heading = f"## Stance → {stance} ({util.today()})"
    lines = [heading, ""]
    if note:
        lines.append(note)
    if reasons:
        if note:
            lines.append("")
        lines.append(f"_Because: {', '.join(reasons)}._")
    if not note and not reasons:
        lines.append(f"_Stance moved to {stance}._")
    body = page.body.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"
    pages.write_page(page.path, page.fm, body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def set_status(
    root: Path, belief_id: str, status: str, *, note: str | None = None
) -> pages.Page:
    """Move a belief's record status: active | dormant | retracted.

    This is custody of the record of who believes what, and nothing else.
    `dormant` says we no longer observe the belief being held (or, on a
    working belief, that we have stopped pursuing it) while the record stands;
    `retracted` says we got the *believing* wrong — misattributed it, misread
    the interview, mistook one population for another.

    `retracted` requires a note, because it is the only status that asserts an
    error and the error it asserts is easy to misread as a verdict on the
    proposition. Nothing here ever says the proposition is false: that belongs
    to a Claim, which has sources and a bar.
    """
    root = util.require_notebook_root(root)
    if status not in STATUSES:
        raise SystemExit(
            f"invalid belief status '{status}' (one of: {', '.join(STATUSES)}). "
            "There is no 'verified', 'false-positive' or 'superseded' here: those "
            "are verdicts on a proposition, they live on Claim pages, and a belief "
            f"page is not where a proposition is judged — see `flip belief stance "
            f"{belief_id} …` for the notebook's relation to what is believed"
        )
    page = _find_belief(root, belief_id)
    if status == "retracted" and not (note or "").strip():
        raise SystemExit(
            f"retracting {belief_id} needs --note; retraction is the one status that "
            "asserts an error, and the error is in our record of the BELIEVING — "
            "misattributed, misread, wrong population. Say which, so nobody later "
            "reads it as the proposition having been disproved"
        )
    page.fm["status"] = status
    entry: dict = {"status": status, "at": util.utc_now(), "by": util.detect_actor()}
    if note:
        entry["note"] = str(note)
    history = pages.as_list(page.fm.get("status_history"))
    history.append(entry)
    page.fm["status_history"] = history
    pages.write_page(page.path, page.fm, page.body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


def link_about(root: Path, belief_id: str, claim_id: str | None) -> pages.Page:
    """Point a belief at the Claim stating its proposition as a fact about the
    world (or clear the link with `claim_id=None`).

    A pointer, deliberately inert: linking never changes the claim's status,
    never adds to its corroboration, and never lets the belief's measurement
    sources count toward it. What it buys is that both records are reachable
    from either side, which is the whole ask — hold the belief and the fact at
    once, and let a reader see which is which.

    Linking after the fact is the normal case: the claim usually exists first,
    and the belief is recognized as a separate object later.
    """
    root = util.require_notebook_root(root)
    page = _find_belief(root, belief_id)
    if claim_id is None:
        if "about" not in page.fm:
            raise SystemExit(f"belief {belief_id} points at no claim; nothing to clear")
        page.fm.pop("about")
    else:
        page.fm = _set_before(page.fm, "about", _check_about(root, claim_id), "stance")
    pages.write_page(page.path, page.fm, page.body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


def list_beliefs(
    root: Path, belief_kind: str | None = None, stance: str | None = None
) -> list[dict]:
    """Every belief as a frontmatter dict (+ slug, root-relative path, and the
    linked claim's status under `about_status` when `about` resolves), id
    order. Read-only.

    `about_status` is computed, never stored: the claim owns its own status,
    and a belief page storing a copy would be the second record of the world
    side that `about` exists to avoid.
    """
    if belief_kind is not None and belief_kind not in BELIEF_KINDS:
        raise SystemExit(
            f"invalid belief kind '{belief_kind}' (one of: {', '.join(BELIEF_KINDS)})"
        )
    if stance is not None and stance not in STANCES:
        raise SystemExit(f"invalid stance '{stance}' (one of: {', '.join(STANCES)})")
    claim_status = {
        p.id: str(p.fm.get("status", ""))
        for p in pages.iter_pages(root, "claims")
        if p.id and p.fm.get("type") == "Claim"
    }
    out = []
    for page in belief_pages(root):
        if belief_kind is not None and page.fm.get("belief_kind") != belief_kind:
            continue
        if stance is not None and page.fm.get("stance") != stance:
            continue
        row = {
            **page.fm,
            "slug": page.slug,
            "path": page.path.relative_to(root).as_posix(),
        }
        about = str(page.fm.get("about") or "")
        if about and about in claim_status:
            row["about_status"] = claim_status[about]
        out.append(row)
    return sorted(out, key=_id_sort_key)
