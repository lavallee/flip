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
    assert pages.generated_by(page.fm) == "human:test"
    assert pages.generated_at(page.fm).endswith("Z")
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
    assert p2.path.name == "d2-use-jsonl.md"
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
    assert pages.generated_by(page.fm) == "human:test"
    assert pages.generated_at(page.fm).endswith("Z")
    assert page.body.strip() == "who funded it?"
    assert ledgers.add_question(root, "when?").id == "Q2"


def test_answer_question_updates_frontmatter_keeps_body(root: Path):
    asked = ledgers.add_question(root, "who?")
    got = ledgers.answer_question(root, "Q1")
    page = pages.read_page(got.path)
    assert page.fm["status"] == "answered"
    assert page.fm["answered"].endswith("Z")
    assert page.fm["answered_by"] == "human:test"
    assert pages.generated_at(page.fm) == pages.generated_at(asked.fm)  # ask time untouched
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


# --- repose (append-only re-pose) --------------------------------------------


def test_repose_keeps_id_slug_status_and_updates_current_text(root: Path):
    asked = ledgers.add_question(root, "who funded it?")
    got = ledgers.repose_question(root, "Q1", "who funded it, and through what vehicle?")
    page = pages.read_page(got.path)
    assert page.id == "Q1"  # id never changes
    assert page.path == asked.path  # slug (filename) never changes
    assert page.fm["status"] == "open"  # status untouched
    assert page.fm["description"] == "who funded it, and through what vehicle?"
    # the new formulation is the body's lead text
    assert page.body.lstrip("\n").startswith("who funded it, and through what vehicle?")


def test_repose_preserves_old_text_verbatim_in_history_and_body(root: Path):
    ledgers.add_question(root, "who funded it?")
    got = ledgers.repose_question(root, "Q1", "who really funded it?")
    page = pages.read_page(got.path)
    # frontmatter history: the superseded formulation, verbatim, dated, attributed
    hist = page.fm["formulations"]
    assert hist == [{"text": "who funded it?", "date": util.today(), "actor": "human:test"}]
    # body: a dated Re-posed section carrying the old text verbatim
    assert f"## Re-posed {util.today()}" in page.body
    assert "who funded it?" in page.body


def test_repose_is_append_only_across_multiple_reposes(root: Path):
    ledgers.add_question(root, "v1?")
    ledgers.repose_question(root, "Q1", "v2?")
    got = ledgers.repose_question(root, "Q1", "v3?")
    page = pages.read_page(got.path)
    assert [f["text"] for f in page.fm["formulations"]] == ["v1?", "v2?"]
    # every prior formulation survives in the body; nothing overwritten
    for text in ("v1?", "v2?", "v3?"):
        assert text in page.body
    assert page.body.count("## Re-posed") == 2


def test_repose_logs_question_repose_event(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.repose_question(root, "Q1", "who exactly?")
    events = _lines(root / "log" / "log.jsonl")
    repose = [e for e in events if e["text"].startswith("question-repose Q1")]
    assert repose and repose[0]["actor"] == "human:test"


def test_repose_preserves_answer_section(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.answer_question(root, "Q1", note="the foundation")
    got = ledgers.repose_question(root, "Q1", "who, precisely?")
    page = pages.read_page(got.path)
    assert "## Answer\nthe foundation" in page.body  # answer survives the re-pose
    assert page.fm["formulations"][0]["text"] == "who?"


def test_repose_list_shows_current_formulation_only(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.repose_question(root, "Q1", "who, exactly?")
    row = ledgers.list_questions(root)[0]
    assert row["text"] == "who, exactly?"  # the journey stays on the page, not the list


def test_repose_recovers_prior_text_when_body_leads_with_a_section(root: Path):
    # A foreign edit can leave a question body opening directly on a '##'
    # section; the prior formulation then lives only in the description and
    # must land in the history — never an empty record.
    asked = ledgers.add_question(root, "who funded it?")
    page = pages.read_page(asked.path)
    pages.write_page(page.path, page.fm, "## Answer\n\npending\n")
    got = ledgers.repose_question(root, "Q1", "who really funded it?")
    page = pages.read_page(got.path)
    assert [f["text"] for f in page.fm["formulations"]] == ["who funded it?"]
    assert "who funded it?" in page.body  # the Re-posed section carries it too


def test_repose_unknown_question_raises(root: Path):
    ledgers.add_question(root, "one?")
    with pytest.raises(SystemExit, match=r"no question 'Q9'.*known: Q1"):
        ledgers.repose_question(root, "Q9", "x?")


def test_repose_empty_text_raises(root: Path):
    ledgers.add_question(root, "one?")
    with pytest.raises(SystemExit, match="empty new formulation"):
        ledgers.repose_question(root, "Q1", "   ")


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


# --- question journey: evidence notes (SPEC §7) -------------------------------


def test_note_question_appends_dated_evidence_section(root: Path):
    ledgers.add_question(root, "who funded it?")
    got = ledgers.note_question(root, "Q1", "two filings name the trust")
    body = pages.read_page(got.path).body
    assert body.startswith("who funded it?")
    assert "\n## Evidence " in body
    assert body.rstrip().endswith("two filings name the trust")
    assert pages.read_page(got.path).fm["status"] == "open"  # status untouched


def test_note_question_records_scope_verdict_in_heading(root: Path):
    ledgers.add_question(root, "who funded it?")
    got = ledgers.note_question(root, "Q1", "names the 2024 grants only",
                                answers="narrower")
    assert " — answers: narrower" in pages.read_page(got.path).body


def test_note_question_cites_sources_and_refuses_unknown(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.add_decision(root, question="q", decision="d", why="w")  # D1 exists
    got = ledgers.note_question(root, "Q1", "per the ruling", sources=["D1"])
    assert "Sources: [D1]" in pages.read_page(got.path).body
    with pytest.raises(SystemExit, match="unknown source id 'F9'"):
        ledgers.note_question(root, "Q1", "text", sources=["F9"])


def test_note_question_zero_yield_requires_valid_cause(root: Path):
    ledgers.add_question(root, "who?")
    got = ledgers.note_question(root, "Q1", "registry search returned nothing",
                                zero_yield="corpus-gap")
    assert " — zero yield: corpus-gap" in pages.read_page(got.path).body
    with pytest.raises(SystemExit, match="invalid zero-yield cause 'tired'"):
        ledgers.note_question(root, "Q1", "x", zero_yield="tired")


def test_note_question_answers_and_zero_yield_exclusive(root: Path):
    ledgers.add_question(root, "who?")
    with pytest.raises(SystemExit, match="mutually exclusive"):
        ledgers.note_question(root, "Q1", "x", answers="as-worded",
                              zero_yield="saturated")


def test_note_question_invalid_scope_raises(root: Path):
    ledgers.add_question(root, "who?")
    with pytest.raises(SystemExit, match="invalid answers scope 'fully'"):
        ledgers.note_question(root, "Q1", "x", answers="fully")


def test_note_question_logs_question_evidence_event(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.note_question(root, "Q1", "a lead")
    events = util.read_jsonl(root / "log" / "log.jsonl")
    assert any(e["text"].startswith('question-evidence Q1: "a lead"') for e in events)


def test_note_question_allowed_on_answered_page(root: Path):
    # evidence arriving after the answer is exactly what reopen triggers watch
    ledgers.add_question(root, "who?")
    ledgers.answer_question(root, "Q1", note="the trust")
    got = ledgers.note_question(root, "Q1", "a 2027 filing contradicts this")
    page = pages.read_page(got.path)
    assert page.fm["status"] == "answered"
    assert "a 2027 filing contradicts this" in page.body


def test_note_question_keeps_list_text_current(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.note_question(root, "Q1", "some evidence")
    assert ledgers.list_questions(root)[0]["text"] == "who?"


# --- question journey: close / dormant / reopen (SPEC §7) ---------------------


def test_close_question_records_reason_and_section(root: Path):
    ledgers.add_question(root, "who funded it?")
    got = ledgers.close_question(root, "Q1", "dead-end", note="registry sealed")
    page = pages.read_page(got.path)
    assert page.fm["status"] == "closed"
    assert page.fm["closed_reason"] == "dead-end"
    assert page.fm["closed"].endswith("Z")
    assert page.fm["closed_by"] == "human:test"
    assert "## Closed" in page.body and "— dead-end" in page.body
    assert "registry sealed" in page.body


def test_close_question_invalid_reason_raises(root: Path):
    ledgers.add_question(root, "who?")
    with pytest.raises(SystemExit, match="invalid close reason 'boring'"):
        ledgers.close_question(root, "Q1", "boring")


def test_close_answered_question_refused(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.answer_question(root, "Q1")
    with pytest.raises(SystemExit, match="answered; closing would bury"):
        ledgers.close_question(root, "Q1", "dead-end")


def test_close_question_twice_raises(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.close_question(root, "Q1", "split")
    with pytest.raises(SystemExit, match="already closed"):
        ledgers.close_question(root, "Q1", "split")


def test_answer_question_arms_reopen_triggers(root: Path):
    ledgers.add_question(root, "who?")
    got = ledgers.answer_question(root, "Q1", note="the trust",
                                  reopen_when=["a new 990 lands", "  "])
    assert pages.read_page(got.path).fm["reopen_when"] == ["a new 990 lands"]


def test_close_question_arms_reopen_triggers(root: Path):
    ledgers.add_question(root, "who?")
    got = ledgers.close_question(root, "Q1", "yielded",
                                 reopen_when=["owner asks again"])
    assert pages.read_page(got.path).fm["reopen_when"] == ["owner asks again"]


def test_dormant_question_sets_review_by(root: Path):
    ledgers.add_question(root, "who?")
    got = ledgers.dormant_question(root, "Q1", "2027-01-01", note="waiting on filing season")
    page = pages.read_page(got.path)
    assert page.fm["status"] == "dormant"
    assert page.fm["review_by"] == "2027-01-01"
    assert "## Dormant" in page.body and "review by 2027-01-01" in page.body


def test_dormant_question_validates_date_and_status(root: Path):
    ledgers.add_question(root, "who?")
    with pytest.raises(SystemExit, match="invalid review date 'soon'"):
        ledgers.dormant_question(root, "Q1", "soon")
    ledgers.answer_question(root, "Q1")
    with pytest.raises(SystemExit, match="only an open question"):
        ledgers.dormant_question(root, "Q1", "2027-01-01")


def test_reopen_question_restores_open_and_keeps_journey(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.answer_question(root, "Q1", note="the trust",
                            reopen_when=["a new 990 lands"])
    got = ledgers.reopen_question(root, "Q1", "the 990 landed")
    page = pages.read_page(got.path)
    assert page.fm["status"] == "open"
    for gone in ("answered", "answered_by"):
        assert gone not in page.fm
    assert page.fm["reopen_when"] == ["a new 990 lands"]  # stays armed
    assert "## Answer\nthe trust" in page.body  # the journey survives
    assert "## Reopened" in page.body and "the 990 landed" in page.body


def test_reopen_closed_question_clears_closed_keys(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.close_question(root, "Q1", "yielded")
    page = pages.read_page(ledgers.reopen_question(root, "Q1", "back to us").path)
    assert page.fm["status"] == "open"
    for gone in ("closed", "closed_by", "closed_reason"):
        assert gone not in page.fm


def test_reopen_dormant_question_clears_review_by(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.dormant_question(root, "Q1", "2027-01-01")
    page = pages.read_page(ledgers.reopen_question(root, "Q1", "woke early").path)
    assert page.fm["status"] == "open"
    assert "review_by" not in page.fm


def test_reopen_open_question_refused(root: Path):
    ledgers.add_question(root, "who?")
    with pytest.raises(SystemExit, match="already open"):
        ledgers.reopen_question(root, "Q1", "x")


def test_answer_closed_question_refused(root: Path):
    # the mirror of close refusing answered pages: settle-over-settle needs
    # an explicit reopen so neither end buries the other
    ledgers.add_question(root, "who?")
    ledgers.close_question(root, "Q1", "dead-end")
    with pytest.raises(SystemExit, match="closed .dead-end.; answering would bury"):
        ledgers.answer_question(root, "Q1", note="found it after all")


def test_answer_dormant_question_drops_stale_review_by(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.dormant_question(root, "Q1", "2027-01-01")
    page = pages.read_page(ledgers.answer_question(root, "Q1", note="them").path)
    assert page.fm["status"] == "answered"
    assert "review_by" not in page.fm


def test_answer_question_logs_question_answer_event(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.answer_question(root, "Q1", note="the trust")
    events = util.read_jsonl(root / "log" / "log.jsonl")
    assert any(e["text"].startswith('question-answer Q1: "the trust"') for e in events)


def test_dormant_question_rejects_impossible_calendar_date(root: Path):
    ledgers.add_question(root, "who?")
    with pytest.raises(SystemExit, match="no such calendar date"):
        ledgers.dormant_question(root, "Q1", "2026-99-99")


def test_open_questions_keeps_unknown_status_visible(root: Path):
    # a typo must degrade to visible, never to a missing question
    p = ledgers.add_question(root, "who?")
    page = pages.read_page(p.path)
    page.fm["status"] = "dormamt"
    pages.write_page(p.path, page.fm, page.body)
    assert [q["id"] for q in ledgers.open_questions(root)] == ["Q1"]


def test_reopen_logs_question_reopen_event(root: Path):
    ledgers.add_question(root, "who?")
    ledgers.close_question(root, "Q1", "dead-end")
    ledgers.reopen_question(root, "Q1", "new registry access")
    events = util.read_jsonl(root / "log" / "log.jsonl")
    assert any(e["text"].startswith("question-reopen Q1:") for e in events)


def test_open_questions_includes_dormant_excludes_closed(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.add_question(root, "two?")
    ledgers.add_question(root, "three?")
    ledgers.close_question(root, "Q1", "dead-end")
    ledgers.dormant_question(root, "Q2", "2027-01-01")
    assert [q["id"] for q in ledgers.open_questions(root)] == ["Q2", "Q3"]


def test_list_questions_surfaces_journey_keys(root: Path):
    ledgers.add_question(root, "one?")
    ledgers.add_question(root, "two?")
    ledgers.close_question(root, "Q1", "split")
    ledgers.answer_question(root, "Q2", reopen_when=["numbers restated"])
    rows = ledgers.list_questions(root)
    assert rows[0]["closed_reason"] == "split"
    assert rows[1]["reopen_when"] == ["numbers restated"]


# --- question journey: sharpened re-poses (SPEC §7) ---------------------------


def test_repose_records_sharpened_axes_on_history_entry(root: Path):
    ledgers.add_question(root, "what about the money?")
    got = ledgers.repose_question(
        root, "Q1", "which 2026 grants exceeded the cap?",
        sharpened=["scope", "falsifiability"], note="named the cap and the year",
    )
    entry = pages.read_page(got.path).fm["formulations"][0]
    assert entry["text"] == "what about the money?"
    assert entry["sharpened"] == ["scope", "falsifiability"]
    assert entry["note"] == "named the cap and the year"


def test_repose_invalid_sharpened_axis_raises(root: Path):
    ledgers.add_question(root, "who?")
    with pytest.raises(SystemExit, match="invalid sharpened axis 'vibes'"):
        ledgers.repose_question(root, "Q1", "which?", sharpened=["vibes"])


def test_repose_without_instrumentation_keeps_plain_entry(root: Path):
    ledgers.add_question(root, "who?")
    got = ledgers.repose_question(root, "Q1", "which trust?")
    entry = pages.read_page(got.path).fm["formulations"][0]
    assert "sharpened" not in entry and "note" not in entry
