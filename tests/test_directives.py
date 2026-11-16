"""Directives: log/directives.jsonl, `flip directive`, and their place at the
top of `flip next` and `flip show`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import directives, pages, util
from flip.cli import main

HEADING = "DIRECTIVES — standing instructions; follow every one until it is withdrawn"
LONG = ("Primary sources only: do not cite press coverage, summaries, or anything that "
        "republishes another document, however reputable the outlet, unless the primary "
        "is recorded as out of reach and the note says what was tried.")


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:jane")


def invoke(args: list[str], ok: bool = True):
    result = CliRunner().invoke(main, args)
    if ok:
        assert result.exit_code == 0, result.output
    return result


@pytest.fixture
def notebook(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "demo"
    invoke(["new", "demo", "--kind", "ledger", "--dest", str(root)])
    monkeypatch.chdir(root)
    return root


def ledger(root: Path) -> list[dict]:
    return util.read_jsonl(root / "log" / "directives.jsonl")


# --- lifecycle -------------------------------------------------------------------


def test_add_allocates_dr_ids_and_withdraw_appends(notebook, monkeypatch):
    assert invoke(["directive", "add", LONG]).output.strip() == f"DR1 · human:jane · {LONG}"
    invoke(["directive", "add", "Stop at ten sources."])
    monkeypatch.setenv("FLIP_ACTOR", "human:sam")
    out = invoke(["directive", "withdraw", "DR2", "--because", "limit lifted"])
    assert out.output.strip() == "DR2 withdrawn · human:sam · limit lifted"

    first, second, withdrawal = ledger(notebook)
    assert set(first) == {"ts", "id", "text", "actor"} and first["id"] == "DR1"
    assert first["text"] == LONG  # whole, never clipped
    assert second["id"] == "DR2"
    assert set(withdrawal) == {"ts", "event", "id", "because", "actor"}
    assert (withdrawal["event"], withdrawal["id"]) == ("withdraw", "DR2")

    rows = directives.list_directives(notebook, include_all=True)
    assert [(r["id"], r["state"]) for r in rows] == [("DR1", "active"), ("DR2", "withdrawn")]
    assert (rows[1]["withdrawn_actor"], rows[1]["because"]) == ("human:sam", "limit lifted")
    assert rows[1]["actor"] == "human:jane"  # who set it survives the withdrawal
    assert [r["id"] for r in directives.list_directives(notebook)] == ["DR1"]


def test_list_text_and_json(notebook):
    invoke(["directive", "add", "Primary sources only."])
    invoke(["directive", "add", "Stop at ten sources."])
    invoke(["directive", "withdraw", "DR2"])
    text = invoke(["directive", "list"]).output
    assert "DR1 · active · human:jane" in text and "DR2" not in text
    everything = invoke(["directive", "list", "--all"]).output
    assert "DR2 · withdrawn · human:jane" in everything and "withdrawn 20" in everything

    rows = json.loads(invoke(["directive", "list", "--all", "--json"]).output)
    keys = {"id", "text", "state", "ts", "actor", "withdrawn_ts", "withdrawn_actor", "because"}
    assert [set(r) for r in rows] == [keys, keys]
    assert rows[0]["withdrawn_ts"] is None and rows[0]["because"] is None
    assert rows[1]["withdrawn_ts"] and rows[1]["because"] is None
    assert json.loads(invoke(["directive", "list", "--json"]).output) == rows[:1]


def test_refusals_are_actionable(notebook):
    assert "no active directives" in invoke(["directive", "list"]).output
    empty = invoke(["directive", "add", "  "], ok=False)
    assert empty.exit_code != 0 and "empty directive" in empty.output
    unknown = invoke(["directive", "withdraw", "DR1"], ok=False)
    assert unknown.exit_code != 0 and "no directive 'DR1'" in unknown.output
    invoke(["directive", "add", "Primary sources only."])
    invoke(["directive", "withdraw", "DR1"])
    again = invoke(["directive", "withdraw", "DR1"], ok=False)
    assert again.exit_code != 0 and "already withdrawn" in again.output
    assert len(ledger(notebook)) == 2  # the refused withdrawal wrote nothing


# --- the DR prefix does not disturb D, and is never reused -------------------------


def test_dr_and_d_series_are_independent(notebook):
    invoke(["directive", "add", "Primary sources only."])
    out = invoke(["decide", "--question", "q", "--decision", "d", "--why", "w"])
    assert out.output.startswith("D1 ·")
    invoke(["directive", "add", "Stop at ten sources."])
    assert [r["id"] for r in ledger(notebook)] == ["DR1", "DR2"]
    assert util.next_id("D", ["DR7", "D2"]) == "D3"
    assert util.next_id("DR", ["D9", "DR1"]) == "DR2"
    assert util.parse_ref("DR1") == (None, "DR1")


def test_dr_ids_are_not_reused_when_the_reservation_file_is_gone(notebook):
    # .flip/ does not travel with an export; the ledger alone must hold the ids.
    invoke(["directive", "add", "one"])
    invoke(["directive", "add", "two"])
    invoke(["directive", "withdraw", "DR2"])
    shutil.rmtree(notebook / ".flip")
    assert "DR2" in pages.all_ids(notebook)
    assert invoke(["directive", "add", "three"]).output.startswith("DR3 ·")


def test_open_and_resolve_refuse_a_directive_id_and_say_what_it_is(notebook):
    invoke(["directive", "add", "Primary sources only."])
    for command in ("open", "resolve"):
        out = invoke([command, "DR1"], ok=False)
        assert out.exit_code != 0
        assert 'DR1 (active, set by human:jane): "Primary sources only."' in out.output
        assert "flip directive list --all" in out.output
    missing = invoke(["open", "DR9"], ok=False)
    assert missing.exit_code != 0 and "no page with id 'DR9'" in missing.output


# --- flip next / flip show ---------------------------------------------------------


def test_next_and_show_are_unchanged_without_directives(notebook):
    assert HEADING not in invoke(["next"]).output
    assert HEADING not in invoke(["show"]).output
    assert json.loads(invoke(["next", "--json"]).output)["context"]["directives"] == []
    assert json.loads(invoke(["show", "--json"]).output)["directives"] == []


def test_active_directives_print_first_whole_in_next_and_show(notebook):
    invoke(["question", "add", "How much do tides vary?"])
    invoke(["directive", "add", LONG])
    invoke(["directive", "add", "Stop at ten sources."])
    invoke(["directive", "withdraw", "DR2", "--because", "limit lifted"])
    for command in ("next", "show"):
        lines = invoke([command]).output.splitlines()
        assert lines[0] == HEADING, command
        assert lines[1].startswith("  DR1 · human:jane · ") and lines[1].endswith(LONG)
        assert lines[2] == "" and lines[3].startswith("demo · ")
        assert "DR2" not in "\n".join(lines) and "Stop at ten" not in "\n".join(lines)


def test_active_directives_are_in_next_and_show_json(notebook):
    invoke(["directive", "add", LONG])
    invoke(["directive", "add", "Stop at ten sources."])
    invoke(["directive", "withdraw", "DR2"])
    expected = directives.list_directives(notebook)
    assert [r["id"] for r in expected] == ["DR1"] and expected[0]["text"] == LONG
    assert json.loads(invoke(["next", "--json"]).output)["context"]["directives"] == expected
    assert json.loads(invoke(["show", "--json"]).output)["directives"] == expected


def test_a_corrupt_directive_ledger_does_not_take_next_down(notebook):
    invoke(["directive", "add", "Primary sources only."])
    with open(notebook / "log" / "directives.jsonl", "a", encoding="utf-8") as f:
        f.write("not json\n")
    assert invoke(["next"]).exit_code == 0
    assert invoke(["directive", "list"], ok=False).exit_code != 0
