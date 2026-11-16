"""`flip snapshot`: the flip-snapshot/1 document over a notebook holding one of
everything."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import snapshot
from flip.cli import main

CLAIM = ("The moon's gravity is the main driver of ocean tides on Earth, with the sun "
         "contributing roughly half as much again, which is why spring tides at new and "
         "full moon run markedly higher than neap tides at the quarters.")

TOP = ["schema", "generated", "root", "notebook", "sources", "claims", "questions",
       "decisions", "sessions", "forecasts", "commissions", "passed", "leads",
       "directives", "log"]
NOTEBOOK = {"slug", "uid", "title", "kind", "status", "created", "updated", "visibility",
            "workflow", "idle_days"}
SOURCE = {"id", "title", "description", "kind", "url", "local", "status", "grade",
          "independence", "freshness", "support", "notes", "path", "by", "at", "custody",
          "text", "cited_by", "read_by"}
CUSTODY = {"ts", "sha256", "bytes", "tool", "strategy", "status", "mime"}
CLAIM_KEYS = {"id", "text", "summary", "status", "load_bearing", "sources", "about",
              "corroboration", "exposure", "value", "unit", "notes", "stances", "rivals",
              "tests", "verified", "derives_from", "path", "by", "at"}
QUESTION = {"id", "text", "status", "path", "by", "at", "review_by", "reopen_when",
            "resolves_via", "formulations"}
DECISION = {"id", "question", "decision", "why", "rejected", "path", "by", "at"}
SESSION = {"path", "actor", "model", "started", "ended", "goal", "workflow", "phase", "item"}
PASSED = {"ts", "text", "reason", "url", "actor"}
LEAD = {"url", "title", "snippet", "query", "note", "ts", "actor", "state", "source_id",
        "reason"}
DIRECTIVE = {"id", "text", "state", "ts", "actor", "withdrawn_ts", "withdrawn_actor",
             "because"}


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
    invoke(["new", "demo", "--kind", "ledger", "--title", "Tides", "--dest", str(root)])
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def full(notebook, tmp_path, monkeypatch) -> Path:
    doc = tmp_path / "doc.md"
    doc.write_text("Tides follow the moon.\n", encoding="utf-8")
    invoke(["add-source", str(doc), "--note", "tide tables"])
    invoke(["grade", "F1", "--independence", "independent", "--basis", "measured",
            "--notes", "agency data"])
    monkeypatch.setenv("FLIP_ACTOR", "agent:reader")
    invoke(["source", "read", "F1", "--note", "all of it"])
    monkeypatch.setenv("FLIP_ACTOR", "human:jane")
    invoke(["claim", "add", CLAIM, "--source", "F1", "--load-bearing"])
    invoke(["question", "add", "How much do tides vary?", "--resolves-via", "tide-gauges"])
    invoke(["decide", "--question", "Which model?", "--decision", "Equilibrium theory",
            "--why", "Simple enough for a first pass", "--rejected", "dynamic theory"])
    invoke(["pass", "a blog post", "--reason", "no data", "--url", "https://b.test/passed"])
    for url in (doc.as_uri(), "https://b.test/passed", "https://c.test/dismissed",
                "https://d.test/open"):
        invoke(["lead", "add", url])
    invoke(["lead", "dismiss", "https://c.test/dismissed", "--reason", "off topic"])
    invoke(["directive", "add", "Primary sources only."])
    invoke(["directive", "add", "Stop at ten sources."])
    invoke(["directive", "withdraw", "DR2", "--because", "limit lifted"])
    invoke(["session", "start", "first-pass", "--model", "some-model"])
    for n in range(3):
        invoke(["log", f"step {n}"])
    return notebook


def snap(*args: str) -> dict:
    return json.loads(invoke(["snapshot", *args]).output)


def test_top_level_shape_and_notebook_block(full):
    data = snap()
    assert list(data) == TOP
    assert data["schema"] == "flip-snapshot/1"
    assert data["root"] == str(full.resolve())
    assert data["generated"].endswith("Z")
    nb = data["notebook"]
    assert set(nb) == NOTEBOOK
    assert (nb["slug"], nb["title"], nb["kind"], nb["status"]) == (
        "demo", "Tides", "ledger", "active")
    assert nb["uid"].startswith("nb-") and nb["idle_days"] == 0 and nb["workflow"] is None


def test_source_carries_grade_custody_citations_and_readers(full):
    (source,) = snap()["sources"]
    assert set(source) == SOURCE
    assert (source["id"], source["kind"], source["status"]) == ("F1", "file", "captured")
    assert (source["grade"], source["independence"]) == ("A", "independent")
    assert source["support"] == {"basis": "measured"} and source["notes"] == "agency data"
    assert source["url"].startswith("file://") and source["local"] == "sources/raw/F1.md"
    assert source["path"] == "references/doc.md" and source["by"] == "human:jane"
    assert set(source["custody"]) == CUSTODY
    assert source["custody"]["bytes"] == 23 and len(source["custody"]["sha256"]) == 64
    assert source["text"] is None
    assert source["cited_by"] == ["C1"]
    assert [set(r) for r in source["read_by"]] == [{"actor", "ts"}]
    assert source["read_by"][0]["actor"] == "agent:reader"


def test_source_text_is_the_extracted_file_path_when_there_is_one(full):
    text = full / "sources" / "text" / "F1.txt"
    text.parent.mkdir(parents=True)
    text.write_text("Tides follow the moon.\n", encoding="utf-8")
    assert snap()["sources"][0]["text"] == "sources/text/F1.txt"


def test_claim_text_is_whole_with_footnote_markers_stripped(full):
    (claim,) = snap()["claims"]
    assert set(claim) == CLAIM_KEYS
    assert claim["text"] == CLAIM
    assert "[^" not in claim["text"]
    assert claim["summary"].endswith("…") and len(claim["summary"]) < len(CLAIM)
    assert (claim["id"], claim["status"], claim["load_bearing"]) == ("C1", "asserted", True)
    assert (claim["sources"], claim["about"], claim["corroboration"]) == (["F1"], [], 1)
    assert claim["stances"] == claim["tests"] == claim["verified"] == claim["rivals"] == []
    assert claim["derives_from"] == [] and isinstance(claim["exposure"], str)
    # the page itself still carries the marker the snapshot stripped
    assert "[^F1]" in (full / claim["path"]).read_text(encoding="utf-8")


def test_question_and_decision(full):
    data = snap()
    (question,) = data["questions"]
    assert set(question) == QUESTION
    assert (question["id"], question["text"], question["status"]) == (
        "Q1", "How much do tides vary?", "open")
    assert question["resolves_via"] == ["tide-gauges"] and question["reopen_when"] == []
    (decision,) = data["decisions"]
    assert set(decision) == DECISION
    assert decision == {
        "id": "D1", "question": "Which model?", "decision": "Equilibrium theory",
        "why": "Simple enough for a first pass", "rejected": ["dynamic theory"],
        "path": "decisions/equilibrium-theory.md", "by": "human:jane", "at": decision["at"],
    }


def test_passed_leads_directives_sessions_and_log(full, tmp_path):
    data = snap()
    (passed,) = data["passed"]
    assert set(passed) == PASSED and passed["url"] == "https://b.test/passed"

    assert [set(lead) for lead in data["leads"]] == [LEAD] * 4
    by_state = {lead["state"]: lead for lead in data["leads"]}
    assert set(by_state) == {"captured", "passed", "dismissed", "open"}
    assert by_state["captured"]["source_id"] == "F1"
    assert by_state["passed"]["reason"] == "no data"
    assert by_state["dismissed"]["reason"] == "off topic"

    assert [set(d) for d in data["directives"]] == [DIRECTIVE] * 2
    assert [(d["id"], d["state"]) for d in data["directives"]] == [
        ("DR1", "active"), ("DR2", "withdrawn")]
    assert data["directives"][1]["because"] == "limit lifted"

    (session,) = data["sessions"]
    assert set(session) == SESSION
    assert session["path"].endswith("-first-pass.md") and session["model"] == "some-model"
    assert session["actor"] == "human:jane" and session["ended"] is None

    assert [row["text"] for row in data["log"]] == ["step 0", "step 1", "step 2"]
    assert data["forecasts"] == [] and data["commissions"] == []


def test_log_limit_keeps_the_newest_rows(full):
    assert [row["text"] for row in snap("--log-limit", "2")["log"]] == ["step 1", "step 2"]
    assert snap("--log-limit", "0")["log"] == []
    assert invoke(["snapshot", "--log-limit", "-1"], ok=False).exit_code != 0


def test_forecasts_and_commissions_match_their_list_commands(full):
    invoke(["forecast", "add", "Will the barrier close in 2199?",
            "--resolves-by", "2199-03-31", "--resolves-via", "agency-log",
            "--annul-if", "the barrier is removed",
            "--probability", "0.3", "--confidence", "0.5"])
    invoke(["commission", "add", "refresh the tide rows", "--universe", "180 rows",
            "--stop", "each row checked once", "--does-not-redo", "audited rows"])
    data = snap()
    assert data["forecasts"] == json.loads(invoke(["forecast", "list", "--json"]).output)
    assert data["commissions"] == json.loads(invoke(["commission", "list", "--json"]).output)


def test_snapshot_is_read_only_and_ignores_visibility(full):
    def tree() -> dict[str, bytes]:
        return {p.relative_to(full).as_posix(): p.read_bytes()
                for p in sorted(full.rglob("*")) if p.is_file()}

    before = tree()
    data = snapshot.snapshot(full)
    assert tree() == before
    # an internal notebook is read whole: local, not a publication surface
    assert data["notebook"]["visibility"] != "public" and data["sources"][0]["url"]


def test_empty_notebook_snapshots_to_empty_lists(notebook):
    data = snap()
    assert list(data) == TOP
    for key in TOP[4:]:
        assert data[key] == [], key


def test_a_source_older_than_the_event_ledger_has_no_kind(full):
    (full / "log" / "events.jsonl").unlink()
    source = snapshot.snapshot(full)["sources"][0]
    assert source["kind"] is None and source["read_by"] == []
