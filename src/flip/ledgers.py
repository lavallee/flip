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


def _finish(root: Path) -> None:
    """Common tail of every mutation: bump the manifest's `updated`, then
    refresh the generated views (index.md bodies, log.md — SPEC §10)."""
    manifest.touch_updated(root)
    views.regenerate(root)


# --- event ledgers (append-only JSONL) ----------------------------------------


def log_event(root: Path, text: str) -> dict:
    """Append one work-log event to log/log.jsonl; returns the row written."""
    root = util.require_notebook_root(root)  # before any write: no stray log/ dirs
    text = _require_text(text, "log text")
    row = {"ts": util.utc_now(), "text": text, "actor": util.detect_actor()}
    util.append_jsonl(root / LOG, row)
    _finish(root)
    return row


def add_passed(root: Path, text: str, reason: str, url: str | None = None) -> dict:
    """Append negative evidence — considered and rejected — to log/passed.jsonl."""
    root = util.require_notebook_root(root)
    text = _require_text(text, "text")
    reason = _require_text(reason, "reason")
    row: dict = {"ts": util.utc_now(), "text": text}
    if url:
        row["url"] = url
    row["reason"] = reason
    row["actor"] = util.detect_actor()
    util.append_jsonl(root / PASSED, row)
    _finish(root)
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
    fm["timestamp"] = util.utc_now()
    fm["actor"] = util.detect_actor()
    paragraphs = [
        f"**Question.** {question}",
        f"**Decision.** {decision}",
        f"**Why.** {why}",
    ]
    if alternatives_rejected:
        paragraphs.append("**Rejected.** " + "; ".join(str(a) for a in alternatives_rejected))
    body = "\n\n".join(paragraphs) + "\n"
    directory = root / "decisions"
    slug = pages.unique_slug(directory, pages.slugify(decision, fallback="decision"))
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    _finish(root)
    return pages.Page(path=path, fm=fm, body=body)


# --- questions (entity pages) --------------------------------------------------


def add_question(root: Path, text: str) -> pages.Page:
    """Create questions/<slug>.md with status: open, allocating the next Q#.

    Q#s are allocated over every id in the notebook and reserved in
    .flip/ids, so ids are never reused even after a question is answered or
    its page deleted. Returns the Page.
    """
    root = util.require_notebook_root(root)
    text = _require_text(text, "question text")
    qid = pages.allocate_id(root, "Q")
    fm = {
        "type": "Question",
        "id": qid,
        "aliases": [qid],
        "description": _description(text),
        "status": "open",
        "timestamp": util.utc_now(),
        "actor": util.detect_actor(),
    }
    directory = root / "questions"
    slug = pages.unique_slug(directory, pages.slugify(text, fallback="question"))
    path = pages.write_page(directory / f"{slug}.md", fm, text + "\n")
    _finish(root)
    return pages.Page(path=path, fm=fm, body=text + "\n")


def answer_question(root: Path, qid: str, note: str | None = None) -> pages.Page:
    """Mark a question answered: status → answered, plus answered/answered_by.

    Edits the page in place (round-trip rule, SPEC §6.6): only the keys this
    function owns change; foreign frontmatter keys and the body survive. When
    `note` is given it is appended to the body under an `## Answer` heading.
    The page's history stays recoverable through git. Returns the Page.
    """
    root = util.require_notebook_root(root)
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
    if page.fm.get("status") == "answered":
        raise SystemExit(f"question {qid} is already answered; nothing to do")
    page.fm["status"] = "answered"
    page.fm["answered"] = util.utc_now()
    page.fm["answered_by"] = util.detect_actor()
    body = page.body
    note = (note or "").strip()
    if note:
        base = body.rstrip("\n")
        body = (base + "\n\n" if base else "") + f"## Answer\n{note}\n"
    pages.write_page(page.path, page.fm, body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def _question_text(page: pages.Page) -> str:
    """The question text: the body up to any ## Answer, else the description."""
    body = page.body
    if body.startswith("## Answer"):
        body = ""
    body = body.split("\n## Answer", 1)[0].strip()
    return body or str(page.fm.get("description", ""))


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
        rows.append(
            {
                "id": page.id,
                "slug": page.slug,
                "path": page.path.relative_to(root).as_posix(),
                "text": _question_text(page),
                "status": str(page.fm.get("status", "open")),
                "ts": str(page.fm.get("timestamp", "")),
                "actor": str(page.fm.get("actor", "")),
            }
        )
    rows.sort(key=lambda r: _id_num(r["id"]))
    if status is not None:
        rows = [r for r in rows if r["status"] == status]
    return rows


def open_questions(root: Path) -> list[dict]:
    """Questions not yet answered (anything but status "answered" needs work).

    Read-only projection over questions/ (used by views); ask order.
    """
    return [q for q in list_questions(root) if q["status"] != "answered"]
