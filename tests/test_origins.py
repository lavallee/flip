"""Where a derivative source's content comes from (SPEC §5.4, "Origin"), and how
corroboration counts origins rather than pages."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import claims, doctor, events, origins, pages, snapshot
from flip.cli import main


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
    """F1-F4, all graded independent: F1 and F2 hold the same bytes (one wire
    story captured twice), F3 and F4 are different documents."""
    root = tmp_path / "demo"
    invoke(["new", "demo", "--kind", "ledger", "--dest", str(root)])
    monkeypatch.chdir(root)
    for name, text in (("wire-a.txt", "AP: chargers fail 1 in 5 times.\n"),
                       ("wire-b.txt", "AP: chargers fail 1 in 5 times.\n"),
                       ("study.txt", "A 2023 study found 1 in 5 sessions fail.\n"),
                       ("report.txt", "The lab measured failures directly.\n")):
        doc = tmp_path / name
        doc.write_text(text, encoding="utf-8")
        invoke(["add-source", str(doc)])
    for sid in ("F1", "F2", "F3", "F4"):
        invoke(["grade", sid, "--independence", "independent", "--basis", "measured"])
    return root.resolve()


def _fms(root: Path) -> list[dict]:
    return [p.fm for p in pages.iter_pages(root, "references")]


def _src(root: Path, sid: str) -> pages.Page:
    return next(p for p in pages.iter_pages(root, "references") if p.id == sid)


# --- the record --------------------------------------------------------------------


def test_origin_is_recorded_with_a_reason_and_an_actor(nb):
    page = origins.set_origin(nb, "F2", republishes="F1", because="same AP copy")
    assert page.fm["origin"] == {"republishes": "F1", "because": "same AP copy",
                                 "by": "agent:test", "at": page.fm["origin"]["at"]}
    row = events.read_events(nb)[-1]
    assert row["op"] == "source.origin" and row["republishes"] == "F1"
    assert row["because"] == "same AP copy"
    # an external origin the notebook does not hold
    page = origins.set_origin(nb, "F3", ref="https://example.org/2023-study",
                              because="quotes the 2023 study's figure")
    assert page.fm["origin"]["ref"] == "https://example.org/2023-study"
    assert page.fm["grade"] == "A"  # an origin never moves the letter


def test_origin_validation(nb):
    with pytest.raises(SystemExit, match="needs --because"):
        origins.set_origin(nb, "F2", republishes="F1")
    with pytest.raises(SystemExit, match="cannot republish itself"):
        origins.set_origin(nb, "F2", republishes="F2", because="x")
    with pytest.raises(SystemExit, match="unknown source id 'F9'"):
        origins.set_origin(nb, "F2", republishes="F9", because="x")
    with pytest.raises(SystemExit, match="looks like a source id"):
        origins.set_origin(nb, "F2", ref="F1", because="x")
    with pytest.raises(SystemExit, match="name the origin"):
        origins.set_origin(nb, "F2", because="x")
    origins.set_origin(nb, "F2", republishes="F1", because="x")
    origins.set_origin(nb, "F3", republishes="F2", because="x")
    with pytest.raises(SystemExit, match="close a cycle"):
        origins.set_origin(nb, "F1", republishes="F3", because="x")
    with pytest.raises(SystemExit, match="records no origin"):
        origins.set_origin(nb, "F4", clear=True, because="x")
    page = origins.set_origin(nb, "F3", clear=True, because="it was a separate study")
    assert "origin" not in page.fm
    assert events.read_events(nb)[-1]["cleared"] is True


# --- the count ---------------------------------------------------------------------


def test_sources_sharing_an_origin_count_once(nb):
    claims.add_claim(nb, "Chargers fail one time in five.", ["F1", "F2", "F3"])
    assert claims.corroboration_count(_fms(nb), ["F1", "F2", "F3"]) == 3  # no origins yet
    origins.set_origin(nb, "F2", republishes="F1", because="same AP copy")
    detail = claims.corroboration_detail(_fms(nb), ["F1", "F2", "F3"])
    assert detail["count"] == 2
    assert detail["counted"] == ["F1", "F2", "F3"]
    assert detail["collapsed"] == [{"origin": "F1", "sources": ["F1", "F2"],
                                    "why": ["F2 republishes F1 (same AP copy)"]}]


def test_an_origin_chain_through_an_uncited_source_still_collapses(nb):
    origins.set_origin(nb, "F2", republishes="F1", because="copy")
    origins.set_origin(nb, "F3", republishes="F2", because="copy of the copy")
    assert claims.corroboration_count(_fms(nb), ["F2", "F3"]) == 1
    assert claims.corroboration_count(_fms(nb), ["F3", "F4"]) == 2


def test_two_sources_naming_one_external_origin_count_once(nb):
    origins.set_origin(nb, "F1", ref="https://www.example.org/wire/123?utm_source=x",
                       because="AP story")
    origins.set_origin(nb, "F2", ref="https://example.org/wire/123/", because="AP story")
    assert claims.corroboration_count(_fms(nb), ["F1", "F2", "F4"]) == 2


def test_an_external_ref_resolves_to_the_held_source_at_that_address(nb):
    page = _src(nb, "F1")
    page.fm["resource"] = "https://example.org/wire/123"
    pages.write_page(page.path, page.fm, page.body)
    origins.set_origin(nb, "F3", ref="https://example.org/wire/123", because="quotes it")
    detail = claims.corroboration_detail(_fms(nb), ["F1", "F3"])
    assert detail["count"] == 1
    assert detail["collapsed"][0]["why"] == [
        "F3 comes from https://example.org/wire/123, which F1 holds (quotes it)"]


def test_the_verified_gate_counts_origins_and_says_which_collapsed(nb):
    """ledger needs two independent sources (grade A does not suffice there by
    itself once the letter is below A): two copies of one story are one."""
    for sid in ("F1", "F2"):
        invoke(["grade", sid, "--basis", "survey", "--method", "wire copy"])  # grade B
    claims.add_claim(nb, "Chargers fail one time in five.", ["F1", "F2"])
    assert claims.set_claim_status(nb, "C1", "needs-2nd")  # 2 origins: the bar is met
    claims.add_claim(nb, "Chargers fail one time in five, again.", ["F1", "F2"])
    origins.set_origin(nb, "F2", republishes="F1", because="same AP copy")
    with pytest.raises(SystemExit, match=r"1 independent source\(s\) of 2 required.*"
                                         r"F1, F2 count as one origin"):
        claims.set_claim_status(nb, "C2", "verified")


def test_status_output_and_snapshot_name_the_collapse(nb):
    claims.add_claim(nb, "Chargers fail one time in five.", ["F1", "F2", "F3"])
    invoke(["source", "origin", "F2", "--republishes", "F1", "--because", "same AP copy"])
    out = invoke(["claim", "status", "C1", "needs-2nd"]).output
    assert "corroboration: 2" in out
    assert "F1, F2 count as one origin (F1) — F2 republishes F1 (same AP copy)" in out
    data = snapshot.snapshot(nb)
    by_id = {s["id"]: s for s in data["sources"]}
    assert by_id["F2"]["origin"]["republishes"] == "F1"
    assert by_id["F2"]["origin_key"] == "F1" and by_id["F4"]["origin_key"] == "F4"
    assert by_id["F4"]["origin"] is None
    claim = data["claims"][0]
    assert claim["corroboration"] == 2
    assert claim["corroboration_collapsed"][0]["sources"] == ["F1", "F2"]


def test_grade_explain_says_what_a_source_shares_an_origin_with(nb):
    invoke(["source", "origin", "F2", "--republishes", "F1", "--because", "same AP copy"])
    out = invoke(["grade", "F2", "--explain"]).output
    assert "F2 republishes F1 (same AP copy)" in out
    assert "counts as one origin (F1) with: F1" in out
    assert "origin" not in invoke(["grade", "F4", "--explain"]).output


# --- doctor --------------------------------------------------------------------------


def test_doctor_hints_at_identical_bytes_with_no_origin(nb):
    claims.add_claim(nb, "Chargers fail one time in five.", ["F1", "F2", "F3"])
    found = [f for f in doctor.run_doctor(nb) if f.code == "possible-shared-origin"]
    assert len(found) == 1 and found[0].level == "WARN"
    assert "F1 and F2" in found[0].message and "identical bytes" in found[0].message
    invoke(["source", "origin", "F2", "--republishes", "F1", "--because", "same copy"])
    assert "possible-shared-origin" not in {f.code for f in doctor.run_doctor(nb)}


def test_doctor_hints_at_one_canonical_address_with_no_origin(nb):
    for sid, url in (("F3", "https://www.example.org/a/?utm_medium=x"),
                     ("F4", "https://example.org/a#top")):
        page = _src(nb, sid)
        page.fm["resource"] = url
        pages.write_page(page.path, page.fm, page.body)
    claims.add_claim(nb, "x", ["F3", "F4"])
    msgs = [f.message for f in doctor.run_doctor(nb) if f.code == "possible-shared-origin"]
    assert msgs and "share the address https://example.org/a" in msgs[0]


def test_doctor_names_a_hand_broken_origin(nb):
    page = _src(nb, "F2")
    page.fm["origin"] = {"republishes": "F9", "because": "x"}
    pages.write_page(page.path, page.fm, page.body)
    found = [f for f in doctor.run_doctor(nb) if f.code == "bad-origin"]
    assert found and "F9" in found[0].message


def test_doctor_reports_drift_after_an_origin_until_the_status_refreshes(nb):
    claims.add_claim(nb, "x", ["F1", "F2"])
    invoke(["source", "origin", "F2", "--republishes", "F1", "--because", "copy"])
    assert "corroboration-drift" in {f.code for f in doctor.run_doctor(nb)}
    invoke(["claim", "status", "C1", "asserted"])
    assert "corroboration-drift" not in {f.code for f in doctor.run_doctor(nb)}


def test_cli_origin_json_free_paths(nb):
    out = invoke(["source", "origin", "F3", "--ref", "doi:10.1000/x", "--because",
                  "cites its figure"]).output
    assert out.startswith("F3 · ref doi:10.1000/x")
    data = json.loads(invoke(["snapshot"]).output)
    assert next(s for s in data["sources"] if s["id"] == "F3")["origin_key"] == "doi:10.1000/x"
