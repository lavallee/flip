"""A recorded basis on verification, test and status records (SPEC §7, "Basis"),
and the record of who set a claim's current status."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import claims, doctor, events, pages, passages, snapshot, stance, util
from flip.cli import main

RULE = "standard:document@1#2008960"


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
    doc = tmp_path / "doc.txt"
    doc.write_text("The budget sets aside $5,585,576 for tax relief.\n", encoding="utf-8")
    invoke(["add-source", str(doc)])
    passages.pin(root.resolve(), "F1", "relief", quote="sets aside $5,585,576")
    return root.resolve()


def _claim(root: Path, cid: str) -> pages.Page:
    return next(p for p in pages.iter_pages(root, "claims") if p.id == cid)


# --- the grammar -----------------------------------------------------------------


@pytest.mark.parametrize("rule", [
    RULE, "standard:desk-default@v1.2#abcdef0", "rule:x@1#" + "a" * 64,
    "standard:Document_Rule@2026-11#0123456789",
])
def test_basis_rules_on_the_grammar_are_accepted(rule):
    assert claims.BASIS_RULE_RE.match(rule)


@pytest.mark.parametrize("rule", [
    "document@1#2008960", "standard:document#2008960", "standard:document@1",
    "standard:document@1#ABCDEF0", "standard:document@1#abc", "Standard:x@1#abcdef0",
    "standard:x y@1#abcdef0", "standard:x@1#" + "a" * 65,
])
def test_basis_rules_off_the_grammar_are_refused(nb, rule):
    claims.add_claim(nb, "x", ["F1"])
    with pytest.raises(SystemExit, match="invalid --basis"):
        claims.verify_claim(nb, "C1", "adversarial", basis=rule)
    assert "verified" not in _claim(nb, "C1").fm  # refusal writes nothing


def test_basis_against_needs_a_rule_and_a_real_pin(nb):
    claims.add_claim(nb, "x", ["F1"])
    with pytest.raises(SystemExit, match="give the rule"):
        claims.verify_claim(nb, "C1", "adversarial", basis_against=["F1§relief"])
    with pytest.raises(SystemExit, match="pins no passage 'ghost'"):
        claims.verify_claim(nb, "C1", "adversarial", basis=RULE, basis_against=["F1§ghost"])
    # non-passage refs (a derivation, a script) are taken as given
    page = claims.verify_claim(nb, "C1", "recomputation", against=["derived/x.json#C1"],
                               basis=RULE, basis_against=["derived/x.json#C1"])
    assert page.fm["verified"][-1]["basis"] == {"rule": RULE, "against": ["derived/x.json#C1"]}


# --- stored on each record, and in events ---------------------------------------


def test_verify_test_and_status_store_the_basis_and_emit_it(nb, monkeypatch):
    monkeypatch.setenv("FLIP_ACTOR", "tool:desk-standard")
    claims.add_claim(nb, "The budget sets aside $5,585,576.", [], subjects=["F1§relief"])
    claims.record_test(
        nb, "C1", "attribution", error="the figure is not in the document",
        would_detect="the figure would be absent from the pinned passage",
        if_absent="the passage would carry the figure", against=["F1§relief"],
        result="survived", basis=RULE, basis_against=["F1§relief"],
    )
    claims.set_claim_status(nb, "C1", "verified", because="Settled by standard",
                            basis=RULE, basis_against=["F1§relief"])
    fm = _claim(nb, "C1").fm
    assert fm["tests"][-1]["basis"] == {"rule": RULE, "against": ["F1§relief"]}
    assert fm["tests"][-1]["by"] == "tool:desk-standard"
    assert fm["status_set"]["by"] == "tool:desk-standard"
    assert fm["status_set"]["basis"] == {"rule": RULE, "against": ["F1§relief"]}
    assert fm["status_set"]["from"] == "asserted"
    assert fm["status_set"]["because"] == "Settled by standard"
    rows = events.read_events(nb, op="claim.")
    test_row, status_row = rows[-2], rows[-1]
    assert test_row["op"] == "claim.test" and test_row["basis"] == RULE
    assert status_row["actor"] == "tool:desk-standard"
    assert status_row["basis"] == RULE and status_row["basis_against"] == ["F1§relief"]


def test_a_tool_actor_is_valid_attribution(nb, monkeypatch):
    """`tool:<name>` has always been accepted; a tool applying a standard writes
    as itself, so a reader can never take its ruling for a person's."""
    claims.add_claim(nb, "x", ["F1"])
    out = invoke(["--actor", "tool:desk-standard", "claim", "verify", "C1",
                  "--method", "adversarial", "--basis", RULE]).output
    assert "verified via adversarial" in out
    assert _claim(nb, "C1").fm["verified"][-1]["by"] == "tool:desk-standard"
    assert events.read_events(nb)[-1]["actor"] == "tool:desk-standard"


# --- a basis is a label, never a pass --------------------------------------------


def test_a_basis_never_passes_the_verification_bar(nb):
    """A claim citing nothing, or an ungraded source, is refused `verified`
    with a basis exactly as without one: the bar is the bar."""
    claims.add_claim(nb, "bare claim", [])
    with pytest.raises(SystemExit, match="cannot verify C1"):
        claims.set_claim_status(nb, "C1", "verified", basis=RULE)
    claims.add_claim(nb, "ungraded witness", ["F1"])
    with pytest.raises(SystemExit, match="cannot verify C2"):
        claims.set_claim_status(nb, "C2", "verified", basis=RULE,
                                basis_against=["F1§relief"])
    # independent-sources with a basis still does not clear the gate on its own
    claims.verify_claim(nb, "C2", "independent-sources", basis=RULE)
    with pytest.raises(SystemExit, match="cannot verify C2"):
        claims.set_claim_status(nb, "C2", "verified", basis=RULE)
    # a subject-only claim with a BENT attribution test stays refused
    claims.add_claim(nb, "about F1", [], subjects=["F1§relief"])
    claims.record_test(nb, "C3", "attribution", error="not in it", result="survived",
                       basis=RULE)
    assert stance.test_severity(_claim(nb, "C3").fm["tests"][-1]) == "bent"
    with pytest.raises(SystemExit, match="cannot verify C3"):
        claims.set_claim_status(nb, "C3", "verified", basis=RULE)
    for cid in ("C1", "C2", "C3"):
        assert _claim(nb, cid).fm["status"] == "asserted"
        assert "status_set" not in _claim(nb, cid).fm


def test_a_record_with_a_basis_is_exactly_as_reversible(nb):
    invoke(["grade", "F1", "--independence", "independent", "--basis", "measured"])
    claims.add_claim(nb, "x", ["F1"])
    claims.set_claim_status(nb, "C1", "verified", basis=RULE, because="by standard")
    page = claims.set_claim_status(nb, "C1", "asserted", because="Reopened: rule changed")
    assert page.fm["status"] == "asserted"
    assert page.fm["status_set"] == {
        "by": "agent:test", "at": page.fm["status_set"]["at"], "from": "verified",
        "because": "Reopened: rule changed",
    }
    # and a verification with a basis is undone the same way as one without:
    # the record stays (append-only), the status moves
    claims.verify_claim(nb, "C1", "adversarial", basis=RULE)
    claims.set_claim_status(nb, "C1", "verified", basis=RULE)
    claims.set_claim_status(nb, "C1", "needs-2nd")
    assert _claim(nb, "C1").fm["status"] == "needs-2nd"


def test_refreshing_the_same_status_does_not_rewrite_who_ruled(nb):
    invoke(["grade", "F1", "--independence", "independent", "--basis", "measured"])
    claims.add_claim(nb, "x", ["F1"])
    claims.set_claim_status(nb, "C1", "verified", basis=RULE)
    before = _claim(nb, "C1").path.read_text(encoding="utf-8")
    claims.set_claim_status(nb, "C1", "verified")
    assert _claim(nb, "C1").path.read_text(encoding="utf-8") == before


# --- the snapshot says who set the status ----------------------------------------


def test_snapshot_status_set_from_page_events_or_creation(nb):
    invoke(["grade", "F1", "--independence", "independent", "--basis", "measured"])
    claims.add_claim(nb, "created only", ["F1"])
    claims.add_claim(nb, "ruled", ["F1"])
    invoke(["--actor", "human:jane", "claim", "status", "C2", "verified",
            "--because", "read it", "--basis", RULE, "--basis-against", "F1§relief"])
    util.set_cli_overrides(None, None)  # --actor is process-global; end it here
    claims.add_claim(nb, "ledger only", ["F1"])
    claims.set_claim_status(nb, "C3", "needs-2nd")
    # simulate a page whose status was set before the page kept the record
    page = _claim(nb, "C3")
    page.fm.pop("status_set")
    pages.write_page(page.path, page.fm, page.body)
    claims.add_claim(nb, "unattributable", ["F1"])
    page = _claim(nb, "C4")
    page.fm["status"] = "unconfirmed"
    pages.write_page(page.path, page.fm, page.body)

    data = {c["id"]: c for c in snapshot.snapshot(nb)["claims"]}
    assert data["C1"]["status_set"] == {
        "by": "agent:test", "at": data["C1"]["at"], "from": None, "to": "asserted",
        "because": None, "basis": None, "recorded": "created"}
    c2 = data["C2"]["status_set"]
    assert c2["by"] == "human:jane" and c2["recorded"] == "page" and c2["to"] == "verified"
    assert c2["basis"] == {"rule": RULE, "against": ["F1§relief"]} and c2["because"] == "read it"
    c3 = data["C3"]["status_set"]
    assert c3["recorded"] == "events" and c3["by"] == "agent:test" and c3["from"] == "asserted"
    assert data["C4"]["status_set"] is None


def test_doctor_names_a_hand_edited_basis(nb):
    claims.add_claim(nb, "x", ["F1"])
    claims.verify_claim(nb, "C1", "adversarial", basis=RULE)
    page = _claim(nb, "C1")
    page.fm["verified"][0]["basis"] = "standard:document"
    pages.write_page(page.path, page.fm, page.body)
    found = [f for f in doctor.run_doctor(nb) if f.code == "bad-basis"]
    assert found and found[0].level == "WARN"


def test_cli_status_prints_the_basis(nb):
    invoke(["grade", "F1", "--independence", "independent", "--basis", "measured"])
    claims.add_claim(nb, "x", ["F1"])
    out = invoke(["claim", "status", "C1", "verified", "--basis", RULE]).output
    assert f"basis {RULE}" in out
    snap = json.loads(invoke(["snapshot"]).output)
    assert snap["claims"][0]["status_set"]["basis"] == {"rule": RULE}
