"""Tests for flip.ledgers — work log, passed ledger, decision and question pages."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flip import ledgers, pages, util
from flip.manifest import load_manifest

ROOT_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: t
kind: scout
status: active
created: 2020-01-01
updated: 2020-01-01
visibility: internal
renders_public: false
source_trail_public: false
citation_rule: public-terminus
---
# t
"""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "human:test")
    (tmp_path / "index.md").write_text(ROOT_MD, encoding="utf-8")
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


def test_add_decision_creates_page_with_sequential_ids(root: Path):
    p1 = ledgers.add_decision(root, "q1?", "use jsonl", "because")
    p2 = ledgers.add_decision(root, "q2?", "skip toml", "reasons")
    assert (p1.id, p2.id) == ("D1", "D2")
    assert p1.path == root / "decisions" / "use-jsonl.md"
    page = pages.read_page(p1.path)
    assert page.fm["type"] == "Decision"
    assert page.fm["id"] == "D1"
    assert page.fm["aliases"] == ["D1"]
    assert page.fm["description"] == "use jsonl"
    assert page.fm["question"] == "q1?"
    assert page.fm["actor"] == "human:test"
    assert page.fm["timestamp"].endswith("Z")
    assert "alternatives_rejected" not in page.fm
    assert load_manifest(root).updated == util.today()


def test_add_decision_body_paragraphs(root: Path):
    p = ledgers.add_decision(root, "store format?", "use jsonl", "diffable")
    body = pages.read_page(p.path).body
    assert "**Question.** store format?" in body
    assert "**Decision.** use jsonl" in body
    assert "**Why.** diffable" in body
    assert "**Rejected.**" not in body  # only present when alternatives given


def test_add_decision_ids_never_reused(root: Path):
    # a pre-existing page holding D5 reserves everything up to it
    pages.write_page(
        root / "decisions" / "old-choice.md",
        {"type": "Decision", "id": "D5", "aliases": ["D5"]},
        "old\n",
    )
    assert ledgers.add_decision(root, "new?", "yes", "because").id == "D6"


def test_add_decision_slug_from_text_with_collision_suffix(root: Path):
    p1 = ledgers.add_decision(root, "q?", "Use JSONL", "a")
    p2 = ledgers.add_decision(root, "q2?", "use jsonl!", "b")
    assert p1.path.name == "use-jsonl.md"
    assert p2.path.name == "use-jsonl-2.md"
    assert (p1.id, p2.id) == ("D1", "D2")


def test_add_decision_alternatives_rejected(root: Path):
    p = ledgers.add_decision(root, "q?", "a", "w", alternatives_rejected=["b", "c"])
    assert p.fm["alternatives_rejected"] == ["b", "c"]
    assert "**Rejected.** b; c" in pages.read_page(p.path).body
    # a bare string is wrapped into a list
    p2 = ledgers.add_decision(root, "q?", "a2", "w", alternatives_rejected="b")
    assert p2.fm["alternatives_rejected"] == ["b"]


def test_add_decision_long_text_truncates_description(root: Path):
    p = ledgers.add_decision(root, "q?", "word " * 60, "w")
    assert len(p.fm["description"]) <= 160
    assert p.fm["description"].endswith("…")
    # the full decision text still lives in the body
    assert "word word" in pages.read_page(p.path).body


def test_add_decision_empty_why_raises(root: Path):
    with pytest.raises(SystemExit, match="empty why"):
        ledgers.add_decision(root, "q?", "a", "")
    assert not (root / "decisions").exists()


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
    p = ledgers.add_question(root, "who funded it?")
    assert p.id == "Q1"
    assert p.path == root / "questions" / "who-funded-it.md"
    page = pages.read_page(p.path)
    assert page.fm["type"] == "Question"
    assert page.fm["aliases"] == ["Q1"]
    assert page.fm["status"] == "open"
    assert page.fm["description"] == "who funded it?"
    assert page.fm["actor"] == "human:test"
    assert page.fm["timestamp"].endswith("Z")
    assert page.body.strip() == "who funded it?"
    assert ledgers.add_question(root, "when?").id == "Q2"


def test_answer_question_updates_frontmatter_keeps_body(root: Path):
    asked = ledgers.add_question(root, "who?")
    got = ledgers.answer_question(root, "Q1")
    page = pages.read_page(got.path)
    assert page.fm["status"] == "answered"
    assert page.fm["answered"].endswith("Z")
    assert page.fm["answered_by"] == "human:test"
    assert page.fm["timestamp"] == asked.fm["timestamp"]  # ask time untouched
    assert page.body.strip() == "who?"  # body untouched without a note


def test_answer_question_note_appends_answer_section(root: Path):
    ledgers.add_question(root, "who?")
    got = ledgers.answer_question(root, "Q1", note="the foundation")
    body = pages.read_page(got.path).body
    assert "who?" in body
    assert body.rstrip().endswith("## Answer\nthe foundation")


def test_answer_question_preserves_foreign_frontmatter_key(root: Path):
    # round-trip rule (SPEC §6.6): a key some other tool wrote must survive
    p = ledgers.add_question(root, "who?")
    page = pages.read_page(p.path)
    page.fm["obsidian_color"] = "red"
    pages.write_page(p.path, page.fm, page.body)
    ledgers.answer_question(root, "Q1", note="found it")
    after = pages.read_page(p.path)
    assert after.fm["obsidian_color"] == "red"
    assert after.fm["status"] == "answered"
    assert "who?" in after.body


def test_question_ids_never_reused_after_answer(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.answer_question(root, "Q1")
    assert ledgers.add_question(root, "two?").id == "Q2"


def test_question_id_not_reused_after_page_deletion(root: Path):
    # SPEC §9: deleting a page never frees its id — the .flip/ids reservation
    # file backstops allocation for pages with no provenance trail
    p = ledgers.add_question(root, "one?")
    p.path.unlink()
    assert ledgers.add_question(root, "two?").id == "Q2"


def test_decision_id_not_reused_after_page_deletion(root: Path):
    p = ledgers.add_decision(root, "scope?", "first pass", "time-boxed")
    p.path.unlink()
    second = ledgers.add_decision(root, "scope?", "second pass", "still time-boxed")
    assert second.id == "D2"
    assert "D1" in (root / ".flip" / "ids").read_text(encoding="utf-8").splitlines()


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


def test_open_questions_excludes_answered(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.add_question(root, "two?")
    ledgers.answer_question(root, "Q1")
    open_qs = ledgers.open_questions(root)
    assert [q["id"] for q in open_qs] == ["Q2"]
    assert open_qs[0]["text"] == "two?"


def test_open_questions_empty_when_no_pages(root: Path):
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
    assert rows[0]["path"] == "questions/one.md"


def test_list_questions_status_filter(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.add_question(root, "two?")
    ledgers.answer_question(root, "Q1")
    assert [r["id"] for r in ledgers.list_questions(root, status="answered")] == ["Q1"]
    assert [r["id"] for r in ledgers.list_questions(root, status="open")] == ["Q2"]


def test_list_questions_text_excludes_answer_section(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.answer_question(root, "Q1", note="them")
    assert ledgers.list_questions(root)[0]["text"] == "who?"


def test_list_questions_empty_when_no_pages(root: Path):
    assert ledgers.list_questions(root) == []
