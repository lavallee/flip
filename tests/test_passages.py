"""Passage pins on any held source (SPEC §5.7): pin by quote or by lines, read
back against the digest, list, unpin, cite from a claim, and doctor's checks."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import claims, doctor, events, pages, passages, snapshot, util
from flip.cli import main

DOC = (
    "The district budget for FY2026\n"
    "sets aside $5,585,576 to be designated\n"
    "for tax relief in the 2026-27 budget cycle.\n"
    "The board voted seven to zero.\n"
    "The board voted seven to zero.\n"
)
EXTRACTED = (
    "Directory of clinics\n"
    "Newark Health Center   Newark\n"
    "Camden Family Clinic   Camden\n"
)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")


def invoke(args: list[str], ok: bool = True):
    result = CliRunner().invoke(main, args)
    if ok:
        assert result.exit_code == 0, result.output
    return result


@pytest.fixture
def nb(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "demo"
    invoke(["new", "demo", "--kind", "ledger", "--dest", str(root)])
    monkeypatch.chdir(root)
    doc = tmp_path / "budget.txt"
    doc.write_text(DOC, encoding="utf-8")
    invoke(["add-source", str(doc)])
    return root.resolve()


def _set_extractor(tmp_path: Path, monkeypatch, text: str) -> None:
    """An [extractors].html lane that writes `text` — a lossy extraction,
    standing in for one that dropped a ZIP column."""
    payload = tmp_path / "extracted.txt"
    payload.write_text(text, encoding="utf-8")
    script = tmp_path / "fakeextract"
    script.write_text(f'#!/bin/sh\ncat "{payload}" > "$2"\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    home = tmp_path / "fliphome"
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text(
        f'[extractors]\nhtml = "{script} {{src}} {{out}}"\n', encoding="utf-8"
    )


@pytest.fixture
def html(nb, tmp_path, monkeypatch) -> Path:
    """F2: a captured web page with a logged text derivative."""
    page = tmp_path / "clinics.html"
    page.write_text("<table><tr><td>Newark Health Center</td><td>Newark</td>"
                    "<td>07102</td></tr></table>", encoding="utf-8")
    invoke(["add-source", str(page)])
    _set_extractor(tmp_path, monkeypatch, EXTRACTED)
    invoke(["extract", "F2", "--method", "markup-strip"])
    return nb


def _page(root: Path, sid: str) -> pages.Page:
    return passages.find_source(root, sid)


# --- pinning by quote ------------------------------------------------------------


def test_a_quote_pin_records_locator_and_both_digests(nb):
    record = passages.pin(nb, "F1", "relief", quote="sets aside $5,585,576 to be designated")
    held = (nb / "sources" / "raw" / "F1.txt").read_bytes()
    start = DOC.index("sets aside")
    assert record["held"] == "raw"
    assert record["lines"] == [2, 2]
    assert record["span"] == [start, start + len("sets aside $5,585,576 to be designated")]
    assert record["sha256"] == hashlib.sha256(
        b"sets aside $5,585,576 to be designated").hexdigest()
    assert record["held_sha256"] == hashlib.sha256(held).hexdigest()
    assert record["words"] == 6 and record["by"] == "agent:test" and record["at"]
    assert "extraction" not in record and "match" not in record
    # stored on the page, never the text itself
    stored = passages.records(_page(nb, "F1").fm)
    assert stored == [record] and "text" not in stored[0]


def test_a_quote_may_cross_line_breaks_and_the_pin_holds_the_held_words(nb):
    record = passages.pin(nb, "F1", "relief",
                          quote="to be designated for tax relief")
    assert record["match"] == "whitespace" and record["lines"] == [2, 3]
    out = passages.read_pin(nb, "F1", "relief")
    assert out["text"] == "to be designated\nfor tax relief"  # as held, not as typed


def test_a_quote_that_does_not_occur_names_the_nearest_miss(nb):
    with pytest.raises(SystemExit) as exc:
        passages.pin(nb, "F1", "relief", quote="sets aside $5,585,577 to be designated")
    msg = str(exc.value)
    assert "does not occur in F1's raw capture" in msg
    assert "Nearest miss" in msg and "line 2" in msg and "$5,585,576" in msg
    assert passages.records(_page(nb, "F1").fm) == []  # refusal writes nothing


def test_a_case_only_miss_says_so(nb):
    with pytest.raises(SystemExit, match="different capitalisation at line 4"):
        passages.pin(nb, "F1", "vote", quote="the Board voted seven to zero")


def test_a_repeated_quote_needs_an_occurrence_or_context(nb):
    with pytest.raises(SystemExit, match=r"occurs 2 times .*lines 4, 5.*--occurrence"):
        passages.pin(nb, "F1", "vote", quote="The board voted seven to zero.")
    second = passages.pin(nb, "F1", "vote", quote="The board voted seven to zero.",
                          occurrence=2)
    assert second["lines"] == [5, 5]
    with pytest.raises(SystemExit, match="out of range"):
        passages.pin(nb, "F1", "vote3", quote="The board voted seven to zero.",
                     occurrence=3)


def test_context_disambiguates_a_repeated_quote(nb):
    record = passages.pin(
        nb, "F1", "vote", quote="The board voted",
        context="budget cycle.\nThe board voted seven",
    )
    assert record["lines"] == [4, 4]
    with pytest.raises(SystemExit, match="occurs 2 times"):
        passages.pin(nb, "F1", "v2", quote="voted", context="The board voted seven to zero.")


def test_a_line_pin_works_on_any_held_text(nb):
    record = passages.pin(nb, "F1", "opening", lines=(1, 2))
    assert record["lines"] == [1, 2] and "span" not in record
    assert passages.read_pin(nb, "F1", "opening")["text"] == "\n".join(DOC.splitlines()[:2])
    with pytest.raises(SystemExit, match="runs past the end"):
        passages.pin(nb, "F1", "late", lines=(4, 9))


def test_labels_are_stable_and_validated(nb):
    passages.pin(nb, "F1", "relief", quote="tax relief")
    with pytest.raises(SystemExit, match="already pins 'relief'"):
        passages.pin(nb, "F1", "relief", quote="budget cycle")
    with pytest.raises(SystemExit, match="invalid passage label"):
        passages.pin(nb, "F1", "Bad Label", quote="budget cycle")
    with pytest.raises(SystemExit, match="exactly one of --quote or --lines"):
        passages.pin(nb, "F1", "x", quote="tax", lines=(1, 1))


def test_a_binary_raw_capture_without_a_derivative_is_refused(nb, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n\x00\x01binary")
    invoke(["add-source", str(pdf)])
    with pytest.raises(SystemExit, match="not plain text.*flip extract F2"):
        passages.pin(nb, "F2", "x", lines=(1, 1))


# --- the held copy: raw versus the text derivative -------------------------------


def test_the_default_on_an_extracted_source_is_the_derivative_and_says_so(html):
    record = passages.pin(html, "F2", "newark", quote="Newark Health Center")
    text = (html / "sources" / "text" / "F2.txt").read_bytes()
    raw = next((html / "sources" / "raw").glob("F2*"))
    raw = raw if raw.is_file() else next(raw.rglob("*.html"))
    assert record["held"] == "text"
    assert record["held_sha256"] == hashlib.sha256(text).hexdigest()
    ex = record["extraction"]
    assert ex["tool"] == "fakeextract" and ex["method"] == "markup-strip" and ex["at"]
    assert ex["from_sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest()
    body = _page(html, "F2").body
    assert "pinned on the text derivative (fakeextract, markup-strip)" in body


def test_what_the_extraction_dropped_is_named_as_a_derivative_miss(html):
    """The ZIP column is in the page and not in its extraction."""
    with pytest.raises(SystemExit) as exc:
        passages.pin(html, "F2", "zip", quote="Newark 07102")
    msg = str(exc.value)
    assert "text derivative" in msg and "extraction can drop" in msg
    # the raw capture can still be pinned explicitly, and the pin says which
    record = passages.pin(html, "F2", "zip", quote="07102", held="raw")
    assert record["held"] == "raw" and "extraction" not in record


def test_an_unlogged_derivative_cannot_be_pinned(html):
    (html / "sources" / "text" / "F2.txt").write_text("hand edit\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="matches no row"):
        passages.pin(html, "F2", "x", lines=(1, 1))


def test_a_re_extraction_drifts_the_pin_and_relocate_reanchors_the_same_words(
    html, tmp_path, monkeypatch
):
    passages.pin(html, "F2", "camden", quote="Camden Family Clinic")
    _set_extractor(tmp_path, monkeypatch, "Header line\n" + EXTRACTED)
    invoke(["extract", "F2", "--method", "markup-strip"])
    page = _page(html, "F2")
    reading = passages.read_record(html, page, passages.records(page.fm)[0])
    assert reading.state == "drifted"
    codes = {(f.level, f.code) for f in doctor.run_doctor(html)}
    assert ("ERROR", "excerpt-drift") in codes
    with pytest.raises(SystemExit, match="cannot be read.*--relocate"):
        passages.read_pin(html, "F2", "camden")
    with pytest.raises(SystemExit, match="same words"):
        passages.pin(html, "F2", "camden", quote="Newark Health Center", relocate=True)
    moved = passages.pin(html, "F2", "camden", quote="Camden Family Clinic", relocate=True)
    assert moved["lines"] == [4, 4] and moved["relocated"]["by"] == "agent:test"
    assert moved["by"] == "agent:test"  # the original pinner is kept
    out = passages.read_pin(html, "F2", "camden")
    assert out["text"] == "Camden Family Clinic" and out["held_current"] is True
    assert "excerpt-drift" not in {f.code for f in doctor.run_doctor(html)}


def test_a_lost_derivative_is_an_unbacked_pin(html):
    passages.pin(html, "F2", "newark", quote="Newark Health Center")
    (html / "sources" / "text" / "F2.txt").unlink()
    found = [f for f in doctor.run_doctor(html) if f.code == "unbacked-excerpt"]
    assert found and found[0].level == "ERROR" and "text derivative" in found[0].message


def test_a_hand_edited_pin_on_raw_drifts(nb):
    passages.pin(nb, "F1", "relief", quote="tax relief")
    page = _page(nb, "F1")
    page.fm["excerpts"][0]["sha256"] = "0" * 64
    pages.write_page(page.path, page.fm, page.body)
    msgs = [f.message for f in doctor.run_doctor(nb) if f.code == "excerpt-drift"]
    assert msgs and "hand-edited" in msgs[0]


# --- citing a pin ----------------------------------------------------------------


def test_claims_cite_pins_as_witness_or_subject(nb):
    passages.pin(nb, "F1", "relief", quote="tax relief")
    page = claims.add_claim(nb, "The budget sets money aside for tax relief.",
                            [], subjects=["F1§relief"])
    assert page.fm["sources"][0]["excerpts"] == ["relief"]
    assert page.fm["sources"][0]["role"] == "subject"
    assert page.fm["sources"][0]["resource"].endswith("#relief")
    other = claims.add_claim(nb, "Money is set aside.", ["F1"])
    claims.add_claim_sources(nb, other.id, ["F1§relief"])
    with pytest.raises(SystemExit, match="pins no excerpt 'nope'.*flip source passage pin"):
        claims.add_claim_sources(nb, other.id, ["F1§nope"])
    with pytest.raises(SystemExit, match="still cite"):
        passages.unpin(nb, "F1", "relief")


def test_a_dangling_passage_ref_is_named_with_the_right_command(nb):
    claims.add_claim(nb, "x", ["F1§ghost"])
    msgs = [f.message for f in doctor.run_doctor(nb) if f.code == "dangling-excerpt"]
    assert msgs and "flip source passage pin F1" in msgs[0]


def test_unpin_drops_the_pin_and_its_section(nb):
    passages.pin(nb, "F1", "relief", quote="tax relief")
    passages.unpin(nb, "F1", "relief")
    page = _page(nb, "F1")
    assert passages.records(page.fm) == [] and passages.EXCERPTS_HEADING not in page.body
    rows = events.read_events(nb, op="source.")
    assert [r["op"] for r in rows][-2:] == ["source.pin", "source.unpin"]
    assert rows[-2]["label"] == "relief" and rows[-2]["held"] == "raw"


def test_a_hand_written_excerpts_heading_is_not_clobbered(nb):
    page = _page(nb, "F1")
    pages.write_page(page.path, page.fm, page.body + "\n## Excerpts\n\nmy notes\n")
    with pytest.raises(SystemExit, match="hand-written"):
        passages.pin(nb, "F1", "relief", quote="tax relief")


# --- the CLI ---------------------------------------------------------------------


def test_cli_pin_list_read_unpin(nb):
    out = invoke(["source", "passage", "pin", "F1", "--label", "relief",
                  "--quote", "sets aside $5,585,576"]).output
    assert out.splitlines()[0] == "F1§relief"
    assert "pinned on the raw capture" in out and "--about F1§relief" in out
    listed = json.loads(invoke(["source", "passage", "list", "F1", "--json"]).output)
    assert listed[0]["ref"] == "F1§relief" and listed[0]["state"] == "intact"
    assert listed[0]["text"] == "sets aside $5,585,576"
    text = invoke(["source", "passage", "read", "F1§relief"]).output
    assert text.strip() == "sets aside $5,585,576"
    data = json.loads(invoke(["source", "passage", "read", "F1", "relief", "--json"]).output)
    assert set(data) == {"ref", "source", "label", "held", "lines", "span", "sha256",
                         "held_sha256", "held_current", "text"}
    assert data["held_current"] is True
    invoke(["source", "passage", "unpin", "F1", "relief"])
    refused = invoke(["source", "passage", "pin", "F1", "--label", "x", "--quote",
                      "no such words here"], ok=False)
    assert refused.exit_code != 0 and "Nearest miss" in refused.output


def test_snapshot_carries_pins_and_resolved_passage_refs(nb):
    passages.pin(nb, "F1", "relief", quote="tax relief")
    claims.add_claim(nb, "Tax relief is budgeted.", ["F1§relief", "F1§gone"])
    data = snapshot.snapshot(nb)
    pin = data["sources"][0]["passages"][0]
    assert pin["ref"] == "F1§relief" and pin["state"] == "intact"
    assert pin["text"] == "tax relief" and pin["held"] == "raw" and pin["held_current"]
    cites = data["claims"][0]["citations"]
    assert cites[0]["passage"] == {
        "source": "F1", "label": "relief", "pinned": True, "held": "raw",
        "lines": pin["lines"], "span": pin["span"], "sha256": pin["sha256"],
        "state": "intact",
    }
    assert cites[1]["passage"]["pinned"] is False and cites[1]["passage"]["state"] is None


def test_transcript_pins_read_through_the_shared_core(nb, tmp_path):
    talk = tmp_path / "chat.md"
    talk.write_text("a: hello\nb: the figure is 82\nc: bye\n", encoding="utf-8")
    invoke(["session", "start", "s1", "--model", "m"])
    invoke(["session", "transcript", "s1", "--file", str(talk)])
    invoke(["transcript", "excerpt", "T1", "--lines", "2-2", "--label", "figure"])
    record = passages.records(_page(nb, "T1").fm)[0]
    assert set(record) == {"label", "lines", "sha256", "words"}  # 0.26's shape, unchanged
    # the generic reader reads it, as a pin on the raw capture
    out = passages.read_pin(nb, "T1", "figure")
    assert out["held"] == "raw" and out["text"] == "b: the figure is 82"
    # and a quote pin on a transcript works too
    passages.pin(nb, "T1", "bye", quote="c: bye")
    assert util.read_jsonl(nb / "log" / "events.jsonl")[-1]["op"] == "source.pin"
