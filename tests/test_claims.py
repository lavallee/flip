"""Tests for flip.claims — the claim ledger and the verification bar."""

from __future__ import annotations

from pathlib import Path

import pytest

from flip import claims, util
from flip.manifest import load_manifest

MANIFEST = """\
slug = "t"
kind = "scout"
status = "active"
created = "2020-01-01"
updated = "2020-01-01"
"""

LEDGER_ROWS = [
    {"id": "A1", "kind": "article", "title": "orig B", "local": "sources/raw/A1.html",
     "grade": "B", "independence": "original", "freshness": "fresh", "status": "captured",
     "supports": []},
    {"id": "A2", "kind": "article", "title": "repub A", "local": "sources/raw/A2.html",
     "grade": "A", "independence": "republisher", "freshness": "fresh", "status": "captured",
     "supports": []},
    {"id": "A3", "kind": "article", "title": "orig C", "local": "sources/raw/A3.html",
     "grade": "C", "independence": "original", "freshness": "fresh", "status": "captured",
     "supports": []},
    # captured but never judged: capture-time defaults (original/fresh) are
    # inert while grade is "?" — this row must corroborate nothing (SPEC §7.2)
    {"id": "A4", "kind": "article", "title": "unjudged", "local": "sources/raw/A4.html",
     "grade": "?", "independence": "original", "freshness": "fresh", "status": "captured",
     "supports": []},
]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    (tmp_path / "notebook.toml").write_text(MANIFEST, encoding="utf-8")
    return tmp_path


@pytest.fixture
def sourced(root: Path) -> Path:
    util.write_jsonl(root / "sources" / "ledger.jsonl", LEDGER_ROWS)
    return root


# --- add_claim ---------------------------------------------------------------


def test_add_claim_shape_and_corroboration(sourced: Path):
    row = claims.add_claim(sourced, "the sky is blue", ["A1", "A2"], load_bearing=True)
    assert row["id"] == "C1"
    assert row["status"] == "asserted"
    assert row["load_bearing"] is True
    assert row["sources"] == ["A1", "A2"]
    assert row["independent_corroboration"] == 1  # only A1 is independence=original
    assert row["first_asserted"] == util.today()
    assert row["actor"] == "agent:test"
    assert "notes" not in row
    assert util.read_jsonl(sourced / "analysis" / "claims.jsonl") == [row]


def test_add_claim_notes_and_touch(sourced: Path):
    row = claims.add_claim(sourced, "x", [], notes="single vendor study")
    assert row["notes"] == "single vendor study"
    assert row["independent_corroboration"] == 0
    assert load_manifest(sourced).updated == util.today()


def test_add_claim_missing_ledger_gives_zero(root: Path):
    row = claims.add_claim(root, "x", ["A1", "A2"])
    assert row["independent_corroboration"] == 0


def test_add_claim_unknown_and_duplicate_sources(sourced: Path):
    row = claims.add_claim(sourced, "x", ["A1", "A1", "ZZ9"])
    assert row["independent_corroboration"] == 1  # deduped, unknown id ignored


def test_add_claim_empty_text_raises(sourced: Path):
    with pytest.raises(SystemExit, match="empty claim text"):
        claims.add_claim(sourced, "  ", ["A1"])


def test_claim_ids_never_reused(sourced: Path):
    claims.add_claim(sourced, "one", [])
    claims.add_claim(sourced, "two", [])
    claims.set_claim_status(sourced, "C2", "retracted")
    assert claims.add_claim(sourced, "three", [])["id"] == "C3"


# --- set_claim_status --------------------------------------------------------


def test_set_status_invalid_raises(sourced: Path):
    claims.add_claim(sourced, "x", [])
    with pytest.raises(SystemExit, match="invalid claim status 'bogus'"):
        claims.set_claim_status(sourced, "C1", "bogus")


def test_set_status_unknown_claim_raises(sourced: Path):
    claims.add_claim(sourced, "x", [])
    with pytest.raises(SystemExit, match=r"no claim 'C9'.*known: C1"):
        claims.set_claim_status(sourced, "C9", "needs-2nd")


def test_set_status_recomputes_corroboration(root: Path):
    row = claims.add_claim(root, "x", ["A1"])  # no ledger yet
    assert row["independent_corroboration"] == 0
    util.write_jsonl(root / "sources" / "ledger.jsonl", LEDGER_ROWS)
    updated = claims.set_claim_status(root, "C1", "needs-2nd")
    assert updated["independent_corroboration"] == 1
    assert updated["status"] == "needs-2nd"
    on_disk = util.read_jsonl(root / "analysis" / "claims.jsonl")
    assert on_disk[0]["independent_corroboration"] == 1


def test_verify_meets_min_independent(sourced: Path):
    # scout profile: claim_min_independent = 1; A1 is original
    claims.add_claim(sourced, "x", ["A1"])
    assert claims.set_claim_status(sourced, "C1", "verified")["status"] == "verified"


def test_verify_grade_a_suffices(sourced: Path):
    # A2 is a republisher (0 original) but grade A, and scout allows grade-A shortcuts
    claims.add_claim(sourced, "x", ["A2"])
    row = claims.set_claim_status(sourced, "C1", "verified")
    assert row["status"] == "verified"
    assert row["independent_corroboration"] == 0


def test_verify_below_bar_raises_actionable(sourced: Path):
    # strict local profile: 2 independent required, grade A does not suffice
    strict = sourced / ".flip" / "profiles" / "strict.toml"
    strict.parent.mkdir(parents=True)
    strict.write_text(
        'id = "strict"\nclaim_min_independent = 2\nclaim_grade_a_suffices = false\n',
        encoding="utf-8",
    )
    manifest_text = (sourced / "notebook.toml").read_text(encoding="utf-8")
    (sourced / "notebook.toml").write_text(
        manifest_text.replace('kind = "scout"', 'kind = "strict"'), encoding="utf-8"
    )
    claims.add_claim(sourced, "x", ["A1", "A2"])  # 1 original, grade A present but moot
    with pytest.raises(SystemExit, match=r"cannot verify C1: 1 independent.*of 2 required"):
        claims.set_claim_status(sourced, "C1", "verified")
    # status unchanged on disk
    assert util.read_jsonl(sourced / "analysis" / "claims.jsonl")[0]["status"] == "asserted"


def test_verify_no_sources_message_names_gap(sourced: Path):
    claims.add_claim(sourced, "x", [])
    with pytest.raises(SystemExit, match=r"sources: none.*grade A"):
        claims.set_claim_status(sourced, "C1", "verified")


# --- ungraded sources never corroborate (SPEC §7.2) ---------------------------


def test_corroboration_count_ignores_ungraded_and_dedupes():
    rows = LEDGER_ROWS
    assert claims.corroboration_count(rows, ["A4"]) == 0  # grade "?" is inert
    assert claims.corroboration_count(rows, ["A1", "A4"]) == 1
    assert claims.corroboration_count(rows, ["A1", "A1", "A1"]) == 1  # deduped
    assert claims.corroboration_count(rows, ["A2"]) == 0  # judged but republisher
    assert claims.corroboration_count(rows, ["A1", "A3", "ZZ9"]) == 2


def test_add_claim_ungraded_source_counts_zero(sourced: Path):
    row = claims.add_claim(sourced, "x", ["A4"])
    assert row["independent_corroboration"] == 0


def test_verify_refused_when_only_source_is_ungraded(sourced: Path):
    # scout needs 1 independent original; A4's capture-time defaults say
    # original/fresh but it was never judged — the bar must not see it.
    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    with pytest.raises(SystemExit) as ei:
        claims.set_claim_status(sourced, "C1", "verified")
    msg = str(ei.value)
    assert "cannot verify C1: 0 independent original source(s)" in msg
    assert "A4" in msg and "flip grade" in msg  # names the unjudged source
    assert util.read_jsonl(sourced / "analysis" / "claims.jsonl")[0]["status"] == "asserted"


def test_grading_the_source_then_allows_verification(sourced: Path):
    from flip import sources as sources_mod

    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    with pytest.raises(SystemExit):
        claims.set_claim_status(sourced, "C1", "verified")
    sources_mod.grade_source(sourced, "A4", grade="B", independence="original")
    row = claims.set_claim_status(sourced, "C1", "verified")
    assert row["status"] == "verified"
    assert row["independent_corroboration"] == 1


# --- list_claims -------------------------------------------------------------


def test_list_claims_all_and_filtered(sourced: Path):
    claims.add_claim(sourced, "one", ["A1"])
    claims.add_claim(sourced, "two", [])
    claims.set_claim_status(sourced, "C1", "verified")
    assert [c["id"] for c in claims.list_claims(sourced)] == ["C1", "C2"]
    assert [c["id"] for c in claims.list_claims(sourced, status="verified")] == ["C1"]
    assert claims.list_claims(sourced, status="retracted") == []


def test_list_claims_invalid_status_raises(sourced: Path):
    with pytest.raises(SystemExit, match="invalid claim status"):
        claims.list_claims(sourced, status="nope")


def test_list_claims_empty_notebook(root: Path):
    assert claims.list_claims(root) == []


# --- mutators validate the notebook before writing ----------------------------


def test_add_claim_outside_notebook_writes_nothing(tmp_path: Path):
    outside = tmp_path / "not-a-notebook"
    outside.mkdir()
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        claims.add_claim(outside, "x", [])
    assert not (outside / "analysis").exists()


def test_set_claim_status_outside_notebook_raises(tmp_path: Path):
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        claims.set_claim_status(tmp_path, "C1", "retracted")
