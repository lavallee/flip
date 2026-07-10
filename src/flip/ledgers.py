"""Work-log ledgers: log, decisions, passed, questions (SPEC §8).

Everything under log/*.jsonl is append-only JSONL, written exclusively with
util.append_jsonl; one event per line, every line carries `ts` (ISO-8601 UTC)
and `actor`.

questions.jsonl is append-only like its siblings: answering a question never
rewrites the file. `add_question` appends {ts, id, text, actor, status:
"open"}; `answer_question` appends a second event {ts, id, status:
"answered", actor}. A question's current status is the status of the LAST
event bearing its id — the open questions are the ids whose last event isn't
"answered" (see `open_questions`).
"""

from __future__ import annotations

from pathlib import Path

from . import manifest, util

LOG = Path("log") / "log.jsonl"
DECISIONS = Path("log") / "decisions.jsonl"
PASSED = Path("log") / "passed.jsonl"
QUESTIONS = Path("log") / "questions.jsonl"


def _require_text(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise SystemExit(f"empty {what}; pass a non-empty {what} string")
    return value


def log_event(root: Path, text: str) -> dict:
    """Append one work-log event to log/log.jsonl; returns the row written."""
    root = util.require_notebook_root(root)  # before any write: no stray log/ dirs
    text = _require_text(text, "log text")
    row = {"ts": util.utc_now(), "text": text, "actor": util.detect_actor()}
    util.append_jsonl(root / LOG, row)
    manifest.touch_updated(root)
    return row


def add_decision(
    root: Path,
    question: str,
    decision: str,
    why: str,
    alternatives_rejected: list[str] | str | None = None,
) -> dict:
    """Append a decision to log/decisions.jsonl, allocating the next D#.

    Ids are allocated over every row ever written (append-only ledger), so a
    D# is never reused. Returns the row written.
    """
    root = util.require_notebook_root(root)
    question = _require_text(question, "question")
    decision = _require_text(decision, "decision")
    why = _require_text(why, "why")
    existing = [r.get("id", "") for r in util.read_jsonl(root / DECISIONS)]
    row: dict = {
        "ts": util.utc_now(),
        "id": util.next_id("D", existing),
        "question": question,
        "decision": decision,
        "why": why,
    }
    if alternatives_rejected:
        if isinstance(alternatives_rejected, str):
            alternatives_rejected = [alternatives_rejected]
        row["alternatives_rejected"] = list(alternatives_rejected)
    row["actor"] = util.detect_actor()
    util.append_jsonl(root / DECISIONS, row)
    manifest.touch_updated(root)
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
    manifest.touch_updated(root)
    return row


def add_question(root: Path, text: str) -> dict:
    """Append an open question to log/questions.jsonl, allocating the next Q#.

    Q#s are allocated over every event ever written, so ids are never reused
    even after a question is answered.
    """
    root = util.require_notebook_root(root)
    text = _require_text(text, "question text")
    events = util.read_jsonl(root / QUESTIONS)
    qid = util.next_id("Q", [e.get("id", "") for e in events])
    row = {
        "ts": util.utc_now(),
        "id": qid,
        "text": text,
        "actor": util.detect_actor(),
        "status": "open",
    }
    util.append_jsonl(root / QUESTIONS, row)
    manifest.touch_updated(root)
    return row


def answer_question(root: Path, qid: str) -> dict:
    """Mark a question answered by APPENDING {ts, id, status: "answered", actor}.

    questions.jsonl is append-only; the original ask row is never touched. The
    last event per id wins when computing current status.
    """
    root = util.require_notebook_root(root)
    events = util.read_jsonl(root / QUESTIONS)
    last = None
    for e in events:
        if e.get("id") == qid:
            last = e
    if last is None:
        known = sorted({e.get("id") for e in events if e.get("id")})
        hint = (
            f"known: {', '.join(known)}"
            if known
            else 'none recorded yet; add one with `flip question add "<text>"`'
        )
        raise SystemExit(f"no question '{qid}' in log/questions.jsonl ({hint})")
    if last.get("status") == "answered":
        raise SystemExit(f"question {qid} is already answered; nothing to do")
    row = {"ts": util.utc_now(), "id": qid, "status": "answered", "actor": util.detect_actor()}
    util.append_jsonl(root / QUESTIONS, row)
    manifest.touch_updated(root)
    return row


def list_questions(root: Path) -> list[dict]:
    """Every question with its CURRENT status (last event per id wins).

    Read-only projection over log/questions.jsonl (backs `flip question
    list`): one dict per question in ask order — the original ask row with
    `status` replaced by the current one.
    """
    events = util.read_jsonl(root / QUESTIONS)
    asked: dict[str, dict] = {}
    status: dict[str, str] = {}
    for e in events:
        qid = e.get("id")
        if not qid:
            continue
        asked.setdefault(qid, e)
        status[qid] = e.get("status", status.get(qid, "open"))
    return [{**row, "status": status[qid]} for qid, row in asked.items()]


def open_questions(root: Path) -> list[dict]:
    """Questions whose LAST event isn't "answered", as their original ask rows.

    Read-only projection over log/questions.jsonl (used by views); returns
    rows in ask order.
    """
    return [q for q in list_questions(root) if q["status"] != "answered"]
