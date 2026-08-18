"""Work log, negative evidence, decisions, questions (SPEC §7, §8).

Two kinds of record live here, per the v0.4 split:

- **Event ledgers** — append-only JSONL under log/: log/log.jsonl (the work
  log) and log/passed.jsonl (considered-and-rejected). Written exclusively
  with util.append_jsonl; one event per line, every line carries `ts`
  (ISO-8601 UTC) and `actor`. Never rewritten.
- **Entity pages** — decisions/<slug>.md and questions/<slug>.md, one
  markdown file per entity with YAML frontmatter, the canonical record.
  Filenames are human slugs; the immutable compact id (D#/Q#) lives in
  frontmatter with `aliases: [<id>]`. History is git's job (pages are
  current-state); ids are still never reused — allocation goes through
  pages.allocate_id, which counts every id in the notebook and records the
  grant in the append-only .flip/ids reservation file.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import manifest, pages, util, views

LOG = Path("log") / "log.jsonl"
PASSED = Path("log") / "passed.jsonl"

DESCRIPTION_LIMIT = 160

_ID_NUM = re.compile(r"(\d+)$")


def _require_text(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise SystemExit(f"empty {what}; pass a non-empty {what} string")
    return value


def _description(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """One-line frontmatter description: whitespace collapsed, ≤`limit` chars."""
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _finish(root: Path, changed: tuple[str, ...] | None = None) -> None:
    """Common tail of every mutation: bump the manifest's `updated`, then
    refresh the generated views (index.md bodies, log.md — SPEC §10).

    `changed` narrows the refresh to the entity dirs the mutation touched
    (views.regenerate); None keeps the full rebuild."""
    manifest.touch_updated(root)
    views.regenerate(root, changed=changed)


# --- event ledgers (append-only JSONL) ----------------------------------------


def log_event(root: Path, text: str) -> dict:
    """Append one work-log event to log/log.jsonl; returns the row written."""
    root = util.require_notebook_root(root)  # before any write: no stray log/ dirs
    text = _require_text(text, "log text")
    row = {"ts": util.utc_now(), "text": text, "actor": util.detect_actor()}
    util.append_jsonl(root / LOG, row)
    # A log event touches no entity page, so nothing needs recounting — this
    # call was O(every page in the notebook) purely by default (measured:
    # 19.8 s for one line at 10,300 sources).
    _finish(root, changed=())
    return row


# Where an absence claim is scoped (SPEC §8, design phase 2): only `corpus`
# may be asserted without naming surfaces — "a true statement about a corpus
# became a false statement about the world."
ABSENT_FROM = util.ABSENT_FROM  # shared with absence claims (claims.py)

# The scope verdict an evidence note passes on a question: did this evidence
# answer the question as worded, a narrower question, or an adjacent one?
# Narrower/adjacent is exactly the case where the question stays open with
# the partial answer preserved on the page (SPEC §7).
ANSWER_SCOPES = ("as-worded", "narrower", "adjacent")

# Why a retrieval probe came back empty. A zero-yield round only counts
# toward a stop decision once it carries a cause — a single dud round is
# indistinguishable from saturation without one (SPEC §7).
ZERO_YIELD_CAUSES = ("saturated", "bad-reformulation", "corpus-gap", "entity-collision")

# How a question leaves the world other than being answered. `answered`
# stays its own status with its own path (`flip question answer`).
CLOSED_REASONS = ("split", "yielded", "counter-example", "dead-end", "superseded")

# Everything a question's `status:` may say (SPEC §7). Doctor audits pages
# against this; the views deliberately show UNKNOWN statuses on the working
# roster rather than hiding them — a typo degrades to visible, never to a
# question silently missing from every surface.
QUESTION_STATUSES = ("open", "answered", "closed", "dormant")

# What a re-pose sharpened. Recorded, never scored: the axes instrument the
# journey so sharpening becomes measurable later (SPEC §7).
SHARPENED_AXES = ("scope", "falsifiability", "decomposability", "evidence-anchored")


def add_passed(
    root: Path,
    text: str,
    reason: str,
    url: str | None = None,
    absent_from: str | None = None,
    surfaces: list[str] | None = None,
) -> dict:
    """Append negative evidence — considered and rejected — to log/passed.jsonl.

    `absent_from` scopes an absence assertion (corpus | named_surfaces |
    world); anything beyond `corpus` must name the surfaces the desk can
    show an attempt against.
    """
    root = util.require_notebook_root(root)
    text = _require_text(text, "text")
    reason = _require_text(reason, "reason")
    named = [str(s) for s in (surfaces or []) if str(s).strip()]
    if absent_from is not None:
        if absent_from not in ABSENT_FROM:
            raise SystemExit(
                f"invalid absent_from '{absent_from}' (one of: {', '.join(ABSENT_FROM)})"
            )
        if absent_from != "corpus" and not named:
            raise SystemExit(
                f"absent_from '{absent_from}' asserts more than this corpus; name the "
                "surfaces checked (--surface, repeatable) or scope it to 'corpus'"
            )
    row: dict = {"ts": util.utc_now(), "text": text}
    if url:
        row["url"] = url
    row["reason"] = reason
    if absent_from:
        row["absent_from"] = absent_from
    if named:
        row["surfaces"] = named
    row["actor"] = util.detect_actor()
    util.append_jsonl(root / PASSED, row)
    # passed.jsonl feeds no generated view; like a log event, nothing to recount.
    _finish(root, changed=())
    return row


# --- decisions (entity pages) --------------------------------------------------


def add_decision(
    root: Path,
    question: str,
    decision: str,
    why: str,
    alternatives_rejected: list[str] | str | None = None,
) -> pages.Page:
    """Create decisions/<slug>.md, allocating the next D#. Returns the Page.

    The slug comes from the decision text; the id is allocated over every id
    in the notebook and reserved in .flip/ids (pages.allocate_id), so a D# is
    never reused even if its page is later deleted.
    """
    root = util.require_notebook_root(root)
    question = _require_text(question, "question")
    decision = _require_text(decision, "decision")
    why = _require_text(why, "why")
    if alternatives_rejected and isinstance(alternatives_rejected, str):
        alternatives_rejected = [alternatives_rejected]
    did = pages.allocate_id(root, "D")
    fm: dict = {
        "type": "Decision",
        "id": did,
        "aliases": [did],
        "description": _description(decision),
        "question": question,
    }
    if alternatives_rejected:
        fm["alternatives_rejected"] = [str(a) for a in alternatives_rejected]
    fm["generated"] = util.generated_now()
    paragraphs = [
        f"**Question.** {question}",
        f"**Decision.** {decision}",
        f"**Why.** {why}",
    ]
    if alternatives_rejected:
        paragraphs.append("**Rejected.** " + "; ".join(str(a) for a in alternatives_rejected))
    body = "\n\n".join(paragraphs) + "\n"
    directory = root / "decisions"
    slug = pages.unique_slug(directory, pages.slugify(decision, fallback="decision"), entity_id=did)
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    _finish(root, changed=("decisions",))
    return pages.Page(path=path, fm=fm, body=body)


# --- questions (entity pages) --------------------------------------------------


def add_question(root: Path, text: str, resolves_via: list[str] | None = None) -> pages.Page:
    """Create questions/<slug>.md with status: open, allocating the next Q#.

    `resolves_via` names the surfaces that could answer this question (L17:
    an open question without a watching surface is a wish, not a plan) —
    `flip show` marks open questions that lack one. Q#s are allocated over
    every id in the notebook and reserved in .flip/ids, so ids are never
    reused even after a question is answered or its page deleted. Returns
    the Page.
    """
    root = util.require_notebook_root(root)
    text = _require_text(text, "question text")
    qid = pages.allocate_id(root, "Q")
    fm: dict = {
        "type": "Question",
        "id": qid,
        "aliases": [qid],
        "description": _description(text),
        "status": "open",
    }
    vias = [str(s) for s in (resolves_via or []) if str(s).strip()]
    if vias:
        fm["resolves_via"] = vias
    fm["generated"] = util.generated_now()
    directory = root / "questions"
    slug = pages.unique_slug(directory, pages.slugify(text, fallback="question"), entity_id=qid)
    path = pages.write_page(directory / f"{slug}.md", fm, text + "\n")
    _finish(root, changed=("questions",))
    return pages.Page(path=path, fm=fm, body=text + "\n")


def _find_question(root: Path, qid: str) -> pages.Page:
    """The question page for `qid`, or a SystemExit naming the known ids."""
    page = pages.find_by_id(root, qid)
    if page is None:
        known = sorted(
            (p.id for p in pages.iter_pages(root, "questions") if p.id),
            key=lambda s: (len(s), s),
        )
        hint = (
            f"known: {', '.join(known)}"
            if known
            else 'none recorded yet; add one with `flip question add "<text>"`'
        )
        raise SystemExit(f"no question '{qid}' in questions/ ({hint})")
    return page


def _append_section(body: str, heading: str, text: str | None = None) -> str:
    """Append a `## <heading>` section (plus optional text) to a page body."""
    base = body.rstrip("\n")
    section = f"## {heading}" + (f"\n{text.strip()}" if text and text.strip() else "")
    return (base + "\n\n" if base else "") + section + "\n"


def _log_question_event(root: Path, event: str, qid: str, detail: str) -> None:
    util.append_jsonl(
        root / LOG,
        {
            "ts": util.utc_now(),
            "text": f'{event} {qid}: "{detail}"',
            "actor": util.detect_actor(),
        },
    )


def _set_reopen_when(fm: dict, reopen_when: list[str] | None) -> None:
    """Arm reopen triggers on a page leaving the open state.

    A trigger is a written observable condition under which the settled
    question should be looked at again — the counterpart of resolves_via:
    that names what could answer it, this names what would un-answer it.
    """
    triggers = [str(t).strip() for t in (reopen_when or []) if str(t).strip()]
    if triggers:
        fm["reopen_when"] = triggers


def answer_question(
    root: Path,
    qid: str,
    note: str | None = None,
    reopen_when: list[str] | None = None,
) -> pages.Page:
    """Mark a question answered: status → answered, plus answered/answered_by.

    Edits the page in place (round-trip rule, SPEC §6.6): only the keys this
    function owns change; foreign frontmatter keys and the body survive. When
    `note` is given it is appended to the body under an `## Answer` heading.
    `reopen_when` arms written reopen triggers (`reopen_when:` on the page) —
    the conditions under which this answer should be revisited. A closed
    question refuses answering (its end is already recorded — reopen first,
    the mirror of close_question refusing answered pages); a dormant one
    answers directly, dropping its now-stale `review_by`. The page's
    history stays recoverable through git. Returns the Page.
    """
    root = util.require_notebook_root(root)
    page = _find_question(root, qid)
    status = str(page.fm.get("status", "open"))
    if status == "answered":
        raise SystemExit(f"question {qid} is already answered; nothing to do")
    if status == "closed":
        raise SystemExit(
            f"question {qid} is closed ({page.fm.get('closed_reason', 'no reason')}); "
            f"answering would bury the close — `flip question reopen {qid} "
            f"--because …` first"
        )
    page.fm["status"] = "answered"
    page.fm["answered"] = util.utc_now()
    page.fm["answered_by"] = util.detect_actor()
    page.fm.pop("review_by", None)  # a dormancy the answer just ended
    _set_reopen_when(page.fm, reopen_when)
    body = page.body
    note = (note or "").strip()
    if note:
        base = body.rstrip("\n")
        body = (base + "\n\n" if base else "") + f"## Answer\n{note}\n"
    pages.write_page(page.path, page.fm, body)
    _log_question_event(root, "question-answer", qid,
                        _description(note) if note else "answered")
    _finish(root, changed=("questions",))
    return pages.Page(path=page.path, fm=page.fm, body=body)


def note_question(
    root: Path,
    qid: str,
    text: str,
    answers: str | None = None,
    sources: list[str] | None = None,
    zero_yield: str | None = None,
) -> pages.Page:
    """Land evidence on a question without closing it (append-only).

    Appends a dated `## Evidence` section to the page body and logs a
    `question-evidence` event. `answers` records the scope verdict — did
    this evidence answer the question as worded, a narrower one, or an
    adjacent one? A narrower/adjacent verdict is the case where the
    question STAYS open with the partial answer preserved. `zero_yield`
    records an empty probe WITH its cause (a zero round without a cause is
    indistinguishable from saturation); it excludes `answers` — an empty
    round answered nothing. `sources` cites evidence ids, refused unless
    they resolve. Works at any status: evidence arriving after an answer
    is exactly what reopen triggers watch for. Returns the Page.
    """
    root = util.require_notebook_root(root)
    text = _require_text(text, "evidence note")
    if answers is not None and answers not in ANSWER_SCOPES:
        raise SystemExit(
            f"invalid answers scope '{answers}' (one of: {', '.join(ANSWER_SCOPES)})"
        )
    if zero_yield is not None and zero_yield not in ZERO_YIELD_CAUSES:
        raise SystemExit(
            f"invalid zero-yield cause '{zero_yield}' "
            f"(one of: {', '.join(ZERO_YIELD_CAUSES)})"
        )
    if answers and zero_yield:
        raise SystemExit(
            "--answers and --zero-yield are mutually exclusive: an empty round "
            "answered nothing; record what it rules out in the note text"
        )
    cited = [str(s).strip() for s in (sources or []) if str(s).strip()]
    for sid in cited:
        if pages.find_by_id(root, sid) is None:
            raise SystemExit(f"unknown source id '{sid}'; capture it first (flip add-source)")
    page = _find_question(root, qid)
    heading = f"Evidence {util.today()}"
    if answers:
        heading += f" — answers: {answers}"
    if zero_yield:
        heading += f" — zero yield: {zero_yield}"
    section = text
    if cited:
        section += "\n\nSources: " + ", ".join(f"[{sid}]" for sid in cited)
    body = _append_section(page.body, heading, section)
    pages.write_page(page.path, page.fm, body)
    _log_question_event(root, "question-evidence", qid, _description(text))
    _finish(root, changed=("questions",))
    return pages.Page(path=page.path, fm=page.fm, body=body)


def close_question(
    root: Path,
    qid: str,
    reason: str,
    note: str | None = None,
    reopen_when: list[str] | None = None,
) -> pages.Page:
    """Close a question without an answer, with a reason from the vocabulary.

    `answered` has its own path (`flip question answer`); this records the
    other honest ends of a question's life: split into sharper questions,
    yielded to its owner, closed by a counter-example, dropped as a dead
    end, or superseded. Status → closed with `closed_reason:`; a dated
    `## Closed` section lands on the body; a `question-close` event lands
    in the log. `reopen_when` arms reopen triggers. Returns the Page.
    """
    root = util.require_notebook_root(root)
    if reason not in CLOSED_REASONS:
        raise SystemExit(
            f"invalid close reason '{reason}' (one of: {', '.join(CLOSED_REASONS)})"
        )
    page = _find_question(root, qid)
    status = str(page.fm.get("status", "open"))
    if status == "closed":
        raise SystemExit(f"question {qid} is already closed; nothing to do")
    if status == "answered":
        raise SystemExit(
            f"question {qid} is answered; closing would bury the answer — "
            f"`flip question reopen {qid} --because …` first if it needs a new end"
        )
    page.fm["status"] = "closed"
    page.fm["closed_reason"] = reason
    page.fm["closed"] = util.utc_now()
    page.fm["closed_by"] = util.detect_actor()
    page.fm.pop("review_by", None)
    _set_reopen_when(page.fm, reopen_when)
    body = _append_section(page.body, f"Closed {util.today()} — {reason}", note)
    pages.write_page(page.path, page.fm, body)
    _log_question_event(root, "question-close", qid, reason)
    _finish(root, changed=("questions",))
    return pages.Page(path=page.path, fm=page.fm, body=body)


def dormant_question(
    root: Path, qid: str, until: str, note: str | None = None
) -> pages.Page:
    """Park an open question with a review date (status → dormant).

    Dormant is not dead: `review_by:` names the date the question resurfaces
    in `flip show` ("review due"). Only an open question can go dormant —
    answered and closed pages already have their end recorded. Returns the
    Page.
    """
    root = util.require_notebook_root(root)
    until = _require_text(until, "review date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", until):
        raise SystemExit(f"invalid review date '{until}' (expected YYYY-MM-DD)")
    try:
        date.fromisoformat(until)
    except ValueError:
        raise SystemExit(
            f"invalid review date '{until}' (no such calendar date)"
        ) from None
    page = _find_question(root, qid)
    status = str(page.fm.get("status", "open"))
    if status != "open":
        raise SystemExit(
            f"question {qid} is {status}; only an open question can go dormant"
        )
    page.fm["status"] = "dormant"
    page.fm["review_by"] = until
    body = _append_section(page.body, f"Dormant {util.today()} — review by {until}", note)
    pages.write_page(page.path, page.fm, body)
    _log_question_event(root, "question-dormant", qid, f"review by {until}")
    _finish(root, changed=("questions",))
    return pages.Page(path=page.path, fm=page.fm, body=body)


def reopen_question(root: Path, qid: str, because: str) -> pages.Page:
    """Reopen a settled question (answered/closed/dormant → open).

    `because` names which trigger fired or what changed — it lands in a
    dated `## Reopened` section and the log. Current-state keys that
    described the settled state (answered/closed timestamps, closed_reason,
    review_by) are removed; the body keeps every prior section, so the
    journey — answer included — survives on the page. Armed `reopen_when`
    triggers stay armed. Returns the Page.
    """
    root = util.require_notebook_root(root)
    because = _require_text(because, "reason")
    page = _find_question(root, qid)
    status = str(page.fm.get("status", "open"))
    if status == "open":
        raise SystemExit(f"question {qid} is already open; nothing to do")
    page.fm["status"] = "open"
    for key in ("answered", "answered_by", "closed", "closed_by", "closed_reason", "review_by"):
        page.fm.pop(key, None)
    body = _append_section(page.body, f"Reopened {util.today()}", because)
    pages.write_page(page.path, page.fm, body)
    _log_question_event(root, "question-reopen", qid, _description(because))
    _finish(root, changed=("questions",))
    return pages.Page(path=page.path, fm=page.fm, body=body)


def repose_question(
    root: Path,
    qid: str,
    new_text: str,
    sharpened: list[str] | None = None,
    note: str | None = None,
) -> pages.Page:
    """Re-pose a question with a fresh formulation (A3), append-only.

    The id, slug, and status stay. The new formulation becomes the current
    description and the body's lead text; the superseded formulation is
    appended both to a `formulations:` history list in frontmatter
    ({text, date, actor}) and to a dated "Re-posed" section in the body, and a
    `question-repose` event lands in log/log.jsonl. `sharpened` tags which
    axes the re-pose sharpened (recorded on the history entry, never scored —
    the instrumentation that makes sharpening measurable later); `note` says
    how. Nothing is overwritten — `flip open Q#` always shows the full
    journey. Returns the Page.
    """
    root = util.require_notebook_root(root)
    new_text = _require_text(new_text, "new formulation")
    axes = [str(a).strip() for a in (sharpened or []) if str(a).strip()]
    for axis in axes:
        if axis not in SHARPENED_AXES:
            raise SystemExit(
                f"invalid sharpened axis '{axis}' (one of: {', '.join(SHARPENED_AXES)})"
            )
    page = _find_question(root, qid)

    # The current formulation is the body's lead text — everything up to the
    # first '##' section (prior Re-posed blocks, ## Answer). That tail is
    # preserved verbatim below the newest Re-posed section.
    lines = page.body.split("\n")
    cut = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), None)
    old_text = ("\n".join(lines if cut is None else lines[:cut])).strip()
    # A body may open directly on a '##' section (an answered or foreign-
    # edited page); the description still holds the prior formulation, and
    # it is about to be overwritten — capture it, never record ''.
    if not old_text:
        old_text = str(page.fm.get("description", ""))
    tail = "" if cut is None else "\n".join(lines[cut:]).strip("\n")

    formulations = pages.as_list(page.fm.get("formulations"))
    entry: dict = {"text": old_text, "date": util.today(), "actor": util.detect_actor()}
    if axes:
        entry["sharpened"] = axes
    if note and note.strip():
        entry["note"] = note.strip()
    formulations.append(entry)
    page.fm["formulations"] = formulations
    page.fm["description"] = _description(new_text)

    parts = [new_text.strip(), f"## Re-posed {util.today()}\n\n{old_text}"]
    if tail:
        parts.append(tail)
    body = "\n\n".join(parts) + "\n"
    pages.write_page(page.path, page.fm, body)
    util.append_jsonl(
        root / LOG,
        {
            "ts": util.utc_now(),
            "text": f'question-repose {qid}: "{_description(new_text)}"',
            "actor": util.detect_actor(),
        },
    )
    _finish(root, changed=("questions",))
    return pages.Page(path=page.path, fm=page.fm, body=body)


def _question_text(page: pages.Page) -> str:
    """The current question text: the body's lead prose, up to the first '##'
    section (## Answer, or a dated ## Re-posed block from a re-pose), else the
    description. So a re-posed question lists its current formulation, not its
    whole journey — the journey stays on the page."""
    body = page.body
    if body.lstrip().startswith("## "):
        return str(page.fm.get("description", ""))
    head = body.split("\n## ", 1)[0].strip()
    return head or str(page.fm.get("description", ""))


def _id_num(entity_id: str) -> int:
    m = _ID_NUM.search(entity_id)
    return int(m.group(1)) if m else 0


def list_questions(root: Path, status: str | None = None) -> list[dict]:
    """Every question page as a plain dict, in ask (id) order.

    Read-only projection over questions/ (backs `flip question list`). Each
    dict carries id, slug, path (root-relative posix), text, status, ts, and
    actor. Pass `status` to filter (e.g. "open", "answered").
    """
    rows = []
    for page in pages.iter_pages(root, "questions"):
        if str(page.fm.get("type", "")) != "Question":
            continue
        row = {
            "id": page.id,
            "slug": page.slug,
            "path": page.path.relative_to(root).as_posix(),
            "text": _question_text(page),
            "status": str(page.fm.get("status", "open")),
            "ts": pages.generated_at(page.fm),
            "actor": pages.generated_by(page.fm),
        }
        for key in ("closed_reason", "review_by"):
            if page.fm.get(key):
                row[key] = str(page.fm[key])
        triggers = [str(t) for t in pages.as_list(page.fm.get("reopen_when"))]
        if triggers:
            row["reopen_when"] = triggers
        rows.append(row)
    rows.sort(key=lambda r: _id_num(r["id"]))
    if status is not None:
        rows = [r for r in rows if r["status"] == status]
    return rows


def open_questions(root: Path) -> list[dict]:
    """Questions still needing work: everything not settled (answered/closed).

    Read-only projection over questions/ (used by views); ask order. Dormant
    rows carry `review_by` so a view can say whether the review is due. A
    status outside the vocabulary counts as needing work on purpose: a typo
    must degrade to visible, never to a question missing from every surface
    (doctor names the bad enum; the roster keeps showing the question).
    """
    return [q for q in list_questions(root)
            if q["status"] not in ("answered", "closed")]
