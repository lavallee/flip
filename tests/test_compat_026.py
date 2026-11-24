"""A notebook written by flip 0.26 reads, checks and round-trips unchanged.

`tests/fixtures/notebook-0.26/` was written by the 0.26.0 CLI (sources graded,
a transcript excerpt, a claim verified by a person, an attribution test), with
the capture URLs neutralised. Nothing in it records a pin on a non-transcript
source, a basis, a status record or an origin: everything this version adds
must read as absent there, and no derived number may move.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import doctor, passages, snapshot
from flip.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "notebook-0.26"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")


@pytest.fixture
def old(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "tides"
    shutil.copytree(FIXTURE, root)
    monkeypatch.chdir(root)
    return root.resolve()


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".flip" not in p.parts
    }


def invoke(args: list[str]):
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    return result


def test_reads_change_nothing_on_disk(old):
    before = _tree(old)
    snapshot.snapshot(old)
    doctor.run_doctor(old)
    invoke(["transcript", "read", "T1", "high"])
    invoke(["source", "passage", "read", "T1§high", "--json"])
    invoke(["source", "passage", "list", "T1"])
    invoke(["grade", "F1", "--explain"])
    assert _tree(old) == before


def test_doctor_adds_only_the_shared_origin_hint(old):
    found = {(f.level, f.code) for f in doctor.run_doctor(old)}
    assert not [f for f in found if f[0] == "ERROR"]
    # 0.26 already named the identical bytes notebook-wide; the hint is the
    # same fact said where it matters, on the claim whose count it inflates.
    assert {code for _, code in found} <= {"duplicate-custody", "possible-shared-origin"}


def test_snapshot_reads_old_records_as_absent_and_keeps_every_number(old):
    data = snapshot.snapshot(old)
    claims = {c["id"]: c for c in data["claims"]}
    assert claims["C1"]["corroboration"] == 3  # the stored 0.26 number, unchanged
    assert claims["C1"]["corroboration_collapsed"] == []
    assert all(s["origin"] is None for s in data["sources"])
    assert all(s["origin_key"] == s["id"] for s in data["sources"])
    # who ruled: the page has no record, the 0.26 event ledger does
    assert claims["C1"]["status_set"]["by"] == "human:jane"
    assert claims["C1"]["status_set"]["recorded"] == "events"
    assert claims["C1"]["status_set"]["because"] == "two gauges"
    assert claims["C2"]["status_set"]["recorded"] == "created"
    assert claims["C1"]["verified"][0].get("basis") is None
    t1 = next(s for s in data["sources"] if s["id"] == "T1")
    assert [p["ref"] for p in t1["passages"]] == ["T1§high"]
    assert t1["passages"][0]["state"] == "intact" and t1["passages"][0]["held"] == "raw"
    assert claims["C2"]["citations"][0]["passage"]["state"] == "intact"


def test_a_refresh_and_a_new_excerpt_round_trip(old):
    claim = old / "claims" / "spring-high-water-reaches-4-2-m.md"
    before = claim.read_bytes()
    invoke(["claim", "status", "C1", "verified"])  # a refresh, not a ruling
    assert claim.read_bytes() == before
    page = old / "references" / "chat.md"
    section = page.read_text(encoding="utf-8").split(passages.EXCERPTS_HEADING, 1)[1]
    invoke(["transcript", "excerpt", "T1", "--lines", "3-3", "--label", "thanks"])
    after = page.read_text(encoding="utf-8")
    # the old pin's rendering is untouched; the new one follows it
    assert after.split(passages.EXCERPTS_HEADING, 1)[1].startswith(section.rstrip("\n"))
