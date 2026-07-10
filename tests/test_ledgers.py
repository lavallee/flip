"""Tests for flip.ledgers — log, decisions, passed, questions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flip import ledgers, util
from flip.manifest import load_manifest

MANIFEST = """\
slug = "t"
kind = "scout"
status = "active"
created = "2020-01-01"
updated = "2020-01-01"
"""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "human:test")
    (tmp_path / "notebook.toml").write_text(MANIFEST, encoding="utf-8")
    return tmp_path


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --- log_event ---------------------------------------------------------------


def test_log_event_appends_row(root: Path):
    row = ledgers.log_event(root, "fetched X")
    assert row["text"] == "fetched X"
    assert row["actor"] == "human:test"
    assert row["ts"].endswith("Z")
    assert _lines(root / "log" / "log.jsonl") == [row]


def test_log_event_touches_manifest_updated(root: Path):
    ledgers.log_event(root, "hi")
    assert load_manifest(root).updated == util.today()


def test_log_event_empty_text_raises(root: Path):
    with pytest.raises(SystemExit, match="empty log text"):
        ledgers.log_event(root, "   ")


def test_log_event_outside_notebook_raises_and_writes_nothing(tmp_path: Path):
    outside = tmp_path / "not-a-notebook"
    outside.mkdir()
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        ledgers.log_event(outside, "hi")
    # validation must run BEFORE the append: no stray log/ dir left behind
    assert not (outside / "log").exists()


def test_all_mutators_outside_notebook_raise_and_write_nothing(tmp_path: Path):
    outside = tmp_path / "bare"
    outside.mkdir()
    for call in (
        lambda: ledgers.add_decision(outside, "q?", "a", "w"),
        lambda: ledgers.add_passed(outside, "thing", "reason"),
        lambda: ledgers.add_question(outside, "q?"),
        lambda: ledgers.answer_question(outside, "Q1"),
    ):
        with pytest.raises(SystemExit, match="not inside a flip notebook"):
            call()
    assert list(outside.iterdir()) == []


# --- add_decision ------------------------------------------------------------


def test_add_decision_allocates_sequential_ids(root: Path):
    r1 = ledgers.add_decision(root, "q1?", "yes", "because")
    r2 = ledgers.add_decision(root, "q2?", "no", "reasons")
    assert (r1["id"], r2["id"]) == ("D1", "D2")
    rows = _lines(root / "log" / "decisions.jsonl")
    assert [r["id"] for r in rows] == ["D1", "D2"]
    assert rows[0]["question"] == "q1?"
    assert rows[0]["decision"] == "yes"
    assert rows[0]["why"] == "because"
    assert rows[0]["actor"] == "human:test"
    assert "alternatives_rejected" not in rows[0]


def test_add_decision_ids_never_reused(root: Path):
    util.append_jsonl(
        root / "log" / "decisions.jsonl",
        {"ts": "2020-01-01T00:00:00Z", "id": "D5", "question": "old", "decision": "x",
         "why": "y", "actor": "human:test"},
    )
    row = ledgers.add_decision(root, "new?", "yes", "because")
    assert row["id"] == "D6"


def test_add_decision_alternatives_rejected(root: Path):
    row = ledgers.add_decision(root, "q?", "a", "w", alternatives_rejected=["b", "c"])
    assert row["alternatives_rejected"] == ["b", "c"]
    # a bare string is wrapped into a list
    row2 = ledgers.add_decision(root, "q?", "a", "w", alternatives_rejected="b")
    assert row2["alternatives_rejected"] == ["b"]


def test_add_decision_empty_why_raises(root: Path):
    with pytest.raises(SystemExit, match="empty why"):
        ledgers.add_decision(root, "q?", "a", "")


# --- add_passed --------------------------------------------------------------


def test_add_passed_with_and_without_url(root: Path):
    r1 = ledgers.add_passed(root, "vendor blog", "self-interested", url="https://x.example")
    r2 = ledgers.add_passed(root, "old dataset", "superseded by 2026 release")
    rows = _lines(root / "log" / "passed.jsonl")
    assert rows == [r1, r2]
    assert rows[0]["url"] == "https://x.example"
    assert "url" not in rows[1]
    assert rows[1]["reason"] == "superseded by 2026 release"


def test_add_passed_empty_reason_raises(root: Path):
    with pytest.raises(SystemExit, match="empty reason"):
        ledgers.add_passed(root, "thing", "")


# --- questions ---------------------------------------------------------------


def test_add_question_opens_with_id(root: Path):
    row = ledgers.add_question(root, "who funded it?")
    assert row["id"] == "Q1"
    assert row["status"] == "open"
    assert ledgers.add_question(root, "when?")["id"] == "Q2"


def test_answer_question_appends_never_rewrites(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.answer_question(root, "Q1")
    rows = _lines(root / "log" / "questions.jsonl")
    assert len(rows) == 2
    assert rows[0]["status"] == "open"  # original ask row untouched
    assert rows[0]["text"] == "who?"
    assert rows[1] == {"ts": rows[1]["ts"], "id": "Q1", "status": "answered",
                       "actor": "human:test"}


def test_question_ids_never_reused_after_answer(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.answer_question(root, "Q1")
    assert ledgers.add_question(root, "two?")["id"] == "Q2"


def test_answer_unknown_question_raises(root: Path):
    ledgers.add_question(root, "one?")
    with pytest.raises(SystemExit, match=r"no question 'Q9'.*known: Q1"):
        ledgers.answer_question(root, "Q9")


def test_answer_question_none_recorded_hint_names_the_add_subcommand(root: Path):
    with pytest.raises(SystemExit) as ei:
        ledgers.answer_question(root, "Q1")
    msg = str(ei.value)
    assert "none recorded yet" in msg
    # the hint must name the real command — `flip question add`, not `flip question`
    assert 'flip question add "<text>"' in msg


def test_answer_question_twice_raises(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.answer_question(root, "Q1")
    with pytest.raises(SystemExit, match="already answered"):
        ledgers.answer_question(root, "Q1")


def test_open_questions_last_event_wins(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.add_question(root, "two?")
    ledgers.answer_question(root, "Q1")
    open_qs = ledgers.open_questions(root)
    assert [q["id"] for q in open_qs] == ["Q2"]
    assert open_qs[0]["text"] == "two?"


def test_open_questions_empty_when_no_ledger(root: Path):
    assert ledgers.open_questions(root) == []


def test_list_questions_reports_current_status(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.add_question(root, "two?")
    ledgers.answer_question(root, "Q1")
    rows = ledgers.list_questions(root)
    assert [(r["id"], r["status"], r["text"]) for r in rows] == [
        ("Q1", "answered", "one?"),
        ("Q2", "open", "two?"),
    ]


def test_list_questions_empty_when_no_ledger(root: Path):
    assert ledgers.list_questions(root) == []
