"""The scope-aware orient/select side of the core lifecycle."""

from pathlib import Path

import pytest

from flip import beat, ledgers, loop, scaffold, workspace


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")


def test_notebook_scope_has_bounded_orientation_and_core_frontier(tmp_path: Path):
    root = scaffold.create_notebook(tmp_path / "one", "one", "ledger")
    ledgers.add_question(root, "What changed?")
    data = loop.next_view(root, scope="notebook", explain=True)
    assert data["scope"] == "notebook"
    assert data["context"]["kind"] == "ledger"
    assert data["items"][0]["id"] == "Q1"
    assert data["trace"][0]["handler"] == "flip/core"


def test_beat_scope_retains_threads_and_policy(tmp_path: Path):
    root = tmp_path / "beat"
    beat.create_beat(root, "watch", mission="Watch the record")
    beat.add_thread(root, "New filing", "arc")
    data = loop.next_view(root, scope="beat")
    assert data["scope"] == "beat"
    assert data["mission"] == "Watch the record"
    assert data["items"][0]["lane"] == "thread"


def test_workspace_scope_qualifies_notebook_rows_with_handles(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    notebook = scaffold.create_notebook(vault / "notes", "notes", "ledger")
    ledgers.add_question(notebook, "Who confirmed it?")
    workspace.ws_init(vault)
    data = loop.next_view(vault, scope="workspace")
    assert data["scope"] == "workspace"
    assert data["items"][0]["notebook"] == "notes"
    assert data["items"][0]["id"] == "Q1"


def test_scope_resolution_prefers_child_notebook_over_enclosing_beat(tmp_path: Path):
    root = tmp_path / "beat"
    beat.create_beat(root, "watch")
    thread = beat.add_thread(root, "New filing", "arc")
    notebook = beat.graduate(root, thread.id, "filing", kind="ledger")
    kind, found = loop.resolve_scope(notebook / "questions")
    assert kind == "notebook"
    assert found == notebook
