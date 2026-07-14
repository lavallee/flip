"""Tests for flip.query: the research (find/ask) and knowledge (recall) roles —
neutral normalization, sessions/raw landing for synthesis, and the invariant
that these roles never mint a source page."""

import stat

import pytest

from flip import query
from flip.util import read_jsonl

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: test-nb
kind: scout
status: active
created: 2026-01-01
updated: 2026-01-01
---
# test-nb
"""


def make_notebook(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    return root.resolve()


def make_tool(tmp_path, name, stdout):
    script = tmp_path / name
    script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{stdout}\nEOF\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def config(tmp_path, monkeypatch, role, verb, tool):
    home = tmp_path / "fliphome"
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text(
        f'[{role}]\n{verb} = "{tool} {{query}}"\n', encoding="utf-8"
    )
    monkeypatch.setenv("FLIP_HOME", str(home))


# --- research find ----------------------------------------------------------


def test_find_normalizes_and_drops_backend_ids(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    tool = make_tool(
        tmp_path, "res",
        '{"results": [{"url": "https://a.test/1", "title": "One", '
        '"snippet": "s1", "source_id": 42, "resource_id": "cx"}]}',
    )
    config(tmp_path, monkeypatch, "research", "find", tool)

    result = query.research_find(root, "who owns Acme?")

    assert result.candidates == [
        {"url": "https://a.test/1", "title": "One", "snippet": "s1"}
    ]
    # backend-native ids never surface as flip fields
    assert set(result.candidates[0]) <= {"url", "title", "snippet"}
    # find captures nothing
    assert not (root / "references").exists()
    assert not (root / "sessions").exists()


def test_find_tolerates_bare_list_and_alt_keys(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    tool = make_tool(tmp_path, "res", '[{"link": "https://b.test", "name": "B"}]')
    config(tmp_path, monkeypatch, "research", "find", tool)
    result = query.research_find(root, "q")
    assert result.candidates == [{"url": "https://b.test", "title": "B"}]


def test_find_skips_items_without_a_url(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    tool = make_tool(tmp_path, "res", '[{"title": "no url"}, {"url": "https://ok.test"}]')
    config(tmp_path, monkeypatch, "research", "find", tool)
    result = query.research_find(root, "q")
    assert result.candidates == [{"url": "https://ok.test"}]


# --- research ask -----------------------------------------------------------


def test_ask_lands_raw_logs_and_opens_no_reference(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    raw = ('{"answer": "Acme is owned by Beta Corp.", '
           '"citations": [{"url": "https://beta.test/filing", "title": "Filing", '
           '"resource_id": "z9"}]}')
    tool = make_tool(tmp_path, "ask", raw)
    config(tmp_path, monkeypatch, "research", "ask", tool)

    result = query.research_ask(root, "who owns Acme?")

    assert result.answer == "Acme is owned by Beta Corp."
    assert result.citations == [{"url": "https://beta.test/filing", "title": "Filing"}]
    # synthesis is a lead: raw preserved under sessions/raw, no source page
    assert result.raw_path.parent == root / "sessions" / "raw"
    assert result.raw_path.read_text(encoding="utf-8").startswith('{"answer"')
    assert not (root / "references").exists()
    # a breadcrumb is logged
    log = read_jsonl(root / "log" / "log.jsonl")
    assert any("research ask" in row["text"] for row in log)


def test_ask_falls_back_to_raw_text_when_not_json(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    tool = make_tool(tmp_path, "ask", "just a prose answer, no json")
    config(tmp_path, monkeypatch, "research", "ask", tool)
    result = query.research_ask(root, "q")
    assert result.answer == "just a prose answer, no json"
    assert result.citations == []
    assert result.raw_path.is_file()


# --- knowledge recall -------------------------------------------------------


def test_recall_reads_and_lands_nothing(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    tool = make_tool(
        tmp_path, "localknow",
        '{"hits": [{"path": "notes/acme.md", "title": "Acme", "excerpt": "prior work"}]}',
    )
    config(tmp_path, monkeypatch, "knowledge", "recall", tool)

    result = query.knowledge_recall(root, "acme")

    assert result.hits == [
        {"path": "notes/acme.md", "title": "Acme", "excerpt": "prior work"}
    ]
    assert not (root / "sessions").exists()  # read-only by default
    assert not (root / "references").exists()


def test_recall_record_preserves_raw_and_logs(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    tool = make_tool(tmp_path, "localknow", '[{"path": "n.md", "title": "N"}]')
    config(tmp_path, monkeypatch, "knowledge", "recall", tool)

    result = query.knowledge_recall(root, "n", record=True)

    assert result.hits == [{"path": "n.md", "title": "N"}]
    raws = list((root / "sessions" / "raw").glob("*.json"))
    assert len(raws) == 1
    log = read_jsonl(root / "log" / "log.jsonl")
    assert any("knowledge recall" in row["text"] for row in log)


def test_roles_require_a_notebook(tmp_path, monkeypatch):
    config(tmp_path, monkeypatch, "research", "find", make_tool(tmp_path, "t", "[]"))
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        query.research_find(tmp_path / "nowhere", "q")
