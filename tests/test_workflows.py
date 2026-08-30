"""Workflow registry and receipt-derived phase state."""

from pathlib import Path

import pytest

from flip import pages, scaffold, sessions, workflows
from flip.manifest import load_manifest


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    return scaffold.create_notebook(tmp_path / "watch", "watch", "ledger")


def test_builtins_are_plain_valid_workflows(root: Path):
    visible = {item.qualified_id: item for item in workflows.list_workflows(root)}
    assert set(("question-pursuit", "weekly-watch")) <= set(visible)
    assert visible["weekly-watch"].entry == "orient"
    assert workflows.load_workflow("weekly-watch@1", root).version == "1.0"


def test_use_pins_exact_version_and_next_is_derived_from_sessions(root: Path):
    chosen = workflows.use_workflow(root, "weekly-watch@1")
    assert load_manifest(root).workflow == chosen.pin
    assert workflows.next_phase(root)["phase"] == "orient"

    path = sessions.start_session(root, "watch-pass", workflow="weekly-watch", phase="orient",
                                  item="Q1")
    open_state = workflows.next_phase(root)
    assert open_state["phase"] == "orient"
    assert "resume open session" in open_state["reason"]

    sessions.end_session(root, path, "oriented", outputs=["Q1"], checks=["doctor"])
    after = workflows.next_phase(root)
    assert after["phase"] == "refresh"
    receipt = pages.read_page(path).fm["receipt"]
    assert receipt["protocol"] == "flip-session-receipt/1"
    assert receipt["outputs"] == ["Q1"]
    assert all(not value.endswith("/index.md") for value in receipt["artifacts"])
    assert "reader relevance" in receipt["does_not_establish"]


def test_notebook_local_workflow_is_authored_checked_and_visible(root: Path):
    path = workflows.create_workflow("team-review", root, from_id="weekly-watch")
    assert path == root / ".flip/workflows/team-review.toml"
    item = workflows.load_workflow("team-review", root)
    assert item.origin == "notebook"
    assert item.phases[-1].next == "orient"


def test_collision_is_refused_instead_of_last_wins(root: Path):
    directory = root / ".flip/workflows"
    directory.mkdir(parents=True)
    (directory / "weekly-watch.toml").write_text(
        'id = "weekly-watch"\nversion = "9.0"\nentry = "x"\n'
        '[[phase]]\nid = "x"\n', encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="workflow id collision"):
        workflows.list_workflows(root)


def test_inline_kind_phases_remain_a_sequential_compatibility_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "home"))
    review = scaffold.create_notebook(tmp_path / "review", "review", "lit-review")
    item = workflows.load_workflow("kind:lit-review", review)
    assert item.phases[0].id == "search"
    assert item.phases[0].next == "screen"
    assert item.phases[0].produces == ["search-log.md — surfaces queried, dates, hit counts"]
