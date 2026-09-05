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


def test_next_uses_receipt_time_for_reverse_lexical_slugs_in_same_minute(
    root: Path, monkeypatch: pytest.MonkeyPatch
):
    workflows.use_workflow(root, "weekly-watch")
    monkeypatch.setattr(sessions.util, "stamp_slug", lambda: "2026-09-05T0315")
    monkeypatch.setattr(sessions.util, "utc_now", lambda: "2026-09-05T03:15:00Z")
    now = [1_788_578_100_000_000_001]
    monkeypatch.setattr(sessions.time, "time_ns", lambda: now[0])
    older = sessions.start_session(root, "z-orient", workflow="weekly-watch", phase="orient")
    sessions.end_session(root, older, "oriented")
    now[0] += 1
    newer = sessions.start_session(root, "a-refresh", workflow="weekly-watch", phase="refresh")
    assert newer.name < older.name
    state = workflows.next_phase(root)
    assert state["phase"] == "refresh"
    assert newer.name in state["reason"]
    assert "resume open session" in state["reason"]
    sessions.end_session(root, newer, "refreshed")
    state = workflows.next_phase(root)
    definition = workflows.load_workflow("weekly-watch", root)
    assert state["phase"] == next(p.next for p in definition.phases if p.id == "refresh")
    assert newer.name in state["reason"]


@pytest.mark.parametrize("field", ["started", "ended"])
def test_next_uses_legacy_iso_timestamps_before_filename(root: Path, field: str):
    workflows.use_workflow(root, "weekly-watch")
    directory = root / "sessions"
    directory.mkdir(exist_ok=True)
    for filename, stamp, phase in (
        ("2026-09-05T0315-z-older.md", "2026-09-05T03:15:01Z", "orient"),
        ("2026-09-05T0315-a-newer.md", "2026-09-04T23:15:02-04:00", "refresh"),
    ):
        fm = {"workflow": "weekly-watch@1.0", "phase": phase, field: stamp}
        pages.write_page(directory / filename, fm, "Legacy session")
    state = workflows.next_phase(root)
    assert "a-newer.md" in state["reason"]


def test_next_uses_deterministic_filename_fallback_for_undated_sessions(root: Path):
    workflows.use_workflow(root, "weekly-watch")
    directory = root / "sessions"
    directory.mkdir(exist_ok=True)
    for filename, phase in (
        ("2026-09-05T0314-z-older.md", "orient"),
        ("2026-09-05T0315-a-newer.md", "refresh"),
        ("2026-09-05T0315-z-tiebreak.md", "refresh"),
    ):
        pages.write_page(directory / filename, {
            "workflow": "weekly-watch", "phase": phase, "started": "unknown",
            "receipt": {"observed_since_ns": "invalid"},
        }, "Legacy session")
    state = workflows.next_phase(root)
    assert "z-tiebreak.md" in state["reason"]


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


def test_repeatable_gain_can_resume_each_phase_and_stops(root: Path):
    chosen = workflows.use_workflow(root, "repeatable-gain")
    assert chosen.origin == "built-in"
    assert load_manifest(root).workflow == "repeatable-gain@1.0"
    for number, phase in enumerate(chosen.phases, 1):
        assert workflows.next_phase(root)["phase"] == phase.id
        path = sessions.start_session(root, f"gain-{number:02d}-{phase.id}",
                                      workflow=chosen.pin, phase=phase.id)
        assert "resume open session" in workflows.next_phase(root)["reason"]
        output = root / f"gain-{number:02d}.md"
        output.write_text("Synthetic phase receipt; no user benefit established.\n")
        sessions.end_session(root, path, "Fixture phase finished", outputs=[output.name])
    state = workflows.next_phase(root)
    assert state["complete"] is True
