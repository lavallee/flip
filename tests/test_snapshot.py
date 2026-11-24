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
NOTEBOOK = {"draft_versions", "question_plan", "slug", "uid", "title", "kind", "status", "created", "updated", "visibility",
            "workflow", "idle_days"}
SOURCE = {"assessment_key", "grade_reason", "capture_fidelity", "id", "title", "description", "kind", "url", "local", "status", "grade",
          "independence", "freshness", "support", "notes", "path", "by", "at", "custody",
          "text", "cited_by", "read_by", "passages", "origin", "origin_key"}
CUSTODY = {"ts", "sha256", "bytes", "tool", "strategy", "status", "mime"}
CLAIM_KEYS = {"citations", "id", "text", "summary", "status", "load_bearing", "sources", "about",
              "corroboration", "exposure", "value", "unit", "notes", "stances", "rivals",
              "tests", "verified", "derives_from", "path", "by", "at",
              "corroboration_collapsed", "status_set"}
QUESTION = {"reporting", "answer_revisions", "status_note", "closed_reason", "answered_at", "id", "text", "status", "path", "by", "at", "review_by", "reopen_when",
            "resolves_via", "formulations", "evidence", "answer"}
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
    assert "strong basis 'measured'" in source["grade_reason"]
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

def test_question_evidence_survives_without_events(full):
    invoke(["question", "note", "Q1", "Two measurements.\n\n## Method\nSecond paragraph.",
            "--answers", "narrower", "--source", "F1"])
    invoke(["question", "note", "Q1", "Station series unavailable.", "--zero-yield", "corpus-gap"])
    (full / "log/events.jsonl").unlink()
    evidence = snap()["questions"][0]["evidence"]
    assert len({note.pop("anchor") for note in evidence}) == 2
    assert evidence == [
        {"date": snapshot.util.today(), "text": "Two measurements.\n\n## Method\nSecond paragraph.",
         "answers": "narrower", "zero_yield": None, "sources": ["F1"]},
        {"date": snapshot.util.today(), "text": "Station series unavailable.",
         "answers": None, "zero_yield": "corpus-gap", "sources": []},
    ]

def test_question_snapshot_preserves_multiline_answer(full):
    answer = "The tide rose.\n\n## Method\nGauge readings from both piers."
    invoke(["question", "answer", "Q1", "--note", answer])
    assert snap()["questions"][0]["answer"] == answer
    invoke(["question", "reopen", "Q1", "--because", "New gauge readings arrived"])
    invoke(["question", "answer", "Q1"])
    assert snap()["questions"][0]["answer"] is None

def test_evidence_links_identify_content_across_insertions():
    first = ("Evidence 2026-01-01", "First result")
    second = ("Evidence 2026-01-01", "Second result")
    def anchors(sections):
        return [row["anchor"] for row in snapshot.question_evidence(sections)]
    a, b = anchors([first, second])
    assert anchors([second, first, second]) == [b, a, f"{b}-2"]
    assert anchors([(first[0], "Corrected result")])[0] != a

def test_question_status_note_follows_current_disposition(full):
    invoke(["question", "dormant", "Q1", "--until", "2030-01-01", "--note", "Waiting for release."])
    assert snap()["questions"][0]["status_note"] == "Waiting for release."
    invoke(["question", "reopen", "Q1", "--because", "Release arrived."])
    assert snap()["questions"][0]["status_note"] == "Release arrived."
    invoke(["question", "close", "Q1", "--reason", "split", "--note", "Two time periods."])
    closed = snap()["questions"][0]
    assert (closed["status_note"], closed["closed_reason"]) == ("Two time periods.", "split")


def test_reporting_assignment_tracks_interview_and_held_check(full):
    qcmd = ["question", "report", "Q1", "R1"]
    invoke(["question", "assign", "Q1", "--route", "interview", "--holder", "Gauge operator",
            "--ask", "What did you see?", "--test", "Compare the dated gauge log.",
            "--terms", "On record, quotation subject to spelling check."])
    assert invoke([*qcmd, "reply", "An invented answer"], ok=False).exit_code
    invoke([*qcmd, "asked", "Which gauge did you read?", "--from-step", "0"])
    assert invoke([*qcmd, "reply", "First gauge.", "--from-step", "0"], ok=False).exit_code
    invoke([*qcmd, "reply", "First gauge.", "--from-step", "1"])
    assert invoke([*qcmd, "finding", "Wrong source", "--source", "C1"], ok=False).exit_code
    invoke([*qcmd, "finding", "The sheet identifies the same gauge.", "--source", "F1"])
    question = snap()["questions"][0]
    assignment, = question["reporting"]
    assert [step["kind"] for step in assignment["steps"]] == ["asked", "reply", "finding"]
    assert assignment["steps"][-1]["source"] == "F1"
    assert question["status"] == "open" and question["evidence"] == []
    exchange = [*qcmd, "reply", "At 07:03.", "--asked", "When did you read it?", "--from-step", "3"]
    assert invoke(exchange, ok=False).exit_code
    assert len(snap()["questions"][0]["reporting"][0]["steps"]) == 3
    invoke([*exchange, "--attribution", "On the record, as the duty operator."])
    steps = snap()["questions"][0]["reporting"][0]["steps"]
    assert steps[-2]["text"] == "When did you read it?"
    assert steps[-1]["attribution"] == "On the record, as the duty operator."
    assert invoke([*exchange, "--attribution", "Duplicate"], ok=False).exit_code


def test_saved_answer_versions_and_stale_editor(notebook):
    invoke(["question", "add", "Which counts changed?"])
    invoke(["question", "answer", "Q1", "--note", "Two landings [C1]."])
    invoke(["question", "revise", "Q1", "--note", "Three landings [C2].",
            "--because", "The East count arrived.", "--from-version", "v1"])
    stale = invoke(["question", "revise", "Q1", "--note", "Old edit", "--from-version", "v1"], ok=False)
    assert stale.exit_code and "at v2" in stale.output
    q = json.loads(invoke(["snapshot"]).output)["questions"][0]
    assert [v["version"] for v in q["answer_revisions"]] == ["v1", "v2"]
    assert q["answer_revisions"][0]["text"] == "Two landings [C1]."
    assert q["answer_revisions"][1]["by"] == "human:jane"
    assert q["answer_revisions"][1]["because"] == "The East count arrived."
    assert q["answer"] == "Three landings [C2]."


def test_answer_freezes_cited_rulings(full):
    invoke(["question", "answer", "Q1", "--note", "Reported [C1] from [F1]."])
    q = snap()["questions"][0]
    frozen = q["answer_revisions"][0]["evidence"]
    assert frozen["C1"]["status"] == "asserted"
    assert frozen["C1"]["sources"] == ["F1"]
    assert frozen["F1"]["basis"] == "measured"
    invoke(["claim", "status", "C1", "retracted", "--because", "Withdrawn."])
    invoke(["question", "revise", "Q1", "--note", "Withdrawn [C1]."])
    versions = snap()["questions"][0]["answer_revisions"]
    assert versions[0]["evidence"] == frozen
    assert versions[1]["evidence"]["C1"]["status"] == "retracted"
    assert versions[1]["evidence"]["F1"]["named"] is False


def test_legacy_answer_history_reads_matching_receipts_without_writing(notebook):
    from flip import pages, events
    invoke(["question", "add", "Which count?"])
    path = next(p for p in (notebook / "questions").glob("*.md") if p.name != "index.md")
    page = pages.read_page(path)
    page.fm["status"] = "answered"
    pages.write_page(path, page.fm, page.body + "\n## Answer\nLater count.\n")
    events.emit(notebook, "question.answer", "Q1", text="Earlier count.")
    events.emit(notebook, "question.answer", "Q1", text="Later count.")
    before = path.read_bytes()
    versions = snap()["questions"][0]["answer_revisions"]
    assert [v["text"] for v in versions] == ["Earlier count.", "Later count."]
    assert all(v["by"] == "human:jane" and "evidence" not in v for v in versions)
    assert path.read_bytes() == before


def test_manual_working_edit_is_preserved_and_stale_digest_refused(notebook):
    invoke(["question", "add", "Which count?"])
    invoke(["question", "answer", "Q1", "--note", "Original."])
    q = snap()["questions"][0]
    path = notebook / q["path"]
    path.write_text(path.read_text().replace("## Answer\nOriginal.", "## Answer\nManual edit."))
    result = invoke(["question", "revise", "Q1", "--note", "Next.", "--from-sha",
                     q["answer_revisions"][0]["sha256"]], ok=False)
    assert result.exit_code and "text changed" in result.output
    invoke(["question", "revise", "Q1", "--note", "Next.", "--from-version", "v1"])
    versions = snap()["questions"][0]["answer_revisions"]
    assert [v["text"] for v in versions] == ["Original.", "Manual edit.", "Next."]


def test_manuscript_save_preserves_v0_and_current(notebook, tmp_path):
    directory = notebook / "drafts"
    (directory / "v0").mkdir(parents=True)
    (directory / "v0" / "draft.md").write_text("Legacy draft.")
    path = tmp_path / "manuscript.txt"
    path.write_text("First version.\n")
    args = ["draft", "save", "--file", str(path), "--because", "New count.", "--from-version", "v0"]
    invoke(args)
    invoke(args)
    path.write_text("Another version.\n")
    assert invoke(args, ok=False).exit_code
    assert (directory / "current").readlink() == Path("v1")
    assert (directory / "v0/draft.md").read_text() == "Legacy draft."
    assert (directory / "v1/changelog.md").read_text() == "New count.\n"
    records = snap()["notebook"]["draft_versions"]
    assert [r["version"] for r in records] == ["v0","v1"]
    assert records[1]["by"] == "human:jane"


def test_source_regrade_updates_current_count_and_keeps_earlier_revision_receipt(full):
    invoke(["question", "answer", "Q1", "--note", "The tides follow a cycle [C1]."])
    invoke(["grade", "F1", "--independence", "self-reported", "--basis", "measured",
            "--method", "The agency measured its own tide tables."])
    assert snap()["claims"][0]["corroboration"] == 0
    invoke(["question", "revise", "Q1", "--from-version", "v1", "--note", "The agency reports a cycle [C1]."])
    first, second = snap()["questions"][0]["answer_revisions"]
    assert first["evidence"]["C1"]["corroboration"] == 1
    assert second["evidence"]["C1"]["corroboration"] == 0
    assert second["evidence"]["F1"]["method"] == "The agency measured its own tide tables."
    assert second["evidence"]["C1"]["citations"] == [{"ref": "F1", "role": "evidence"}]

def test_quoted_passage_examples_and_link_destinations_are_not_revision_evidence(full):
    from flip.revisions import evidence_at_save
    answer = "> ~~~~ quotation\n> Literal [C1] and ~~~ within the passage.\n> ~~~~\n\n[F1](<?nb=demo&q=Q1&read=claim:C1>) and `[C1]`."
    assert set(evidence_at_save(full, answer)) == {"F1"}
