"""Tests for flip.sessions — session record scaffolding and closure."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import flip.util
from flip import sessions, util
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
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    (tmp_path / "notebook.toml").write_text(MANIFEST, encoding="utf-8")
    return tmp_path


def _fix_stamp(monkeypatch: pytest.MonkeyPatch, stamp: str) -> None:
    monkeypatch.setattr(flip.util, "stamp_slug", lambda: stamp)


# --- start_session -----------------------------------------------------------


def test_start_session_creates_stubbed_file(root: Path):
    path = sessions.start_session(root, "corpus-sweep")
    assert path.parent == root / "log" / "sessions"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{4}-corpus-sweep\.md", path.name)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\nactor: agent:test\nstarted: ")
    assert "model:" not in text
    assert "tools:" not in text
    for stub in ("## Goal", "## Prompt", "## Key outputs", "## Transcript"):
        assert f"\n{stub}\n" in text
    assert load_manifest(root).updated == util.today()


def test_start_session_model_and_tools(root: Path):
    path = sessions.start_session(root, "scan", model="claude-fable-5", tools=["rg", "curl"])
    text = path.read_text(encoding="utf-8")
    assert "model: claude-fable-5\n" in text
    assert "tools: [rg, curl]\n" in text
    # tools may also be a plain string
    path2 = sessions.start_session(root, "scan2", tools="rg")
    assert "tools: rg\n" in path2.read_text(encoding="utf-8")


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


def test_end_session_by_path_appends_block(root: Path):
    path = sessions.start_session(root, "sweep")
    got = sessions.end_session(root, path, "found the pattern")
    assert got == path
    text = path.read_text(encoding="utf-8")
    assert re.search(r"\n---\nended: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n", text)
    assert text.endswith("## Summary\nfound the pattern\n")
    # frontmatter untouched
    assert text.startswith("---\nactor: agent:test\n")


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
    assert not (outside / "log").exists()
