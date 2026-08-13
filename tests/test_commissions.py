"""Tests for flip.commissions — contract pages: universe/stop/does-not-redo."""

from __future__ import annotations

from pathlib import Path

import pytest

from flip import commissions, ledgers, pages, util

MANIFEST_MD = """\
---
okf_version: "0.2"
flip: "0.8"
slug: t
kind: scout
status: active
created: 2020-01-01
updated: 2020-01-01
visibility: internal
renders_public: false
source_trail_public: false
citation_rule: public-terminus
---
# t
"""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    (tmp_path / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    return tmp_path.resolve()


def add(root: Path, **over) -> pages.Page:
    kw = dict(
        deliverable="refresh the tracker rows against the 2026 snapshot",
        universe="the 180 active rows as of the R1 baseline",
        stop="every row re-checked once or marked unobtainable",
        does_not_redo="no re-discovery of rows already lineage-audited",
    )
    kw.update(over)
    return commissions.add_commission(root, **kw)


# --- add ----------------------------------------------------------------------


def test_add_commission_shape(root: Path):
    page = add(root, for_ref=None, roi_low="+0.5 completeness", roi_high="+1.0")
    fm = page.fm
    assert fm["type"] == "Commission"
    assert fm["id"] == "K1"
    assert fm["aliases"] == ["K1"]
    assert fm["status"] == "proposed"
    assert fm["universe"].startswith("the 180 active rows")
    assert fm["stop"].startswith("every row re-checked")
    assert fm["does_not_redo"].startswith("no re-discovery")
    assert fm["roi_low"] == "+0.5 completeness"
    assert fm["roi_high"] == "+1.0"
    assert page.path.parent.name == "commissions"
    assert add(root).id == "K2"  # ids advance


def test_add_commission_requires_all_contract_fields(root: Path):
    for missing in ("universe", "stop", "does_not_redo"):
        with pytest.raises(SystemExit, match="a commission without one is a wish"):
            add(root, **{missing: "  "})


def test_add_commission_roi_high_requires_low(root: Path):
    with pytest.raises(SystemExit, match="low bound is the expectation"):
        add(root, roi_high="+1.0")


def test_add_commission_for_ref_must_resolve(root: Path):
    with pytest.raises(SystemExit, match="unknown ref 'Q9'"):
        add(root, for_ref="Q9")
    ledgers.add_question(root, "which rows changed?")
    assert add(root, for_ref="Q1").fm["for"] == "Q1"


def test_add_commission_logs_event(root: Path):
    add(root)
    events = util.read_jsonl(root / "log" / "log.jsonl")
    assert any(e["text"].startswith("commission-add K1:") for e in events)


# --- lifecycle ----------------------------------------------------------------


def test_status_walks_the_lifecycle(root: Path):
    add(root)
    commissions.set_commission_status(root, "K1", "dispatched")
    page = commissions.set_commission_status(
        root, "K1", "returned",
        consumed="R1 baseline rows; no re-discovery",
        note="161/161 in-universe",
    )
    assert page.fm["status"] == "returned"
    assert page.fm["consumed"] == "R1 baseline rows; no re-discovery"
    body = pages.read_page(page.path).body
    assert "## Dispatched" in body
    assert "## Returned" in body and "Consumed: R1 baseline rows" in body
    assert "161/161 in-universe" in body


def test_status_refuses_illegal_jumps_and_terminal_exits(root: Path):
    add(root)
    with pytest.raises(SystemExit, match="legal moves: dispatched, declined"):
        commissions.set_commission_status(root, "K1", "returned")
    commissions.set_commission_status(root, "K1", "declined")
    with pytest.raises(SystemExit, match="terminal; open a new commission"):
        commissions.set_commission_status(root, "K1", "dispatched")


def test_status_same_state_and_unknown_id_raise(root: Path):
    add(root)
    with pytest.raises(SystemExit, match="already proposed"):
        commissions.set_commission_status(root, "K1", "proposed")
    with pytest.raises(SystemExit, match="no commission 'K9'.*known: K1"):
        commissions.set_commission_status(root, "K9", "dispatched")


def test_consumed_outside_return_refused(root: Path):
    add(root)
    with pytest.raises(SystemExit, match="--consumed belongs to a return"):
        commissions.set_commission_status(root, "K1", "dispatched", consumed="x")


def test_status_logs_event(root: Path):
    add(root)
    commissions.set_commission_status(root, "K1", "dispatched")
    events = util.read_jsonl(root / "log" / "log.jsonl")
    assert any(e["text"].startswith('commission-status K1: "dispatched"')
               for e in events)


# --- list ---------------------------------------------------------------------


def test_list_commissions_rows_and_filter(root: Path):
    add(root)
    add(root, deliverable="a second run", for_ref=None)
    commissions.set_commission_status(root, "K2", "declined")
    rows = commissions.list_commissions(root)
    assert [r["id"] for r in rows] == ["K1", "K2"]
    assert rows[0]["status"] == "proposed"
    assert rows[1]["status"] == "declined"
    assert [r["id"] for r in commissions.list_commissions(root, status="declined")] \
        == ["K2"]
    with pytest.raises(SystemExit, match="invalid status 'done'"):
        commissions.list_commissions(root, status="done")


def test_list_commissions_empty(root: Path):
    assert commissions.list_commissions(root) == []


def test_commission_id_never_reused_after_deletion(root: Path):
    p = add(root)
    p.path.unlink()
    assert add(root).id == "K2"


def test_commission_resolves_by_id(root: Path):
    p = add(root)
    assert pages.find_by_id(root, "K1").path == p.path
