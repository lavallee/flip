"""Tests for flip.forecast — the Forecast/Cluster classes (SPEC §7).

Every refusal on the write paths, append-only updates, resolution's RS row
and void semantics, the decline fold, due windowing, calibration (incl. the
Brier volume gate), cluster class purity, doctor's two-object gate in both
directions plus the forecast/cluster checks, FC/CL id allocation alongside
existing prefixes, the forward-set built-in kind, the flip-render/2
forecasts array, the CLI surface, and an as-is fixture carrying the pilot's
full field set (invented subject) that must validate ERROR-free.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import claims, forecast, kinds, pages, scaffold, util
from flip.cli import main
from flip.doctor import run_doctor
from flip.export import export_json
from flip.manifest import load_manifest, save_manifest
from flip.util import read_jsonl


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep every test away from the real ~/.flip and the host's git identity."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def make_notebook(tmp_path: Path, kind: str = "scout", slug: str = "demo") -> Path:
    return scaffold.create_notebook(tmp_path / slug, slug, kind)


def day(offset: int) -> str:
    """An ISO date `offset` days from today (UTC) — due/overdue fixtures."""
    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


QUESTION = "Will the north bridge close for repairs before 2028?"


def add_fc(root: Path, question: str = QUESTION, **kw) -> pages.Page:
    args = {
        "resolves_by": "2199-03-31",
        "resolves_via": ["town-meeting-minutes"],
        "annul_if": "The bridge is demolished before any repair vote",
        "probability": 0.3,
        "confidence": 0.55,
    }
    args.update(kw)
    return forecast.add_forecast(
        root,
        question,
        args.pop("resolves_by"),
        args.pop("resolves_via"),
        args.pop("annul_if"),
        args.pop("probability"),
        args.pop("confidence"),
        **args,
    )


# ---------------------------------------------------------------- add_forecast


def test_add_forecast_writes_page_with_core_fields(tmp_path):
    root = make_notebook(tmp_path)
    page = add_fc(root)
    assert page.path.parent == root / "forecasts"
    fm = page.fm
    assert fm["type"] == "Forecast"
    assert fm["id"] == "FC1"
    assert fm["aliases"] == ["FC1"]
    assert fm["question"] == QUESTION
    assert fm["description"] == QUESTION
    assert fm["resolves_by"] == "2199-03-31"
    assert fm["resolves_via"] == ["town-meeting-minutes"]
    assert fm["probability"] == 0.3 and isinstance(fm["probability"], float)
    assert fm["confidence"] == 0.55 and isinstance(fm["confidence"], float)
    assert fm["annul_if"].startswith("The bridge is demolished")
    assert fm["status"] == "open"
    assert fm["updates"] == []
    assert fm["opened"] == util.today() and fm["freeze"] == util.today()
    assert fm["generated"]["by"] == "human:test"


def test_add_forecast_optional_fields_land_when_given(tmp_path):
    root = make_notebook(tmp_path)
    page = add_fc(
        root,
        resolution_criteria="Resolves YES on the council's published vote record.",
        resolution_source_ladder=["council vote record", "the town clerk's minutes"],
        resolver="desk, on the literal published record",
        base_rate="0/3 prior years saw a closure vote",
        predictability="gray-light",
        bears_on=["claim:the-span-is-past-rating", "question:Q1"],
        generated_by="mill/maintenance-cliff",
        horizon=2028,
    )
    fm = page.fm
    assert fm["resolution_source_ladder"] == [
        "council vote record", "the town clerk's minutes",
    ]
    assert fm["base_rate"] == "0/3 prior years saw a closure vote"
    assert fm["predictability"] == "gray-light"
    assert fm["bears_on"] == ["claim:the-span-is-past-rating", "question:Q1"]
    assert fm["generated_by"] == "mill/maintenance-cliff"
    assert fm["horizon"] == 2028
    assert fm["resolver"].startswith("desk")


def test_add_forecast_refuses_undated(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, resolves_by=None)
    assert "no undated forecasts" in str(exc.value)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, resolves_by="soonish")
    assert "not a date" in str(exc.value)


def test_add_forecast_refuses_missing_annul_if(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, annul_if=None)
    assert "annul_if" in str(exc.value) and "mandatory" in str(exc.value)


@pytest.mark.parametrize("bad", ["1.5", -0.1, "high", None])
def test_add_forecast_refuses_bad_probability(tmp_path, bad):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, probability=bad)
    assert "probability" in str(exc.value)


def test_add_forecast_refuses_bad_confidence(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, confidence=2)
    assert "confidence" in str(exc.value) and "[0, 1]" in str(exc.value)


def test_add_forecast_refuses_untyped_bears_on(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, bears_on=["C1"])
    assert "typed ref" in str(exc.value)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, bears_on=["source:A3"])
    assert "typed ref" in str(exc.value)


def test_add_forecast_refuses_bad_predictability(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as exc:
        add_fc(root, predictability="opaque")
    assert "predictability" in str(exc.value)


def test_fc_ids_allocate_alongside_existing_prefixes(tmp_path):
    """FC# never collides with F# (file sources) or C#; deletion never frees."""
    root = make_notebook(tmp_path)
    # A file-source id F1 on disk must not perturb FC allocation.
    pages.write_page(
        root / "references" / "old-file.md",
        {"type": "Source", "id": "F1", "aliases": ["F1"], "grade": "?"},
        "a captured file\n",
    )
    claims.add_claim(root, "The span is past its load rating", [])
    first = add_fc(root)
    second = add_fc(root, question="Will the ferry pick up the slack?")
    assert (first.id, second.id) == ("FC1", "FC2")
    first.path.unlink()
    third = add_fc(root, question="Will the detour stay signed?")
    assert third.id == "FC3"  # FC1 stays reserved in .flip/ids
    cluster = forecast.add_cluster(
        root, "Should the town budget a second span?", ["FC2"], None
    )
    assert cluster.id == "CL1"


# ---------------------------------------------------------------- update


def test_update_appends_and_moves_current_scalars(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    page = forecast.update_forecast(root, "FC1", probability=0.45, note="new minutes")
    assert page.fm["probability"] == 0.45
    assert page.fm["confidence"] == 0.55  # untouched
    updates = page.fm["updates"]
    assert len(updates) == 1
    assert updates[0]["probability"] == 0.45
    assert updates[0]["note"] == "new minutes"
    assert updates[0]["by"] == "human:test"
    assert updates[0]["at"]


def test_updates_are_append_only(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    forecast.update_forecast(root, "FC1", probability=0.45)
    page = forecast.update_forecast(root, "FC1", confidence=0.7, note="second look")
    updates = page.fm["updates"]
    assert len(updates) == 2
    assert updates[0]["probability"] == 0.45  # first record intact
    assert updates[1]["confidence"] == 0.7
    assert page.fm["probability"] == 0.45 and page.fm["confidence"] == 0.7


def test_update_refuses_non_open_and_empty(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    with pytest.raises(SystemExit) as exc:
        forecast.update_forecast(root, "FC1")
    assert "nothing to record" in str(exc.value)
    forecast.resolve_forecast(root, "FC1", "yes")
    with pytest.raises(SystemExit) as exc:
        forecast.update_forecast(root, "FC1", probability=0.9)
    assert "not open" in str(exc.value)


def test_update_unknown_forecast_lists_known(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    with pytest.raises(SystemExit) as exc:
        forecast.update_forecast(root, "FC9", probability=0.5)
    assert "no forecast 'FC9'" in str(exc.value) and "FC1" in str(exc.value)


# ---------------------------------------------------------------- resolve


def test_resolve_yes_writes_rs_row_with_shift(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root, bears_on=["claim:the-span-is-past-rating"],
           resolves_via=["town-meeting-minutes", "state-dot-notices"])
    page = forecast.resolve_forecast(root, "FC1", "yes", note="closure vote passed")
    assert page.fm["status"] == "resolved-yes"
    assert page.fm["updates"][-1]["outcome"] == "yes"
    rows = read_jsonl(root / "log" / "resolutions.jsonl")
    assert len(rows) == 1
    row = rows[0]
    assert row["forecast"] == "FC1"
    assert row["topic"] == QUESTION
    assert row["bears_on"] == ["claim:the-span-is-past-rating"]
    assert row["prior"] == 0.3
    assert row["evidence"] == "closure vote passed"
    assert row["posterior"] == 1.0
    assert row["shift"] == pytest.approx(0.7)
    assert row["confidence"] == 0.55
    assert row["source"] == "town-meeting-minutes, state-dot-notices"


def test_resolve_no_scores_against_prior(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    forecast.resolve_forecast(root, "FC1", "no")
    row = read_jsonl(root / "log" / "resolutions.jsonl")[0]
    assert row["posterior"] == 0.0
    assert row["shift"] == pytest.approx(-0.3)
    assert row["evidence"] == ""


def test_resolve_void_scores_nothing(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    page = forecast.resolve_forecast(root, "FC1", "void", note="bridge demolished")
    assert page.fm["status"] == "void"
    row = read_jsonl(root / "log" / "resolutions.jsonl")[0]
    assert row["posterior"] is None
    assert row["shift"] is None


def test_resolve_logs_event_and_is_final(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    forecast.resolve_forecast(root, "FC1", "yes")
    log_rows = read_jsonl(root / "log" / "log.jsonl")
    assert any(r.get("text") == "forecast-resolve FC1: yes" for r in log_rows)
    with pytest.raises(SystemExit) as exc:
        forecast.resolve_forecast(root, "FC1", "no")
    assert "already 'resolved-yes'" in str(exc.value)
    with pytest.raises(SystemExit) as exc:
        forecast.resolve_forecast(root, "FC1", "maybe")
    assert "invalid outcome" in str(exc.value)


# ---------------------------------------------------------------- decline (the fold)


def test_decline_appends_to_declined_ledger(tmp_path):
    root = make_notebook(tmp_path)
    row = forecast.decline_forecast(
        root, "Will the toll change before the closure?", "collinear with FC1"
    )
    rows = read_jsonl(root / "log" / "declined-forecasts.jsonl")
    assert rows == [row]
    assert row["disposition"] == "declined"
    assert row["reason"] == "collinear with FC1"
    assert row["actor"] == "human:test"
    assert "fold_into" not in row


def test_decline_fold_into_must_exist(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    row = forecast.decline_forecast(
        root, "Will a second inspection be ordered?",
        "absorbed as an annulment clause", fold_into="FC1",
    )
    assert row["fold_into"] == "FC1"
    with pytest.raises(SystemExit) as exc:
        forecast.decline_forecast(root, "another", "reason", fold_into="FC9")
    assert "no forecast 'FC9'" in str(exc.value)
    # the refused fold wrote nothing
    assert len(read_jsonl(root / "log" / "declined-forecasts.jsonl")) == 1


# ---------------------------------------------------------------- due windowing


def test_due_forecasts_window_and_order(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root, question="overdue bet", resolves_by=day(-3))
    add_fc(root, question="near bet", resolves_by=day(10))
    add_fc(root, question="far bet", resolves_by=day(90))
    add_fc(root, question="resolved bet", resolves_by=day(-1))
    forecast.resolve_forecast(root, "FC4", "no")
    rows = forecast.due_forecasts(root)
    assert [r["id"] for r in rows] == ["FC1", "FC2"]  # date order, resolved out
    assert rows[0]["days_left"] == -3 and rows[1]["days_left"] == 10
    wide = forecast.due_forecasts(root, within_days=365)
    assert [r["id"] for r in wide] == ["FC1", "FC2", "FC3"]


# ---------------------------------------------------------------- calibration


def test_calibration_counts_and_sharpness(tmp_path):
    root = make_notebook(tmp_path)
    for i, q in enumerate(["a?", "b?", "c?", "d?"], start=1):
        add_fc(root, question=q)
    forecast.resolve_forecast(root, "FC1", "yes")
    forecast.resolve_forecast(root, "FC2", "no")
    forecast.resolve_forecast(root, "FC3", "void")
    cal = forecast.calibration(root)
    assert cal["open"] == 1
    assert cal["resolved_yes"] == 1 and cal["resolved_no"] == 1 and cal["void"] == 1
    assert cal["n_scored"] == 2
    assert cal["sharpness"] == pytest.approx(0.5)
    assert cal["brier"] is None  # the volume rule: <5 scored resolutions


def test_calibration_empty_record(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    cal = forecast.calibration(root)
    assert cal == {
        "open": 1, "resolved_yes": 0, "resolved_no": 0, "void": 0,
        "sharpness": None, "brier": None, "n_scored": 0,
    }


def test_calibration_brier_after_volume(tmp_path):
    root = make_notebook(tmp_path)
    for i in range(5):
        add_fc(root, question=f"bet {i}?", probability=0.3)
    for i in range(1, 6):
        forecast.resolve_forecast(root, f"FC{i}", "yes" if i <= 2 else "no")
    cal = forecast.calibration(root)
    assert cal["n_scored"] == 5
    # two YES at prior 0.3 → 0.49 each; three NO at 0.3 → 0.09 each
    assert cal["brier"] == pytest.approx((2 * 0.49 + 3 * 0.09) / 5)
    assert cal["sharpness"] == pytest.approx(2 / 5)


# ---------------------------------------------------------------- clusters


def test_add_cluster_unscored_by_construction(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    claims.add_claim(root, "Closure disclosure precedes any budget line", [])
    page = forecast.add_cluster(
        root,
        "Should the town budget a second span or a ferry?",
        ["FC1"],
        "C1",
        horizon=2030,
    )
    fm = page.fm
    assert fm["type"] == "Cluster" and fm["id"] == "CL1"
    assert fm["scored"] is False
    assert "probability" in fm and fm["probability"] is None  # key written, null
    assert fm["proxies"] == ["FC1"]
    assert fm["inference_link"] == "C1"
    assert fm["horizon"] == 2030
    assert fm["status"] == "open"
    # the page serializes the null (write key with None)
    assert "probability: null" in page.path.read_text(encoding="utf-8")


def test_add_cluster_refuses_unknown_proxy(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    with pytest.raises(SystemExit) as exc:
        forecast.add_cluster(root, "decide?", ["FC1", "FC9"], None)
    assert "unknown proxy forecast(s) FC9" in str(exc.value)
    with pytest.raises(SystemExit) as exc:
        forecast.add_cluster(root, "decide?", [], None)
    assert "no proxies" in str(exc.value)


def test_add_cluster_inference_link_class_purity(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    # a Forecast id is not a Claim id — class purity refuses at write time
    with pytest.raises(SystemExit) as exc:
        forecast.add_cluster(root, "decide?", ["FC1"], "FC1")
    assert "not an existing claim id" in str(exc.value)
    page = forecast.add_cluster(root, "decide?", ["FC1"], None)
    assert page.fm["inference_link"] is None  # a linkless cluster is legal


# ---------------------------------------------------------------- doctor


def _errors(findings, code=None):
    return [f for f in findings if f.level == "ERROR" and (code is None or f.code == code)]


def _warns(findings, code=None):
    return [f for f in findings if f.level == "WARN" and (code is None or f.code == code)]


def test_doctor_two_object_gate_both_directions(tmp_path):
    root = make_notebook(tmp_path)
    claim = claims.add_claim(root, "The span is past its load rating", [])
    claim.fm["probability"] = 0.4
    claim.fm["confidence"] = 0.5
    pages.write_page(claim.path, claim.fm, claim.body)
    fc = add_fc(root)
    fc.fm["grade"] = "B"
    fc.fm["support"] = {"basis": "measured"}
    fc.fm["independence"] = "independent"
    pages.write_page(fc.path, fc.fm, fc.body)
    findings = run_doctor(root)
    gate = _errors(findings, "two-object")
    assert len(gate) == 5  # probability+confidence on the claim, three keys on the forecast
    assert any("claim C1 carries 'probability'" in f.message for f in gate)
    assert any("forecast FC1 carries 'grade'" in f.message for f in gate)


def test_doctor_clean_forecast_draws_no_findings(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    findings = run_doctor(root)
    assert not _errors(findings)
    assert not _warns(findings, "overdue-forecast")
    assert not _warns(findings, "dangling-bears-on")


def test_doctor_open_forecast_missing_wiring_errors(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "forecasts" / "bare-bet.md",
        {"type": "Forecast", "id": "FC1", "aliases": ["FC1"],
         "question": "bare?", "probability": 0.5, "confidence": 0.5,
         "status": "open", "updates": []},
        "bare?\n",
    )
    findings = run_doctor(root)
    undated = _errors(findings, "undated-forecast")
    assert len(undated) == 1 and "no undated forecasts" in undated[0].message
    annul = _errors(findings, "missing-annul-if")
    assert len(annul) == 1 and "mandatory" in annul[0].message


def test_doctor_overdue_open_forecast_warns(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root, resolves_by=day(-5))
    findings = run_doctor(root)
    overdue = _warns(findings, "overdue-forecast")
    assert len(overdue) == 1
    assert "overdue — resolve or void" in overdue[0].message
    # resolving clears it
    forecast.resolve_forecast(root, "FC1", "void")
    assert not _warns(run_doctor(root), "overdue-forecast")


def test_doctor_bad_enums_error(tmp_path):
    root = make_notebook(tmp_path)
    fc = add_fc(root)
    fc.fm["status"] = "settled"
    fc.fm["predictability"] = "opaque"
    pages.write_page(fc.path, fc.fm, fc.body)
    findings = run_doctor(root)
    enums = _errors(findings, "bad-enum")
    assert any("status 'settled'" in f.message for f in enums)
    assert any("predictability 'opaque'" in f.message for f in enums)


def test_doctor_bears_on_dangling_and_untyped(tmp_path):
    root = make_notebook(tmp_path)
    claims.add_claim(root, "The span is past its load rating", [])
    fc = add_fc(root, bears_on=["claim:C1", "claim:nobody-home", "question:Q9"])
    findings = run_doctor(root)
    dangling = _warns(findings, "dangling-bears-on")
    assert len(dangling) == 2  # C1 resolves (by id); the other two don't
    fc.fm["bears_on"] = ["C1"]  # untyped, hand-edited
    pages.write_page(fc.path, fc.fm, fc.body)
    findings = run_doctor(root)
    assert len(_errors(findings, "untyped-ref")) == 1


def test_doctor_bears_on_resolves_by_slug_too(tmp_path):
    root = make_notebook(tmp_path)
    claim = claims.add_claim(root, "The span is past its load rating", [])
    add_fc(root, bears_on=[f"claim:{claim.slug}"])
    assert not _warns(run_doctor(root), "dangling-bears-on")


def test_doctor_cluster_checks(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    pages.write_page(
        root / "forecasts" / "scored-cluster.md",
        {"type": "Cluster", "id": "CL1", "aliases": ["CL1"],
         "decision_question": "decide?", "scored": False, "probability": 0.6,
         "proxies": ["FC1", "FC9"], "inference_link": "FC1", "status": "open"},
        "decide?\n",
    )
    findings = run_doctor(root)
    scored = _errors(findings, "scored-cluster")
    assert len(scored) == 1 and "no probability, by construction" in scored[0].message
    impure = _errors(findings, "impure-inference-link")
    assert len(impure) == 1 and "class purity" in impure[0].message
    proxies = _warns(findings, "dangling-proxy")
    assert len(proxies) == 1 and "'FC9'" in proxies[0].message


def test_doctor_cluster_dangling_inference_link_warns(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    cluster = forecast.add_cluster(root, "decide?", ["FC1"], None)
    cluster.fm["inference_link"] = "no-such-claim"
    pages.write_page(cluster.path, cluster.fm, cluster.body)
    findings = run_doctor(root)
    assert len(_warns(findings, "dangling-inference-link")) == 1
    assert not _errors(findings)


def test_doctor_wrong_prefix_in_forecasts_dir(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "forecasts" / "misfiled.md",
        {"type": "Forecast", "id": "Q7", "aliases": ["Q7"], "question": "misfiled?",
         "resolves_by": "2199-01-01", "annul_if": "x", "probability": 0.5,
         "confidence": 0.5, "status": "open", "updates": []},
        "misfiled?\n",
    )
    findings = run_doctor(root)
    wrong = _errors(findings, "wrong-prefix")
    assert len(wrong) == 1
    assert "CL, FC" in wrong[0].message


# ---------------------------------------------------------------- the as-is fixture

# The pilot field set, invented subject: a forecast on a fictional regional
# freight co-op's contracted service book, plus the cluster above it. Shape,
# key set, and value styles mirror the acceptance files exactly (modulo the
# FC#/CL# prefixes and the forecasts/ directory).
PILOT_SHAPED_FORECAST = """\
---
id: FC1
type: Forecast
question: "Will Harborline's annual filing for 2026 disclose at least $2 million of contracted service revenue it expects to recognise in 2028 or later?"
resolution_criteria: |
  Resolves YES if the revenue note of Harborline Co-op's annual filing for the
  year ended 2026-12-31 states remaining contracted amounts expected in 2028 or
  any later period summing to $2,000,000 or more.

  Edge cases, pre-answered:
  - **A twelve-month renewal resolves NO.** Short renewals never enter the table.
  - **A usage-based renewal resolves NO.** Variable consideration is excluded.
  - **A range** resolves on the stated lower bound.
resolves_by: 2199-03-31
resolves_via: [registry-harborline-filing, registry-full-text-search]
resolution_source_ladder:
  - "the registry's filing index → the 2026 annual filing → the revenue note"
  - "the registry's full-text search for the contracted-amounts phrase"
  - "if the filing is late: the extension notice, then the filing when it lands"
resolver: desk (surface sweep), on the literal filed text
probability: 0.30
confidence: 0.55
base_rate: "0/1 observed year produced a new outer-year allocation; net new long-duration contracted value across the year was ~4% of the book."
predictability: gray-light
annul_if: "Harborline ceases to file annual reports before the 2026 filing; or the contracted-amounts schedule is dropped entirely, so the question cannot be answered on its own terms."
bears_on: [cluster:berth-or-annuity, claim:harborline-book-runoff, claim:the-charter-sells-once]
generated_by: mill/contracted-book-cliff
horizon: 2028
opened: 2026-07-25
freeze: 2026-07-25
status: open
updates: []
---

# FC1 — Does the strongest carrier's contracted book extend past its cliff?

## Outside view, stated first

One prior observation of this transition exists, and it points down.

## Inside view

**Toward YES.** Renewals cluster in the twelve months before expiry.

**Toward NO, and this is the heavier side.** Three separate mechanisms convert
a real renewal into a NO.

## Key assumption, and what breaks it

**Assumption:** buyers keep preferring fixed-term, front-loaded charters.
"""

PILOT_SHAPED_CLUSTER = """\
---
id: CL1
type: Cluster
decision_question: "For a charter signed in 2028 or later, should a mid-size shipper price it as a one-time berth sale or as a recurring revenue line?"
scored: false
probability: null            # a decision question carries no probability, by construction
proxies: [FC1]
deferred_proxies: [G6, G7, G31]
inference_link: C1           # a Claim-class object with a grade
horizon: 2030
opened: 2026-07-25
status: open
---

# Cluster CL1 — berth sale or annuity?

Three tiers, structurally distinct. The top tier is a decision and carries no
number. The middle tier is bets and carries numbers. The bottom tier is a
piece of reasoning and carries a grade.
"""


def test_pilot_shaped_fixture_validates_error_free(tmp_path):
    """The acceptance bar: the pilot's full field set, held as-is (modulo id
    prefix and directory), draws zero doctor ERRORs — and its typed refs
    resolve once the pages they name exist."""
    root = make_notebook(tmp_path)
    (root / "forecasts").mkdir(exist_ok=True)
    (root / "forecasts" / "harborline-2028-contracted-book.md").write_text(
        PILOT_SHAPED_FORECAST, encoding="utf-8"
    )
    (root / "forecasts" / "berth-or-annuity.md").write_text(
        PILOT_SHAPED_CLUSTER, encoding="utf-8"
    )
    # the pages the typed refs name (slug-addressed claims, the C1 link claim)
    claims.add_claim(root, "The inference link: disclosure precedes price", [])  # C1
    pages.write_page(
        root / "claims" / "harborline-book-runoff.md",
        {"type": "Claim", "id": "C2", "aliases": ["C2"], "status": "asserted",
         "description": "the book runs off", "sources": [], "load_bearing": False},
        "the book runs off\n",
    )
    pages.write_page(
        root / "claims" / "the-charter-sells-once.md",
        {"type": "Claim", "id": "C3", "aliases": ["C3"], "status": "asserted",
         "description": "the charter sells once", "sources": [], "load_bearing": False},
        "the charter sells once\n",
    )
    findings = run_doctor(root)
    assert not _errors(findings), [f.message for f in _errors(findings)]
    # no forecast-lane WARNs either — refs resolve, nothing overdue or dangling
    for code in ("dangling-bears-on", "dangling-proxy", "dangling-inference-link",
                 "overdue-forecast", "untyped-ref"):
        assert not _warns(findings, code) and not _errors(findings, code)
    # the only advisory allowed on the as-is pages is the aliases nudge
    fixture_paths = {"forecasts/harborline-2028-contracted-book.md",
                     "forecasts/berth-or-annuity.md"}
    for f in findings:
        if f.path in fixture_paths:
            assert f.code == "missing-alias", (f.code, f.message)
    # and the pages round-trip: every pilot key survives a read
    page = pages.read_page(root / "forecasts" / "harborline-2028-contracted-book.md")
    for key in ("question", "resolution_criteria", "resolves_by", "resolves_via",
                "resolution_source_ladder", "resolver", "probability", "confidence",
                "base_rate", "predictability", "annul_if", "bears_on",
                "generated_by", "horizon", "opened", "freeze", "status", "updates"):
        assert key in page.fm, key
    cluster = pages.read_page(root / "forecasts" / "berth-or-annuity.md")
    assert cluster.fm["probability"] is None
    assert cluster.fm["deferred_proxies"] == ["G6", "G7", "G31"]
    # resolve on the copy produces the RS row (the acceptance test's last leg)
    forecast.resolve_forecast(root, "FC1", "no", note="no outer-year bucket appeared")
    row = read_jsonl(root / "log" / "resolutions.jsonl")[0]
    assert row["forecast"] == "FC1" and row["posterior"] == 0.0
    assert row["prior"] == pytest.approx(0.30)


# ---------------------------------------------------------------- forward-set kind


def test_forward_set_kind_parses_with_aka(tmp_path):
    k = kinds.load_kind("forward-set")
    assert k.origin == "built-in"
    assert set(k.aka) == {"forecast set", "predictions", "what to watch", "forward look"}
    by_id = {r.id: r for r in k.contract}
    assert by_id["three-dated-forecasts"].min == 3
    assert by_id["three-dated-forecasts"].entity == "forecasts"
    assert by_id["three-dated-forecasts"].field == "resolves_by"
    assert by_id["three-dated-forecasts"].assembled_by == "the forecast board"
    assert by_id["baseline-declared"].prospective is True
    assert by_id["baseline-declared"].path == "baseline.md"
    assert kinds.resolve_kind_id("what to watch") == "forward-set"
    assert kinds.resolve_kind_id("Forecast Set") == "forward-set"


def test_forward_set_gap_check_and_satisfaction(tmp_path):
    root = make_notebook(tmp_path)
    _k, rows = kinds.adopt_kind(root, "forward-set")
    by_id = {r.requirement_id: r for r in rows}
    assert by_id["three-dated-forecasts"].tier == "recoverable"
    assert by_id["baseline-declared"].tier == "unrecoverable-by-construction"
    for q in ("first bet?", "second bet?", "third bet?"):
        add_fc(root, question=q)
    (root / "baseline.md").write_text("# Baseline\nnaive: no change\n", encoding="utf-8")
    rows = kinds.gap_manifest(root, kinds.load_kind("forward-set", root))
    assert all(r.tier == "met" for r in rows), [(r.requirement_id, r.tier) for r in rows]


def test_forward_set_undated_pages_do_not_count(tmp_path):
    root = make_notebook(tmp_path)
    kinds.adopt_kind(root, "forward-set")
    add_fc(root)
    # a cluster has no resolves_by, so it never counts toward the three
    forecast.add_cluster(root, "decide?", ["FC1"], None)
    rows = kinds.gap_manifest(root, kinds.load_kind("forward-set", root))
    board = next(r for r in rows if r.requirement_id == "three-dated-forecasts")
    assert board.have == 1 and board.tier == "reconstructible-with-loss"


# ---------------------------------------------------------------- export


def test_export_v2_carries_forecasts_v1_unchanged(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root, horizon=2028)
    forecast.update_forecast(root, "FC1", probability=0.4)
    add_fc(root, question="second?", resolves_by="2199-06-30")
    forecast.add_cluster(root, "decide?", ["FC1"], None)
    v2 = export_json(root, include_private=True, render_version=2)
    rows = v2["forecasts"]
    assert [r["id"] for r in rows] == ["FC1", "FC2"]  # clusters stay out
    first = rows[0]
    assert first == {
        "id": "FC1",
        "question": QUESTION,
        "status": "open",
        "probability": 0.4,
        "confidence": 0.55,
        "resolves_by": "2199-03-31",
        "resolves_via": ["town-meeting-minutes"],
        "horizon": 2028,
        "updates": 1,
    }
    v1 = export_json(root, include_private=True, render_version=1)
    assert "forecasts" not in v1
    assert v1["contract"] == "flip-render/1"


# ---------------------------------------------------------------- CLI


def test_cli_forecast_add_update_resolve_roundtrip(tmp_path):
    root = make_notebook(tmp_path)
    nb = ["--notebook", str(root)]
    result = invoke(nb + [
        "forecast", "add", QUESTION,
        "--resolves-by", "2199-03-31", "--resolves-via", "town-meeting-minutes",
        "--annul-if", "The bridge is demolished first",
        "--probability", "0.3", "--confidence", "0.55",
        "--ladder", "council vote record", "--ladder", "the clerk's minutes",
        "--bears-on", "claim:C1", "--predictability", "gray-light",
    ])
    assert result.exit_code == 0, result.output
    assert "FC1 open" in result.output
    page = pages.find_by_id(root, "FC1")
    assert page.fm["resolution_source_ladder"] == [
        "council vote record", "the clerk's minutes",
    ]
    result = invoke(nb + ["forecast", "update", "FC1", "--probability", "0.6"])
    assert result.exit_code == 0 and "1 update(s)" in result.output
    result = invoke(nb + ["forecast", "list"])
    assert result.exit_code == 0
    assert "FC1 · open · 2199-03-31 · p=0.6/c=0.55" in result.output
    result = invoke(nb + ["forecast", "resolve", "FC1", "yes", "--note", "it closed"])
    assert result.exit_code == 0 and "resolved-yes" in result.output
    result = invoke(nb + ["forecast", "resolve", "FC1", "no"])
    assert result.exit_code != 0  # final


def test_cli_forecast_add_refusal_is_actionable(tmp_path):
    root = make_notebook(tmp_path)
    result = invoke(["--notebook", str(root), "forecast", "add", "undated bet?",
                     "--annul-if", "x", "--probability", "0.5", "--confidence", "0.5"])
    assert result.exit_code != 0
    assert "no undated forecasts" in result.output


def test_cli_forecast_due_and_decline(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root, resolves_by=day(5))
    nb = ["--notebook", str(root)]
    result = invoke(nb + ["forecast", "due"])
    assert result.exit_code == 0 and "FC1" in result.output and "in 5d" in result.output
    result = invoke(nb + ["forecast", "due", "--json"])
    rows = json.loads(result.output)
    assert rows[0]["id"] == "FC1" and rows[0]["days_left"] == 5
    result = invoke(nb + ["forecast", "decline", "a generated question?",
                          "--reason", "no enumerable denominator",
                          "--fold-into", "FC1"])
    assert result.exit_code == 0 and "folded into FC1" in result.output
    result = invoke(nb + ["forecast", "decline", "another?", "--reason", "r",
                          "--fold-into", "FC9"])
    assert result.exit_code != 0


def test_cli_show_forecasts_labeled_record(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root, resolves_by=day(3))
    add_fc(root, question="later bet?", resolves_by="2199-06-30")
    add_fc(root, question="scored bet?", resolves_by=day(1))
    forecast.resolve_forecast(root, "FC3", "yes")
    result = invoke(["--notebook", str(root), "show", "--forecasts"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "DUE FORECASTS" in out and "OPEN FORECASTS" in out
    assert out.index("FC1") < out.index("FC2")  # due first
    assert "sharpness (resolved-yes share): 1.00" in out
    assert "Brier (needs ≥5 resolutions): n/a" in out
    result = invoke(["--notebook", str(root), "show", "--forecasts", "--json"])
    data = json.loads(result.output)
    assert data["calibration"]["resolved_yes"] == 1
    result = invoke(["--notebook", str(root), "show", "--forecasts", "--claims"])
    assert result.exit_code != 0  # at most one view flag


def test_cli_show_forecasts_empty_board(tmp_path):
    root = make_notebook(tmp_path)
    result = invoke(["--notebook", str(root), "show", "--forecasts"])
    assert result.exit_code == 0
    assert "no open forecasts" in result.output
    assert "sharpness (resolved-yes share): n/a" in result.output


# ---------------------------------------------------------------- integration


def test_open_and_resolve_ref_route_fc_ids(tmp_path):
    root = make_notebook(tmp_path)
    page = add_fc(root)
    found = pages.find_by_id(root, "FC1")
    assert found is not None and found.path == page.path
    result = invoke(["--notebook", str(root), "open", "FC1"])
    assert result.exit_code == 0
    assert result.output.strip() == str(page.path)


def test_views_regenerate_lists_forecasts(tmp_path):
    root = make_notebook(tmp_path)
    add_fc(root)
    index = (root / "forecasts" / "index.md").read_text(encoding="utf-8")
    assert index.startswith("# Forecasts")
    assert "FC1" in index
    body = (root / "index.md").read_text(encoding="utf-8")
    assert "[Forecasts](forecasts/)" in body


def test_forecast_status_kept_when_manifest_closes(tmp_path):
    """An open forecast survives notebook closure — resolution is its own
    lifecycle; doctor stays quiet about open bets in a done notebook (the
    overdue WARN is the only nudge, and only past the date)."""
    root = make_notebook(tmp_path)
    add_fc(root)
    m = load_manifest(root)
    m.status = "done"
    save_manifest(root, m)
    findings = run_doctor(root)
    assert not _errors(findings, "undated-forecast")
    assert not _warns(findings, "overdue-forecast")
