"""Tests for flip.sessions — session entity pages and closure."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import flip.util
from flip import pages, sessions, util
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

_TS_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    (tmp_path / "index.md").write_text(ROOT_MD, encoding="utf-8")
    return tmp_path


def _fix_stamp(monkeypatch: pytest.MonkeyPatch, stamp: str) -> None:
    monkeypatch.setattr(flip.util, "stamp_slug", lambda: stamp)


# --- start_session -----------------------------------------------------------


def test_start_session_creates_stubbed_page(root: Path):
    path = sessions.start_session(root, "corpus-sweep")
    assert path.parent == root / "sessions"  # top level, not log/sessions/
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{4}-corpus-sweep\.md", path.name)
    page = pages.read_page(path)
    assert page.fm["type"] == "Work Session"
    assert page.fm["actor"] == "agent:test"
    assert re.fullmatch(_TS_RE, page.fm["started"])
    assert "model" not in page.fm
    assert "tools" not in page.fm
    for stub in ("## Goal", "## Prompt", "## Key outputs", "## Transcript"):
        assert stub in page.body
    assert load_manifest(root).updated == util.today()


def test_start_session_model_and_tools(root: Path):
    path = sessions.start_session(root, "scan", model="claude-fable-5", tools=["rg", "curl"])
    fm = pages.read_page(path).fm
    assert fm["model"] == "claude-fable-5"
    assert fm["tools"] == ["rg", "curl"]
    # tools may also be a plain string
    path2 = sessions.start_session(root, "scan2", tools="rg")
    assert pages.read_page(path2).fm["tools"] == "rg"


def test_start_session_slug_is_cleaned(root: Path):
    path = sessions.start_session(root, "Landscape Scan!")
    assert path.name.endswith("-landscape-scan.md")


def test_start_session_bad_slug_raises(root: Path):
    with pytest.raises(SystemExit, match="unusable session slug"):
        sessions.start_session(root, "///")


def test_start_session_same_minute_collision_raises(
    root: Path, monkeypatch: pytest.MonkeyPatch
):
    _fix_stamp(monkeypatch, "2026-07-10T1431")
    sessions.start_session(root, "sweep")
    with pytest.raises(SystemExit, match="already exists"):
        sessions.start_session(root, "sweep")


# --- end_session -------------------------------------------------------------


def test_end_session_by_path_sets_frontmatter_ended(root: Path):
    path = sessions.start_session(root, "sweep")
    got = sessions.end_session(root, path, "found the pattern")
    assert got == path
    page = pages.read_page(path)
    assert re.fullmatch(_TS_RE, page.fm["ended"])  # ended lives in FRONTMATTER
    assert page.fm["actor"] == "agent:test"  # existing keys untouched
    assert re.fullmatch(_TS_RE, page.fm["started"])
    assert page.body.rstrip().endswith("## Summary\nfound the pattern")
    assert "## Goal" in page.body  # stubs survive the rewrite
    # no v0.3-style appended closing block — frontmatter is the record
    assert "\n---\nended:" not in path.read_text(encoding="utf-8")


def test_end_session_preserves_foreign_frontmatter_key(root: Path):
    # round-trip rule (SPEC §6.6): a key some other tool wrote must survive
    path = sessions.start_session(root, "sweep")
    page = pages.read_page(path)
    page.fm["mood"] = "optimistic"
    pages.write_page(path, page.fm, page.body)
    sessions.end_session(root, path, "done")
    after = pages.read_page(path)
    assert after.fm["mood"] == "optimistic"
    assert re.fullmatch(_TS_RE, after.fm["ended"])


def test_end_session_by_slug_picks_newest(root: Path, monkeypatch: pytest.MonkeyPatch):
    _fix_stamp(monkeypatch, "2026-07-10T1400")
    sessions.start_session(root, "sweep")
    _fix_stamp(monkeypatch, "2026-07-10T1500")
    newer = sessions.start_session(root, "sweep")
    got = sessions.end_session(root, "sweep", "done")
    assert got == newer


def test_end_session_slug_must_match_exactly_not_by_suffix(
    root: Path, monkeypatch: pytest.MonkeyPatch
):
    # "sweep" must not resolve to "...-corpus-sweep.md" (suffix collision).
    _fix_stamp(monkeypatch, "2026-07-10T1400")
    sessions.start_session(root, "corpus-sweep")
    with pytest.raises(SystemExit, match=r"no session file matching 'sweep'"):
        sessions.end_session(root, "sweep", "done")


def test_end_session_exact_slug_wins_over_suffix_collision(
    root: Path, monkeypatch: pytest.MonkeyPatch
):
    _fix_stamp(monkeypatch, "2026-07-10T1400")
    sessions.start_session(root, "sweep")
    _fix_stamp(monkeypatch, "2026-07-10T1500")
    sessions.start_session(root, "corpus-sweep")  # newer, but not slug "sweep"
    got = sessions.end_session(root, "sweep", "done")
    assert got.name == "2026-07-10T1400-sweep.md"


def test_end_session_by_bare_filename(root: Path):
    path = sessions.start_session(root, "sweep")
    assert sessions.end_session(root, path.name, "done") == path


def test_end_session_not_found_raises(root: Path):
    sessions.start_session(root, "sweep")
    with pytest.raises(SystemExit, match=r"no session file matching 'other'"):
        sessions.end_session(root, "other", "done")


def test_end_session_no_sessions_dir_raises(root: Path):
    with pytest.raises(SystemExit, match="no session file matching"):
        sessions.end_session(root, "sweep", "done")


def test_end_session_twice_raises(root: Path):
    path = sessions.start_session(root, "sweep")
    sessions.end_session(root, path, "done")
    with pytest.raises(SystemExit, match="already ended"):
        sessions.end_session(root, path, "done again")


def test_end_session_empty_summary_raises(root: Path):
    sessions.start_session(root, "sweep")
    with pytest.raises(SystemExit, match="empty session summary"):
        sessions.end_session(root, "sweep", "  ")


def test_start_session_outside_notebook_writes_nothing(tmp_path: Path):
    outside = tmp_path / "not-a-notebook"
    outside.mkdir()
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        sessions.start_session(outside, "sweep")
    assert list(outside.iterdir()) == []
