"""The leads ledger: `flip find` keeps its candidates, `flip lead`, derived state."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import leads, query, util
from flip.cli import main

CANDIDATES = (
    '{"results": [{"url": "https://a.test/one", "title": "One", "snippet": "first"}, '
    '{"url": "https://b.test/two", "title": "Two"}]}'
)


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


def research_tool(tmp_path: Path, stdout: str) -> None:
    """Stub the [research].find tool with a script that prints `stdout`."""
    script = tmp_path / "res"
    script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{stdout}\nEOF\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    home = tmp_path / "fliphome"
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text(
        f'[research]\nfind = "{script} {{query}}"\n', encoding="utf-8"
    )


def ledger(root: Path) -> list[dict]:
    return util.read_jsonl(root / "log" / "leads.jsonl")


def states(root: Path) -> dict[str, str]:
    return {row["url"]: row["state"] for row in leads.list_leads(root, include_all=True)}


# --- flip find keeps its candidates ----------------------------------------------


def test_find_appends_each_candidate_with_the_spec_row_shape(notebook, tmp_path):
    research_tool(tmp_path, CANDIDATES)
    result = query.research_find(notebook, "tides")
    assert result.new == 2
    first, second = ledger(notebook)
    assert set(first) == {"ts", "query", "url", "title", "snippet", "actor"}
    assert (first["query"], first["url"], first["title"], first["snippet"], first["actor"]) == (
        "tides", "https://a.test/one", "One", "first", "human:jane")
    assert set(second) == {"ts", "query", "url", "title", "actor"}  # no snippet returned
    # still captures nothing
    assert not (notebook / "references").exists()


def test_find_never_duplicates_a_url(notebook, tmp_path):
    research_tool(tmp_path, CANDIDATES)
    invoke(["find", "tides"])
    again = invoke(["find", "tides again"])
    assert "0 new lead(s)" in again.output
    # a different spelling of the same address, and a repeat inside one result
    research_tool(tmp_path, (
        '[{"url": "HTTPS://A.test/one/"}, {"url": "https://a.test/one#top"}, '
        '{"url": "https://c.test/three"}, {"url": "https://c.test/three"}]'
    ))
    out = json.loads(invoke(["find", "more", "--json"]).output)
    assert out["new_leads"] == 1 and len(out["candidates"]) == 4
    assert [row["url"] for row in ledger(notebook)] == [
        "https://a.test/one", "https://b.test/two", "https://c.test/three",
    ]


def test_find_with_no_candidates_writes_no_ledger(notebook, tmp_path):
    research_tool(tmp_path, '{"results": []}')
    assert "no candidates returned" in invoke(["find", "nothing"]).output
    assert not (notebook / "log" / "leads.jsonl").exists()


def test_a_dismissed_lead_is_not_reopened_by_a_later_search(notebook, tmp_path):
    research_tool(tmp_path, CANDIDATES)
    invoke(["find", "tides"])
    invoke(["lead", "dismiss", "https://b.test/two"])
    invoke(["find", "tides"])
    assert states(notebook)["https://b.test/two"] == "dismissed"
    assert len([r for r in ledger(notebook) if "event" not in r]) == 2


# --- state derivation ------------------------------------------------------------


def test_state_is_derived_from_sources_the_passed_ledger_and_dismissals(notebook, tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("words\n", encoding="utf-8")
    for url in (doc.as_uri(), "https://b.test/passed", "https://c.test/dismissed",
                "https://d.test/open"):
        invoke(["lead", "add", url])
    assert set(states(notebook).values()) == {"open"}

    invoke(["add-source", str(doc)])
    invoke(["pass", "b", "--reason", "thin", "--url", "https://b.test/passed/"])
    invoke(["lead", "dismiss", "https://c.test/dismissed", "--reason", "off topic"])

    rows = {row["url"]: row for row in leads.list_leads(notebook, include_all=True)}
    captured = rows[doc.as_uri()]
    assert (captured["state"], captured["source_id"]) == ("captured", "F1")
    passed = rows["https://b.test/passed"]
    assert (passed["state"], passed["reason"], passed["source_id"]) == ("passed", "thin", None)
    dismissed = rows["https://c.test/dismissed"]
    assert (dismissed["state"], dismissed["reason"]) == ("dismissed", "off topic")
    assert rows["https://d.test/open"]["state"] == "open"
    # nothing about state was written back to the lead rows
    assert all("state" not in row and "source_id" not in row for row in ledger(notebook))
    # default list is the open ones only
    assert [r["url"] for r in leads.list_leads(notebook)] == ["https://d.test/open"]


def test_captured_wins_over_passed_and_dismissed(notebook, tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("words\n", encoding="utf-8")
    invoke(["lead", "add", doc.as_uri()])
    invoke(["lead", "dismiss", doc.as_uri()])
    invoke(["pass", "it", "--reason", "r", "--url", doc.as_uri()])
    invoke(["add-source", str(doc)])
    assert states(notebook) == {doc.as_uri(): "captured"}


def test_a_source_page_coordinate_captures_a_lead(notebook):
    invoke(["lead", "add", "https://paper.test/x"])
    page = notebook / "references" / "x.md"
    page.parent.mkdir()
    page.write_text(
        "---\ntype: Source\nid: A1\naliases: [A1]\ntitle: X\n"
        "resource: https://paper.test/x/\ngrade: '?'\n---\n\n# X\n", encoding="utf-8")
    row = leads.list_leads(notebook, include_all=True)[0]
    assert (row["state"], row["source_id"]) == ("captured", "A1")


# --- flip lead -------------------------------------------------------------------


def test_lead_add_dismiss_list_text_and_json(notebook):
    out = invoke(["lead", "add", "https://a.test/one", "--title", "One", "--note", "footnote 3"])
    assert out.output.strip() == "lead · https://a.test/one · One"
    assert ledger(notebook)[0]["note"] == "footnote 3" and "query" not in ledger(notebook)[0]
    invoke(["lead", "add", "https://b.test/two"])
    out = invoke(["lead", "dismiss", "https://b.test/two/", "--reason", "duplicate"])
    assert out.output.strip() == "dismissed · https://b.test/two · duplicate"
    assert ledger(notebook)[-1]["event"] == "dismiss"

    text = invoke(["lead", "list"]).output
    assert "open · One" in text and "b.test" not in text
    everything = invoke(["lead", "list", "--all"]).output
    assert "dismissed · https://b.test/two" in everything and "reason: duplicate" in everything

    rows = json.loads(invoke(["lead", "list", "--all", "--json"]).output)
    assert [set(r) for r in rows] == [{
        "url", "title", "snippet", "query", "note", "ts", "actor", "state", "source_id",
        "reason",
    }] * 2
    assert [r["state"] for r in rows] == ["open", "dismissed"]
    assert json.loads(invoke(["lead", "list", "--json"]).output) == rows[:1]


def test_lead_refusals_are_actionable(notebook):
    invoke(["lead", "add", "https://a.test/one"])
    twice = invoke(["lead", "add", "https://a.test/one/"], ok=False)
    assert twice.exit_code != 0 and "already a lead (open)" in twice.output
    unknown = invoke(["lead", "dismiss", "https://z.test"], ok=False)
    assert unknown.exit_code != 0 and "is not a lead" in unknown.output
    invoke(["lead", "dismiss", "https://a.test/one"])
    again = invoke(["lead", "dismiss", "https://a.test/one"], ok=False)
    assert again.exit_code != 0 and "already dismissed" in again.output
    assert "no open leads" in invoke(["lead", "list"]).output


def test_url_key_compares_spellings_without_rewriting_them():
    assert leads.url_key("HTTPS://Example.TEST/Path/#frag") == "https://example.test/Path"
    assert leads.url_key("https://example.test/a?b=1") == "https://example.test/a?b=1"
    assert leads.url_key("https://example.test/a") != leads.url_key("https://example.test/A")
    assert leads.url_key("10.1000/xyz") == "10.1000/xyz"
    assert leads.url_key("  ") == ""
