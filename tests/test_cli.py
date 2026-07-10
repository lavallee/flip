"""CLI wiring tests: every subcommand end-to-end through click's CliRunner.

The library modules own their behavior tests; these verify the wiring — argument
shapes, output, exit codes, and the actionable one-liners on unhappy paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip.cli import main


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep every test away from the real ~/.flip and the host's git identity."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def make_notebook(dest: Path, kind: str = "scout", slug: str = "demo") -> Path:
    result = invoke(["new", slug, "--kind", kind, "--dest", str(dest)])
    assert result.exit_code == 0, result.output
    return dest


# ---------------------------------------------------------------- new / profiles


def test_new_creates_notebook(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(["new", "demo", "--kind", "scout", "--title", "Demo run"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo" / "notebook.toml").is_file()
    md = (tmp_path / "demo" / "notebook.md").read_text(encoding="utf-8")
    assert "# Reporter's notebook — Demo run" in md
    assert "## The tip" in md
    assert str(tmp_path / "demo") in result.output


def test_new_unknown_kind_is_actionable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(["new", "demo", "--kind", "no-such-kind"])
    assert result.exit_code == 1
    assert "unknown profile kind" in result.output
    assert "scout" in result.output  # lists what IS available


def test_new_refuses_existing_notebook(tmp_path):
    make_notebook(tmp_path / "demo")
    result = invoke(["new", "again", "--dest", str(tmp_path / "demo")])
    assert result.exit_code == 1
    assert "notebook.toml" in result.output


def test_commands_outside_a_notebook_fail_actionably(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for args in (["log", "x"], ["show"], ["doctor"], ["question", "add", "x"]):
        result = invoke(args)
        assert result.exit_code == 1, args
        assert "not inside a flip notebook" in result.output


def test_profiles_lists_shipped_and_local(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    local = root / ".flip" / "profiles"
    local.mkdir(parents=True)
    local.joinpath("custom.toml").write_text(
        'id = "custom"\ndescription = "Project-local profile."\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    result = invoke(["profiles"])
    assert result.exit_code == 0, result.output
    assert "scout — " in result.output
    assert "custom (local) — Project-local profile." in result.output


# ---------------------------------------------------------------- the full happy flow


def test_full_flow(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    payload = tmp_path / "report.txt"
    payload.write_text("vendor says 42%\n", encoding="utf-8")

    result = invoke(["add-source", str(payload), "--note", "vendor report"])
    assert result.exit_code == 0, result.output
    assert "F1" in result.output
    assert (root / "sources" / "raw" / "F1.txt").is_file()
    assert (root / "sources" / "_provenance.jsonl").is_file()

    assert invoke(["log", "captured the vendor report"]).exit_code == 0
    assert "Q1" in invoke(["question", "add", "does it replicate?"]).output
    assert (
        invoke(
            ["decide", "--question", "scope", "--decision", "scout only",
             "--why", "fast screen", "--rejected", "full sweep"]
        ).exit_code
        == 0
    )
    passed = invoke(["pass", "aggregator recap", "--reason", "derivative of F1"])
    assert passed.exit_code == 0
    assert "passed" in passed.output and "derivative of F1" in passed.output

    result = invoke(["claim", "add", "vendor reports 42% uplift", "--source", "F1",
                     "--load-bearing"])
    assert result.exit_code == 0, result.output
    assert "C1 asserted" in result.output
    assert "corroboration: 0" in result.output  # F1 is still grade "?"

    result = invoke(["grade", "F1", "--grade", "A", "--independence", "original"])
    assert result.exit_code == 0, result.output
    assert "grade A" in result.output

    result = invoke(["claim", "status", "C1", "verified"])
    assert result.exit_code == 0, result.output
    assert "C1 → verified" in result.output

    hot = invoke(["show"])
    assert hot.exit_code == 0
    assert "Q1" in hot.output and "RECENT LOG" in hot.output

    data = json.loads(invoke(["show", "--json"]).output)
    assert data["slug"] == "demo"
    assert data["open_questions"][0]["id"] == "Q1"

    by_status = json.loads(invoke(["show", "--claims", "--json"]).output)["by_status"]
    assert [c["id"] for c in by_status["verified"]] == ["C1"]

    doc = invoke(["doctor"])
    assert doc.exit_code == 0, doc.output
    assert "ok: no findings" in doc.output


# ---------------------------------------------------------------- grade / claims


def test_grade_without_flags_is_actionable(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["grade", "F1"])
    assert result.exit_code == 1
    assert "--grade" in result.output


def test_grade_unknown_source_id(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["grade", "F9", "--grade", "A"])
    assert result.exit_code == 1
    assert "unknown source id 'F9'" in result.output


def test_source_list_text_and_json(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    empty = invoke(["source", "list"])
    assert empty.exit_code == 0
    assert "no sources captured" in empty.output

    payload = tmp_path / "table.csv"
    payload.write_text("a,b\n", encoding="utf-8")
    invoke(["add-source", str(payload)])
    invoke(["grade", "F1", "--grade", "B", "--independence", "republisher"])

    listing = invoke(["source", "list"])
    assert listing.exit_code == 0, listing.output
    assert "F1 · file · B/republisher/fresh · sources/raw/F1.csv" in listing.output

    rows = json.loads(invoke(["source", "list", "--json"]).output)
    assert rows[0]["id"] == "F1"
    assert rows[0]["grade"] == "B"


def test_question_list_text_and_json(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    empty = invoke(["question", "list"])
    assert empty.exit_code == 0
    assert "no questions recorded" in empty.output

    invoke(["question", "add", "who funded it?"])
    invoke(["question", "add", "when?"])
    invoke(["question", "answer", "Q1"])

    listing = invoke(["question", "list"])
    assert listing.exit_code == 0, listing.output
    assert "Q1 · answered · who funded it?" in listing.output
    assert "Q2 · open · when?" in listing.output

    rows = json.loads(invoke(["question", "list", "--json"]).output)
    assert [(r["id"], r["status"]) for r in rows] == [("Q1", "answered"), ("Q2", "open")]


def test_pass_echoes_ts_and_reason(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["pass", "vendor blog", "--reason", "self-interested recap"])
    assert result.exit_code == 0, result.output
    # something citable back: the recorded timestamp and the reason
    assert "passed 20" in result.output  # ts starts with the year
    assert "self-interested recap" in result.output


def test_new_bad_slug_is_actionable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(["new", "Bad Slug!", "--kind", "scout"])
    assert result.exit_code == 1
    assert "invalid slug" in result.output
    assert not (tmp_path / "Bad Slug!").exists()


def test_doctor_fresh_scout_warns_but_exits_zero(tmp_path, monkeypatch):
    # SPEC §12: missing profile-required ledgers are WARNs while active.
    root = make_notebook(tmp_path / "demo")  # scout, nothing run yet
    monkeypatch.chdir(root)
    result = invoke(["doctor"])
    assert result.exit_code == 0, result.output
    assert "WARN missing-required" in result.output
    assert "ERROR" not in result.output


def test_claim_verified_below_bar_is_refused(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")  # scout: 1 independent original required
    monkeypatch.chdir(root)
    assert invoke(["claim", "add", "unbacked assertion"]).exit_code == 0
    result = invoke(["claim", "status", "C1", "verified"])
    assert result.exit_code == 1
    assert "cannot verify C1" in result.output


def test_claim_list_filters_and_json(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    invoke(["claim", "add", "first"])
    invoke(["claim", "add", "second"])
    invoke(["claim", "status", "C2", "needs-2nd"])
    listing = invoke(["claim", "list", "--status", "needs-2nd"])
    assert "C2" in listing.output and "C1" not in listing.output
    rows = json.loads(invoke(["claim", "list", "--json"]).output)
    assert [r["id"] for r in rows] == ["C1", "C2"]


def test_claim_status_rejects_unknown_status(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["claim", "status", "C1", "sideways"])
    assert result.exit_code == 2  # click.Choice rejects before the library runs
    assert "sideways" in result.output


# ---------------------------------------------------------------- questions / sessions


def test_question_answer_unknown_id(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["question", "answer", "Q9"])
    assert result.exit_code == 1
    assert "Q9" in result.output


def test_question_add_empty_text(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["question", "add", "  "])
    assert result.exit_code == 1
    assert "empty question text" in result.output


def test_session_start_end_and_double_end(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    started = invoke(["session", "start", "sweep", "--model", "m1", "--tools", "rg"])
    assert started.exit_code == 0, started.output
    path = Path(started.output.strip())
    assert path.is_file() and path.name.endswith("-sweep.md")
    assert "model: m1" in path.read_text(encoding="utf-8")

    ended = invoke(["session", "end", "sweep", "--summary", "done"])
    assert ended.exit_code == 0, ended.output
    assert "## Summary\ndone" in path.read_text(encoding="utf-8")

    again = invoke(["session", "end", "sweep", "--summary", "twice"])
    assert again.exit_code == 1
    assert "already ended" in again.output


# ---------------------------------------------------------------- show / doctor


def test_show_rejects_conflicting_flags(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["show", "--claims", "--stale"])
    assert result.exit_code == 1
    assert "at most one" in result.output


def test_show_stale_lists_open_questions(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    invoke(["question", "add", "still open?"])
    result = invoke(["show", "--stale"])
    assert result.exit_code == 0
    assert "OPEN QUESTIONS" in result.output


def test_doctor_exits_1_on_error_and_emits_json(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    (root / "notebook.md").unlink()
    text = invoke(["doctor"])
    assert text.exit_code == 1
    assert "missing-notebook" in text.output
    as_json = invoke(["doctor", "--json"])
    assert as_json.exit_code == 1
    findings = json.loads(as_json.output)
    assert {"level", "code", "message", "path"} <= set(findings[0])
    assert any(f["code"] == "missing-notebook" for f in findings)


# ---------------------------------------------------------------- index / export


def test_index_writes_registry(tmp_path, monkeypatch):
    make_notebook(tmp_path / "projects" / "demo")
    monkeypatch.chdir(tmp_path)
    result = invoke(["index", "--root", str(tmp_path / "projects")])
    assert result.exit_code == 0, result.output
    assert "indexed 1 notebook(s)" in result.output
    rows = [
        json.loads(line)
        for line in (tmp_path / "fliphome" / "index.jsonl").read_text().splitlines()
    ]
    assert rows[0]["slug"] == "demo"


def test_index_defaults_to_cwd(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = invoke(["index"])
    assert result.exit_code == 0, result.output
    assert "indexed 1 notebook(s)" in result.output


def test_index_nonexistent_root_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(["index", "--root", str(tmp_path / "nope")])
    assert result.exit_code == 2  # click validates existence


def test_export_csl_stdout_and_file(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    payload = tmp_path / "data.csv"
    payload.write_text("a,b\n", encoding="utf-8")
    invoke(["add-source", str(payload), "--kind", "file"])
    items = json.loads(invoke(["export", "csl"]).output)
    assert items[0]["id"] == "F1"
    out = tmp_path / "refs.json"
    result = invoke(["export", "csl", "--output", str(out)])
    assert result.exit_code == 0
    assert json.loads(out.read_text(encoding="utf-8")) == items


def test_export_bag_writes_bag_and_refuses_existing_dest(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    dest = tmp_path / "bag"
    result = invoke(["export", "bag", str(dest)])
    assert result.exit_code == 0, result.output
    assert (dest / "bagit.txt").is_file()
    assert (dest / "data" / "notebook.toml").is_file()
    manifest = (dest / "manifest-sha256.txt").read_text(encoding="utf-8")
    assert "data/notebook.md" in manifest
    again = invoke(["export", "bag", str(dest)])
    assert again.exit_code == 1
    assert "already exists" in again.output


# `flip export okf` wiring/behavior is owned by okf.py; see tests/test_okf.py.


# ---------------------------------------------------------------- misc


def test_version_flag():
    result = invoke(["--version"])
    assert result.exit_code == 0
    assert "flip" in result.output
