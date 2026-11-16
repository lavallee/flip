"""Write events: log/events.jsonl, `flip events`, `flip source read`, and the
guard that keeps every command classified."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from flip import events, util
from flip.cli import main

TS = "2026-11-16T21:00:00Z"
ACTOR = "human:jane"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", ACTOR)


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(util, "utc_now", lambda: TS)
    monkeypatch.setattr(util, "stamp_slug", lambda: "2026-11-16T2100")


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


def rows(root: Path) -> list[dict]:
    return util.read_jsonl(root / "log" / "events.jsonl")


def add_source(root: Path, name: str = "doc.md") -> None:
    src = root.parent / name
    src.write_text("Tides follow the moon.\nSecond line.\nThird line.\n", encoding="utf-8")
    invoke(["add-source", str(src)])


# --- the guard: every command is classified --------------------------------------


def _leaves(group: click.Group, prefix: tuple[str, ...] = ()) -> list[str]:
    out = []
    for name, sub in group.commands.items():
        path = (*prefix, name)
        if isinstance(sub, click.Group):
            out.extend(_leaves(sub, path))
        else:
            out.append(" ".join(path))
    return out


def test_every_leaf_command_is_mapped_read_only_or_exempt():
    leaves = set(_leaves(main))
    classified = set(events.COMMAND_OPS) | set(events.READ_ONLY) | set(events.EXEMPT)
    unclassified = sorted(leaves - classified)
    assert not unclassified, (
        f"{unclassified} are in no table in flip/events.py: map each to the op(s) it "
        "emits (COMMAND_OPS), or declare it READ_ONLY, or EXEMPT with a reason"
    )
    assert not sorted(classified - leaves), "tables name commands that no longer exist"


def test_no_command_is_classified_twice():
    mapped, read_only, exempt = set(events.COMMAND_OPS), set(events.READ_ONLY), set(events.EXEMPT)
    assert not (mapped & read_only) and not (mapped & exempt) and not (read_only & exempt)


def test_mapped_ops_are_entity_dot_verb_and_exemptions_say_why():
    for command, ops in events.COMMAND_OPS.items():
        assert ops, command
        for op in ops:
            assert op == "rename" or len(op.split(".")) == 2, (command, op)
    assert all(reason.strip() for reason in events.EXEMPT.values())


# --- emit ------------------------------------------------------------------------


def test_emit_writes_a_flat_row_and_omits_empty_detail(notebook, frozen):
    row = events.emit(notebook, "claim.status", "C3", to="verified", note=None, tags=[],
                      **{"from": "asserted"})
    assert row == {"ts": TS, "actor": ACTOR, "op": "claim.status", "id": "C3",
                   "to": "verified", "from": "asserted"}
    assert rows(notebook)[-1] == row


def test_emit_refuses_detail_that_shadows_a_core_key(notebook):
    with pytest.raises(ValueError, match="actor"):
        events.emit(notebook, "log.add", actor="someone-else")


def test_emit_is_a_plain_append_that_reads_nothing(notebook, monkeypatch):
    # The ledger must cost a writer nothing that grows with the notebook: no
    # page scan, no ledger read, no view rebuild.
    from flip import pages, views

    def boom(*_args, **_kwargs):
        raise AssertionError("emit must not read the notebook")

    monkeypatch.setattr(pages, "iter_pages", boom)
    monkeypatch.setattr(pages, "iter_pages_tolerant", boom)
    monkeypatch.setattr(util, "read_jsonl", boom)
    monkeypatch.setattr(views, "regenerate", boom)
    events.emit(notebook, "log.add", text="x")


# --- one mutating command per entity group, exact row -----------------------------


def test_source_group_rows(notebook, frozen):
    add_source(notebook)
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "source.add", "id": "F1",
        "url": (notebook.parent / "doc.md").resolve().as_uri(), "kind": "file",
        "status": "captured", "title": "doc.md",
    }
    invoke(["grade", "F1", "--independence", "independent", "--basis", "measured"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "source.grade", "id": "F1",
        "grade": "A", "independence": "independent", "from": "?",
    }


def test_source_read_records_the_reader_and_changes_no_page(notebook, frozen):
    add_source(notebook)
    page = notebook / "references" / "doc.md"
    before = page.read_text(encoding="utf-8")
    out = invoke(["source", "read", "F1", "--note", "sections 2-4"])
    assert out.output.strip() == f"F1 · read {TS} · {ACTOR}"
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "source.read", "id": "F1", "note": "sections 2-4",
    }
    assert page.read_text(encoding="utf-8") == before
    refused = invoke(["source", "read", "F9"], ok=False)
    assert refused.exit_code != 0 and "unknown source id 'F9'" in refused.output


def test_claim_group_rows(notebook, frozen):
    add_source(notebook)
    text = "The moon drives the tides. " * 12  # longer than a clipped description
    invoke(["claim", "add", text, "--source", "F1", "--load-bearing"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "claim.add", "id": "C1",
        "text": text.strip(), "sources": ["F1"], "load_bearing": True,
    }
    invoke(["claim", "status", "C1", "needs-2nd"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "claim.status", "id": "C1",
        "to": "needs-2nd", "from": "asserted",
    }


def test_question_group_rows(notebook, frozen):
    invoke(["question", "add", "How much do tides vary?"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "question.add", "id": "Q1",
        "text": "How much do tides vary?",
    }
    invoke(["question", "answer", "Q1", "--note", "By up to 16 metres."])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "question.answer", "id": "Q1",
        "text": "By up to 16 metres.", "from": "open",
    }


def test_decision_pass_and_log_rows(notebook, frozen):
    invoke(["decide", "--question", "Which model?", "--decision", "Equilibrium theory",
            "--why", "Simple enough", "--rejected", "dynamic theory"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "decision.add", "id": "D1",
        "question": "Which model?", "decision": "Equilibrium theory",
        "why": "Simple enough", "rejected": ["dynamic theory"],
    }
    invoke(["pass", "a blog post", "--reason", "no data", "--url", "https://c.test/x"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "pass.add",
        "text": "a blog post", "reason": "no data", "url": "https://c.test/x",
    }
    invoke(["log", "fetched the tide tables"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "log.add", "text": "fetched the tide tables",
    }
    # the work log itself is unchanged in shape
    assert util.read_jsonl(notebook / "log" / "log.jsonl")[-1] == {
        "ts": TS, "text": "fetched the tide tables", "actor": ACTOR,
    }


def test_lead_and_directive_rows(notebook, frozen):
    invoke(["lead", "add", "https://a.test/one", "--title", "One"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "lead.add", "url": "https://a.test/one",
        "title": "One",
    }
    invoke(["lead", "dismiss", "https://a.test/one", "--reason", "off topic"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "lead.dismiss", "url": "https://a.test/one",
        "reason": "off topic",
    }
    invoke(["directive", "add", "Primary sources only."])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "directive.add", "id": "DR1",
        "text": "Primary sources only.",
    }
    invoke(["directive", "withdraw", "DR1", "--because", "scope widened"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "directive.withdraw", "id": "DR1",
        "because": "scope widened",
    }


def test_session_rows(notebook, frozen):
    invoke(["session", "start", "first-pass", "--model", "some-model"])
    path = "sessions/2026-11-16T2100-first-pass.md"
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "session.start", "path": path, "model": "some-model",
    }
    invoke(["session", "end", "first-pass", "--summary", "Read the tables."])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "session.end", "path": path,
        "text": "Read the tables.",
    }


def test_forecast_and_commission_rows(notebook, frozen):
    invoke(["forecast", "add", "Will the barrier close in 2199?",
            "--resolves-by", "2199-03-31", "--resolves-via", "agency-log",
            "--annul-if", "the barrier is removed",
            "--probability", "0.3", "--confidence", "0.5"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "forecast.add", "id": "FC1",
        "text": "Will the barrier close in 2199?", "resolves_by": "2199-03-31",
        "probability": 0.3,
    }
    invoke(["commission", "add", "refresh the tide rows", "--universe", "180 rows",
            "--stop", "each row checked once", "--does-not-redo", "audited rows"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "commission.add", "id": "K1",
        "text": "refresh the tide rows", "status": "proposed",
    }
    invoke(["commission", "status", "K1", "dispatched"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "commission.status", "id": "K1",
        "to": "dispatched", "from": "proposed",
    }


def test_rename_kind_and_transcript_rows(notebook, frozen):
    invoke(["question", "add", "How much do tides vary?"])
    invoke(["rename", "Q1", "tide-range"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "rename", "id": "Q1",
        "to": "questions/tide-range.md", "from": "questions/how-much-do-tides-vary.md",
    }
    invoke(["kind", "adopt", "lit-review"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "kind.adopt", "kind": "lit-review", "from": "ledger",
    }
    talk = notebook.parent / "talk.md"
    talk.write_text("A: one\nB: two\nA: three\n", encoding="utf-8")
    invoke(["session", "start", "chat"])
    invoke(["session", "transcript", "chat", "--file", str(talk)])
    ops = [r["op"] for r in rows(notebook)]
    assert ops[-2:] == ["source.add", "session.transcript"]
    invoke(["transcript", "excerpt", "T1", "--lines", "1-2", "--label", "opening"])
    assert rows(notebook)[-1] == {
        "ts": TS, "actor": ACTOR, "op": "transcript.excerpt", "id": "T1",
        "label": "opening", "lines": [1, 2],
    }


def test_a_refused_write_emits_nothing(notebook):
    before = (notebook / "log" / "events.jsonl").exists()
    invoke(["claim", "status", "C9", "verified"], ok=False)
    invoke(["question", "answer", "Q9"], ok=False)
    assert (notebook / "log" / "events.jsonl").exists() == before is False


def test_python_callers_emit_too(notebook, frozen):
    from flip import ledgers

    ledgers.add_question(notebook, "Asked from a script?")
    assert rows(notebook)[-1]["op"] == "question.add"


# --- flip events -----------------------------------------------------------------


@pytest.fixture
def history(notebook) -> Path:
    for n, (ts, op, entity) in enumerate([
        ("2026-11-10T09:00:00Z", "source.add", "A1"),
        ("2026-11-11T09:00:00Z", "claim.add", "C1"),
        ("2026-11-12T09:00:00Z", "claim.status", "C1"),
        ("2026-11-13T09:00:00Z", "claim.status", "C2"),
        ("2026-11-14T09:00:00Z", "log.add", None),
    ]):
        row = {"ts": ts, "actor": ACTOR, "op": op}
        if entity:
            row["id"] = entity
        row["n"] = n
        util.append_jsonl(notebook / "log" / "events.jsonl", row)
    return notebook


def listed(*args: str) -> list[int]:
    data = json.loads(invoke(["events", "--json", *args]).output)
    assert data["schema"] == "flip-events/1"
    assert set(data) == {"schema", "events"}
    return [row["n"] for row in data["events"]]


def test_events_lists_oldest_first(history):
    assert listed() == [0, 1, 2, 3, 4]


def test_events_since_is_inclusive_and_takes_a_bare_date(history):
    assert listed("--since", "2026-11-12T09:00:00Z") == [2, 3, 4]
    assert listed("--since", "2026-11-13") == [3, 4]


def test_events_op_is_a_prefix(history):
    assert listed("--op", "claim") == [1, 2, 3]
    assert listed("--op", "claim.status") == [2, 3]
    assert listed("--op", "source.") == [0]


def test_events_id_matches_exactly(history):
    assert listed("--id", "C1") == [1, 2]
    assert listed("--id", "C") == []


def test_events_limit_keeps_the_newest_still_oldest_first(history):
    assert listed("--limit", "2") == [3, 4]
    assert listed("--op", "claim", "--limit", "1") == [3]
    assert invoke(["events", "--limit", "0"], ok=False).exit_code != 0


def test_events_text_and_empty(history, tmp_path, monkeypatch):
    out = invoke(["events", "--id", "C2"]).output
    assert out.strip() == f"2026-11-13T09:00:00Z · {ACTOR} · claim.status · C2  n=3"
    empty = tmp_path / "empty"
    invoke(["new", "empty", "--dest", str(empty)])
    monkeypatch.chdir(empty)
    assert "no events yet" in invoke(["events"]).output
    assert json.loads(invoke(["events", "--json"]).output) == {
        "schema": "flip-events/1", "events": [],
    }


# --- the new ledgers are ordinary ledgers to doctor and export ---------------------


def _written(root: Path) -> Path:
    invoke(["directive", "add", "Primary sources only."])
    invoke(["lead", "add", "https://a.test/one"])
    invoke(["log", "x"])
    return root


def test_doctor_accepts_the_new_ledgers_and_a_stray_id_lock(notebook):
    _written(notebook)
    (notebook / ".flip" / "ids.lock").write_text("", encoding="utf-8")
    report = json.loads(invoke(["doctor", "--json"], ok=False).output)
    findings = report["findings"] if isinstance(report, dict) else report
    text = json.dumps(findings)
    for name in ("events.jsonl", "leads.jsonl", "directives.jsonl", "ids.lock", "DR1"):
        assert name not in text, findings


def test_doctor_reports_a_corrupt_new_ledger(notebook):
    from flip import doctor

    _written(notebook)
    for name in ("events", "leads", "directives"):
        with open(notebook / "log" / f"{name}.jsonl", "a", encoding="utf-8") as f:
            f.write("not json\n")
    bad = {f.path for f in doctor.run_doctor(notebook) if f.code == "bad-jsonl"}
    assert bad == {"log/events.jsonl", "log/leads.jsonl", "log/directives.jsonl"}


def test_exports_treat_the_new_ledgers_like_the_passed_ledger(notebook, tmp_path, monkeypatch):
    from flip import export, okf

    names = ("passed.jsonl", "events.jsonl", "leads.jsonl", "directives.jsonl")
    _written(notebook)
    invoke(["pass", "a thing", "--reason", "no"])
    bag = export.export_bag(notebook, tmp_path / "bag")
    assert all((bag / "data" / "log" / n).is_file() for n in names)
    full = okf.export_okf(notebook, tmp_path / "okf-full", include_private=True)
    assert all((full / "log" / n).is_file() for n in names)
    assert not (bag / "data" / ".flip").exists() and not (full / ".flip").exists()

    # A public render without the source trail withholds every ledger alike.
    public = tmp_path / "public"
    invoke(["new", "public", "--visibility", "public", "--dest", str(public)])
    monkeypatch.chdir(public)
    _written(public)
    invoke(["pass", "a thing", "--reason", "no"])
    withheld = okf.export_okf(public, tmp_path / "okf")
    assert not any((withheld / "log" / n).exists() for n in names)
