"""Tests for flip.views — computed hot/claims/stale views (SPEC §10)."""

import json
from pathlib import Path

import pytest

from flip.views import claims_view, hot_view, stale_view

MANIFEST = """\
slug = "test"
kind = "{kind}"
status = "active"
created = "2026-07-01"
updated = "2026-07-09"
"""


def make_notebook(tmp_path: Path, kind: str = "scout") -> Path:
    root = tmp_path / "nb"
    root.mkdir(exist_ok=True)
    (root / "notebook.toml").write_text(MANIFEST.format(kind=kind), encoding="utf-8")
    return root


def write_jsonl(root: Path, rel: str, rows: list[dict]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


# --- hot_view ---------------------------------------------------------------


def test_hot_view_empty_notebook_is_just_the_manifest_line(tmp_path):
    root = make_notebook(tmp_path)
    text = hot_view(root)
    assert text == "test · scout · active · 2026-07-09"
    assert "OPEN QUESTIONS" not in text
    assert "RECENT LOG" not in text


def test_hot_view_shows_open_questions_and_hides_answered(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "log/questions.jsonl",
        [
            {"ts": "t1", "id": "Q1", "text": "who pays?", "actor": "a", "status": "open"},
            {"ts": "t2", "id": "Q2", "text": "when?", "actor": "a", "status": "open"},
            {"ts": "t3", "id": "Q2", "text": "when?", "actor": "a", "status": "answered"},
        ],
    )
    text = hot_view(root)
    assert "OPEN QUESTIONS" in text
    assert "Q1 · who pays?" in text
    assert "Q2" not in text


def test_hot_view_reopened_question_counts_as_open(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "log/questions.jsonl",
        [
            {"ts": "t1", "id": "Q1", "text": "x?", "actor": "a", "status": "open"},
            {"ts": "t2", "id": "Q1", "text": "x?", "actor": "a", "status": "answered"},
            {"ts": "t3", "id": "Q1", "text": "x?", "actor": "a", "status": "open"},
        ],
    )
    assert "Q1" in hot_view(root)


def test_hot_view_claims_needing_work_load_bearing_first(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "analysis/claims.jsonl",
        [
            {
                "id": "C1",
                "text": "minor",
                "status": "asserted",
                "load_bearing": False,
                "sources": [],
                "independent_corroboration": 0,
            },
            {
                "id": "C2",
                "text": "key",
                "status": "needs-2nd",
                "load_bearing": True,
                "sources": ["A1"],
                "independent_corroboration": 1,
            },
            {
                "id": "C3",
                "text": "done",
                "status": "verified",
                "load_bearing": True,
                "sources": ["A1"],
                "independent_corroboration": 2,
            },
        ],
    )
    text = hot_view(root)
    assert "CLAIMS NEEDING WORK" in text
    assert "C3" not in text  # verified is not "needing work"
    assert text.index("C2") < text.index("C1")  # load-bearing first
    assert "[load-bearing]" in text


def test_hot_view_recent_log_is_last_eight(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "log/log.jsonl",
        [{"ts": f"t{i}", "text": f"event-{i}", "actor": "a"} for i in range(1, 11)],
    )
    text = hot_view(root)
    assert "event-10" in text
    assert "event-3" in text
    assert "event-2" not in text
    assert "event-1\n" not in text and "event-1 " not in text


def test_hot_view_latest_session_is_newest_by_name(tmp_path):
    root = make_notebook(tmp_path)
    sessions = root / "log" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "2026-07-01T1000-old.md").write_text("old", encoding="utf-8")
    (sessions / "2026-07-09T0900-new.md").write_text("new", encoding="utf-8")
    text = hot_view(root)
    assert "LATEST SESSION" in text
    assert "log/sessions/2026-07-09T0900-new.md" in text
    assert "old.md" not in text


def test_hot_view_dated_sources_count(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "sources/ledger.jsonl",
        [
            {"id": "A1", "kind": "article", "local": "x", "freshness": "dated"},
            {
                "id": "A2",
                "kind": "article",
                "local": "y",
                "freshness": "fresh",
                "date": "2026-06-01",
            },
        ],
    )
    assert "DATED SOURCES: 1" in hot_view(root)


def test_hot_view_as_data(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "log/questions.jsonl",
        [{"ts": "t1", "id": "Q1", "text": "x?", "actor": "a", "status": "open"}],
    )
    data = hot_view(root, as_data=True)
    assert data["slug"] == "test"
    assert data["kind"] == "scout"
    assert data["open_questions"][0]["id"] == "Q1"
    assert data["claims_needing_work"] == []
    assert data["recent_log"] == []
    assert data["latest_session"] is None
    assert data["dated_sources"] == 0


def test_hot_view_missing_manifest_exits(tmp_path):
    with pytest.raises(SystemExit):
        hot_view(tmp_path)  # no notebook.toml here


def test_hot_view_unknown_kind_falls_back_to_defaults(tmp_path):
    root = make_notebook(tmp_path, kind="no-such-profile")
    assert "no-such-profile" in hot_view(root)


# --- claims_view ------------------------------------------------------------


def test_claims_view_groups_by_status_in_enum_order(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "analysis/claims.jsonl",
        [
            {
                "id": "C1",
                "text": "a",
                "status": "verified",
                "load_bearing": True,
                "sources": ["A1", "A2"],
                "independent_corroboration": 2,
            },
            {
                "id": "C2",
                "text": "b",
                "status": "asserted",
                "load_bearing": False,
                "sources": [],
                "independent_corroboration": 0,
            },
        ],
    )
    text = claims_view(root)
    assert text.index("ASSERTED") < text.index("VERIFIED")
    assert "C1 · [load-bearing] · a · sources: A1, A2 · corroboration: 2" in text
    assert "C2 · b · sources: none · corroboration: 0" in text


def test_claims_view_truncates_long_text_to_80(tmp_path):
    root = make_notebook(tmp_path)
    long_text = "z" * 200
    write_jsonl(
        root,
        "analysis/claims.jsonl",
        [
            {
                "id": "C1",
                "text": long_text,
                "status": "asserted",
                "load_bearing": False,
                "sources": [],
                "independent_corroboration": 0,
            }
        ],
    )
    text = claims_view(root)
    assert "z" * 79 + "…" in text
    assert "z" * 100 not in text


def test_claims_view_empty(tmp_path):
    root = make_notebook(tmp_path)
    assert "no claims recorded" in claims_view(root)
    data = claims_view(root, as_data=True)
    assert data == {"total": 0, "by_status": {}}


def test_claims_view_unknown_status_still_listed(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "analysis/claims.jsonl",
        [
            {
                "id": "C1",
                "text": "odd",
                "status": "bogus",
                "load_bearing": False,
                "sources": [],
                "independent_corroboration": 0,
            }
        ],
    )
    text = claims_view(root)
    assert "BOGUS" in text
    assert "C1" in text


def test_claims_view_bad_jsonl_exits_actionably(tmp_path):
    root = make_notebook(tmp_path)
    path = root / "analysis" / "claims.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        claims_view(root)
    assert "claims.jsonl" in str(e.value)


# --- stale_view -------------------------------------------------------------


def test_stale_view_flags_dated_and_old_sources(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "sources/ledger.jsonl",
        [
            {
                "id": "A1",
                "kind": "article",
                "title": "judged dated",
                "local": "x",
                "freshness": "dated",
                "date": "2026-06-01",
            },
            {
                "id": "A2",
                "kind": "article",
                "title": "old by date",
                "local": "y",
                "freshness": "fresh",
                "date": "2020-01-01",
            },
            {
                "id": "A3",
                "kind": "article",
                "title": "recent",
                "local": "z",
                "freshness": "fresh",
                "date": "2026-06-01",
            },
        ],
    )
    text = stale_view(root)
    assert "DATED SOURCES" in text
    assert "A1" in text
    assert "A2" in text
    assert "A3" not in text


def test_stale_view_lists_open_questions_and_stuck_claims(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "log/questions.jsonl",
        [{"ts": "t1", "id": "Q1", "text": "open one", "actor": "a", "status": "open"}],
    )
    write_jsonl(
        root,
        "analysis/claims.jsonl",
        [
            {
                "id": "C1",
                "text": "stuck",
                "status": "asserted",
                "load_bearing": True,
                "sources": [],
                "independent_corroboration": 0,
            },
            {
                "id": "C2",
                "text": "fine",
                "status": "verified",
                "load_bearing": True,
                "sources": ["A1"],
                "independent_corroboration": 2,
            },
        ],
    )
    text = stale_view(root)
    assert "OPEN QUESTIONS" in text and "Q1" in text
    assert "STUCK CLAIMS" in text and "C1" in text
    assert "C2" not in text


def test_stale_view_nothing_stale(tmp_path):
    root = make_notebook(tmp_path)
    assert stale_view(root) == "nothing stale"


def test_stale_view_as_data(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "sources/ledger.jsonl",
        [{"id": "A1", "kind": "article", "local": "x", "freshness": "dated"}],
    )
    data = stale_view(root, as_data=True)
    assert [r["id"] for r in data["dated_sources"]] == ["A1"]
    assert data["open_questions"] == []
    assert data["stuck_claims"] == []


def test_stale_view_source_without_date_or_freshness_not_flagged(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(root, "sources/ledger.jsonl", [{"id": "A1", "kind": "article", "local": "x"}])
    assert stale_view(root) == "nothing stale"
