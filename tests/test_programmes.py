"""Tests for flip.programmes — research programmes and their appraisal (SPEC §7).

The thing under test is a *distinction*, so most of these tests are about
which of two superficially identical situations flip puts on which side of it:

- a claim nobody has tested vs. a claim that took a hit (hard core vs. anomaly);
- a modification that bought excess content vs. one that bought none — never
  a modification that accommodated vs. one that did not, because *every*
  modification in the series accommodates (Lakatos 1970, p. 33);
- a bet registered before its evidence vs. one registered after (prediction
  vs. retrodiction) — which is decided on dates, and only on dates;
- an appraisal (`degenerating`) vs. grounds for elimination (a rival
  out-predicting it), which Lakatos treats as different questions (p. 69);
- a barren stretch vs. a barren *run*, since "empirical progress" is only ever
  owed intermittently (p. 49);
- a belief the notebook holds vs. one it records somebody else holding.

The verdict itself is never stored, so every appraisal test reads it back
through `appraise` rather than off a page: that is the point of deriving it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import claims, forecast, pages, programmes, scaffold, views
from flip.cli import main
from flip.doctor import run_doctor


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep every test away from the real ~/.flip and the host's git identity."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def make_notebook(tmp_path: Path, kind: str = "scout", slug: str = "demo") -> Path:
    return scaffold.create_notebook(tmp_path / slug, slug, kind)


def add_claims(root: Path, n: int, load_bearing: bool = False) -> list[str]:
    return [
        claims.add_claim(root, f"Proposition number {i}", [], load_bearing=load_bearing).id
        for i in range(1, n + 1)
    ]


def add_fc(root: Path, bears_on: list[str], probability: float = 0.4, **kw):
    args = {
        "resolves_by": "2199-03-31",
        "resolves_via": ["a surface the desk can read"],
        "annul_if": "The surface stops being published",
        "confidence": 0.5,
    }
    args.update(kw)
    return forecast.add_forecast(
        root,
        kw.pop("question", "Will the watched surface show the predicted movement?"),
        args["resolves_by"],
        args["resolves_via"],
        args["annul_if"],
        probability,
        args["confidence"],
        bears_on=bears_on,
    )


def opened_on(root: Path, fid: str, day: str) -> None:
    """Backdate a forecast's registration date. flip's clock only runs forward,
    so a test about a bet that predates its own resolution has to say so."""
    page = next(p for p in pages.iter_pages(root, "forecasts") if p.id == fid)
    page.fm["opened"] = day
    pages.write_page(page.path, page.fm, page.body)


def find(root: Path, rp: str) -> pages.Page:
    return next(p for p in pages.iter_pages(root, "analysis") if p.id == rp)


def flat(root: Path, rp: str | None = None) -> str:
    """The programmes view with its terminal wrapping undone, so a test can
    assert on a sentence without asserting on where the line broke."""
    return " ".join(str(views.programmes_view(root, rp)).split())


def codes(root: Path) -> list[str]:
    return [f.code for f in run_doctor(root)]


def barren(root: Path, rp: str, n: int, first_hit: str = "C2") -> None:
    """Record `n` problemshifts that buy nothing — the run the degenerating
    verdict is defined against."""
    for i in range(n):
        programmes.record_shift(root, rp, f"Barren occasion {i + 1}", hits=[first_hit])


# ---------------------------------------------------------------- declaration


def test_add_programme_writes_an_analysis_page_with_core_and_belt(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    page = programmes.add_programme(root, "The difficulty is relational", ["C1"], ["C2", "C3"])
    assert page.path.parent == root / "analysis"
    fm = page.fm
    assert fm["type"] == "Programme"
    assert fm["id"] == "RP1" and fm["aliases"] == ["RP1"]
    assert fm["hard_core"] == ["C1"]
    assert fm["protective_belt"] == ["C2", "C3"]
    assert fm["held_by"] == "self"
    assert fm["status"] == "pursued"
    assert fm["shifts"] == [] and fm["acknowledged"] == []
    # No verdict anywhere on the page: the appraisal is derived on every read,
    # the way a source's grade is derived from its support tuple (SPEC §5.4).
    assert not any(k in fm for k in ("verdict", "progressive", "degenerating"))


def test_programme_without_a_hard_core_is_refused(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    with pytest.raises(SystemExit) as e:
        programmes.add_programme(root, "A mood", [], ["C1"])
    assert "a mood" in str(e.value) and "--hard-core" in str(e.value)


def test_core_member_that_is_not_a_claim_is_refused_with_the_known_list(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    with pytest.raises(SystemExit) as e:
        programmes.add_programme(root, "Pointing at nothing", ["Q9"])
    msg = str(e.value)
    assert "Q9" in msg and "class purity" in msg
    assert "C1, C2" in msg  # the refusal says what it could have taken


def test_a_claim_cannot_be_declared_both_core_and_belt(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    with pytest.raises(SystemExit) as e:
        programmes.add_programme(root, "Both at once", ["C1"], ["C1", "C2"])
    assert "never both" in str(e.value)


def test_held_by_records_somebody_elses_programme(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    page = programmes.add_programme(
        root, "Their line of thinking", ["C1"], ["C2"], held_by="the audit movement"
    )
    assert page.fm["held_by"] == "the audit movement"


def test_rp_ids_do_not_collide_with_source_p_ids(tmp_path):
    """RP and P are disjoint prefixes (SPEC §9), so a notebook holding P3 still
    hands out RP1 — and a bare [RP1] cite stays unambiguous."""
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    pages.write_page(
        root / "references" / "paper.md",
        {"type": "Source", "id": "P3", "aliases": ["P3"], "title": "A paper"},
        "",
    )
    page = programmes.add_programme(root, "Disjoint", ["C1"])
    assert page.fm["id"] == "RP1"
    assert pages.find_by_id(root, "RP1") is not None
    assert invoke(["--notebook", str(root), "open", "RP1"]).exit_code == 0


# ---------------------------------------------------------------- belt and shifts


def test_belt_grows_but_the_core_has_no_command(tmp_path):
    """The core is declared once. A programme with a different core is a
    different programme, and the honest record of that is a new RP#."""
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    _page, added = programmes.extend_belt(root, "RP1", ["C3"])
    assert added == ["C3"]
    assert find(root, "RP1").fm["protective_belt"] == ["C2", "C3"]
    with pytest.raises(SystemExit) as e:
        programmes.extend_belt(root, "RP1", ["C1"])
    assert "hard core" in str(e.value)
    with pytest.raises(SystemExit) as e:
        programmes.extend_belt(root, "RP1", ["C3"])
    assert "nothing to add" in str(e.value)


def test_shift_records_the_occasion_and_grows_the_belt(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 4)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    _page, record = programmes.record_shift(
        root, "RP1", "The cited paper does not contain the proposition",
        hits=["C2"], absorbed_by=["C3", "C4"],
    )
    assert record["hits"] == ["C2"] and record["absorbed_by"] == ["C3", "C4"]
    assert record["by"] == "human:test"
    fm = find(root, "RP1").fm
    assert len(fm["shifts"]) == 1
    # Recording a shift IS how the belt grows — the reply to an anomaly is by
    # definition an auxiliary hypothesis.
    assert fm["protective_belt"] == ["C2", "C3", "C4"]
    # Nothing about the appraisal was written down.
    assert set(record) == {"at", "occasion", "hits", "absorbed_by", "by"}


def test_an_anomaly_may_hit_the_hard_core_and_the_core_stands(tmp_path):
    """Anomalies never falsify a core — that is not what they are for. The hit
    is recorded and the core keeps its membership; what changes is the belt."""
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "A direct hit on the core", hits=["C1"],
                            absorbed_by=["C3"])
    fm = find(root, "RP1").fm
    assert fm["hard_core"] == ["C1"]
    assert fm["protective_belt"] == ["C2", "C3"]


def test_an_anomaly_cannot_be_absorbed_into_the_hard_core(tmp_path):
    """A core that quietly moves under fire was never held by decision."""
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    with pytest.raises(SystemExit) as e:
        programmes.record_shift(root, "RP1", "Hit", hits=["C2"], absorbed_by=["C1"])
    assert "cannot absorb an anomaly into RP1's hard core" in str(e.value)
    assert "successor programme" in str(e.value)


def test_a_hit_on_something_the_programme_does_not_hold_is_refused(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    with pytest.raises(SystemExit) as e:
        programmes.record_shift(root, "RP1", "Hit", hits=["C3"])
    assert "not this programme's anomaly" in str(e.value)


def test_shift_needs_an_occasion(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"])
    with pytest.raises(SystemExit) as e:
        programmes.record_shift(root, "RP1", "  ")
    assert "the occasion is the part a later reader cannot reconstruct" in str(e.value)


# ---------------------------------------------------------------- appraisal


def test_a_fresh_programme_is_unappraised(tmp_path):
    """A derivative needs two points. Declaring a programme this morning is one."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    assert programmes.appraise(root)[0]["verdict"] == "unappraised"


def test_a_run_of_barren_problemshifts_is_degenerating(tmp_path):
    """The abandonment condition Lakatos does name — "if and when the
    programme ceases to anticipate novel facts" (1970, p. 49) — read off a
    *run*, because he demands empirical progress only intermittently."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    barren(root, "RP1", programmes.BARREN_RUN_FOR_DEGENERATION)
    report = programmes.appraise(root)[0]
    assert report["verdict"] == "degenerating"
    assert report["novel_count"] == 0
    assert report["barren_run"] == programmes.BARREN_RUN_FOR_DEGENERATION
    assert not any(s["content_increasing"] for s in report["shifts"])


@pytest.mark.parametrize("n", [1, 2])
def test_a_short_barren_stretch_is_not_yet_a_verdict(tmp_path, n):
    """The hindsight caution, made operational. One barren shift is
    indistinguishable from the ordinary lag between a modification and the bet
    it suggests; flip declines to appraise rather than firing on it, and says
    how much further the run has to go."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    barren(root, "RP1", n)
    report = programmes.appraise(root)[0]
    assert report["verdict"] == "unappraised"
    assert report["barren_run"] == n
    assert "degenerating-programme" not in codes(root)
    assert f"threshold for 'degenerating' is a run of {report['barren_run_threshold']}" in (
        flat(root)
    )


def test_old_corroboration_does_not_immunise_a_programme_that_has_gone_quiet(tmp_path):
    """The verdict is read off the tail of the series, never off the lifetime
    total. A programme that could bank one corroborated bet and coast on it
    forever would be the machine for never being wrong."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "The productive one", hits=["C2"])
    add_fc(root, ["claim:C1"])
    opened_on(root, "FC1", "2026-01-05")
    forecast.resolve_forecast(root, "FC1", "yes", note="It held")
    assert programmes.appraise(root)[0]["verdict"] == "progressive"
    barren(root, "RP1", programmes.BARREN_RUN_FOR_DEGENERATION)
    report = programmes.appraise(root)[0]
    assert report["verdict"] == "degenerating"
    assert report["corroborated_count"] == 1  # the win is still on the record
    assert report["barren_run"] >= programmes.BARREN_RUN_FOR_DEGENERATION


def test_an_open_forecast_on_the_core_is_theoretically_progressive(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"], absorbed_by=["C3"])
    add_fc(root, ["claim:C1"])
    report = programmes.appraise(root)[0]
    assert report["verdict"] == "theoretically-progressive"
    assert report["novel_count"] == 1 and report["corroborated_count"] == 0
    assert report["content"][0]["bucket"] == "open"
    assert report["shifts"][-1]["content_increasing"] is True


def test_theoretically_progressive_is_a_good_standing_and_draws_no_finding(tmp_path):
    """"We do not demand that each step produce immediately an observed new
    fact" (1970, p. 49). Corroboration is owed intermittently, so an
    uncorroborated content-increasing series is not a defect and doctor says
    nothing about it."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    add_fc(root, ["claim:C1"])
    assert programmes.appraise(root)[0]["verdict"] == "theoretically-progressive"
    found = codes(root)
    assert "degenerating-programme" not in found and "superseded-programme" not in found
    assert "good standing, not a warning" in flat(root)


def test_a_forecast_resolved_after_it_opened_makes_the_programme_progressive(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    add_fc(root, ["claim:C1"])
    opened_on(root, "FC1", "2026-01-05")  # the bet predates the day it was called
    forecast.resolve_forecast(root, "FC1", "yes", note="The surface showed it")
    report = programmes.appraise(root)[0]
    assert report["verdict"] == "progressive"
    assert report["corroborated_count"] == 1
    assert report["content"][0]["bucket"] == "corroborated"


def test_a_refuted_novel_prediction_is_still_content(tmp_path):
    """Lakatos's theoretical progress is about excess content, not about being
    right. Scoring a failed risky bet as nothing would only teach the desk to
    bet on certainties — which is exactly the behaviour this is against."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    add_fc(root, ["claim:C1"])
    opened_on(root, "FC1", "2026-01-05")
    forecast.resolve_forecast(root, "FC1", "no", note="The surface showed the opposite")
    report = programmes.appraise(root)[0]
    assert report["content"][0]["bucket"] == "refuted"
    assert report["novel_count"] == 1 and report["corroborated_count"] == 0
    assert report["verdict"] == "theoretically-progressive"


def test_a_bet_opened_and_resolved_the_same_day_is_a_retrodiction_worth_nothing(tmp_path):
    """The crux. Novelty is decided on timing: a bet placed on a race already
    run is an accommodation wearing a prediction's clothes."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    add_fc(root, ["claim:C1"])
    forecast.resolve_forecast(root, "FC1", "yes", note="Knew it already")
    report = programmes.appraise(root)[0]
    assert report["content"][0]["bucket"] == "retrodiction"
    assert report["novel_count"] == 0 and report["retrodiction_count"] == 1
    assert report["shifts"][0]["content_increasing"] is False
    assert "retrodiction" in codes(root)


def test_a_void_forecast_scores_nothing_like_it_scores_nothing_in_brier(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    add_fc(root, ["claim:C1"])
    opened_on(root, "FC1", "2026-01-05")
    forecast.resolve_forecast(root, "FC1", "void", note="The question stopped being askable")
    report = programmes.appraise(root)[0]
    assert report["content"][0]["bucket"] == "annulled"
    assert report["novel_count"] == 0
    assert report["shifts"][0]["content_increasing"] is False


def test_content_is_attributed_to_the_last_shift_that_had_already_happened(tmp_path):
    """Attribution is by date alone — nothing is declared, so nothing can be
    declared falsely."""
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "First", hits=["C2"])
    programmes.record_shift(root, "RP1", "Second", hits=["C2"])
    page = find(root, "RP1")
    page.fm["shifts"][0]["at"] = "2026-01-01T00:00:00Z"
    page.fm["shifts"][1]["at"] = "2026-06-01T00:00:00Z"
    pages.write_page(page.path, page.fm, page.body)
    add_fc(root, ["claim:C1"])
    opened_on(root, "FC1", "2026-03-15")  # after the first shift, before the second
    add_fc(root, ["claim:C1"])
    opened_on(root, "FC2", "2026-07-01")  # after the second
    report = programmes.appraise(root)[0]
    assert report["shifts"][0]["novel"] == ["FC1"]
    assert report["shifts"][1]["novel"] == ["FC2"]


def test_a_forecast_on_a_claim_the_programme_does_not_hold_is_not_its_content(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    add_fc(root, ["claim:C3"])
    report = programmes.appraise(root)[0]
    assert report["content"] == [] and report["novel_count"] == 0
    assert report["shifts"][0]["content_increasing"] is False


def test_unconfirmed_is_not_an_anomaly(tmp_path):
    """The distinction the whole design exists for: a claim nobody has tested
    is the state a hard core lives in, not a hit the programme absorbed. Only
    superseded/retracted/false-positive count as anomalies."""
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2", "C3"])
    claims.set_claim_status(root, "C2", "unconfirmed")
    claims.set_claim_status(root, "C3", "superseded")
    report = programmes.appraise(root)[0]
    assert [a["id"] for a in report["anomalies"]] == ["C3"]


def test_low_risk_content_is_counted_and_labelled_never_subtracted(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    add_fc(root, ["claim:C1"], probability=0.97)
    report = programmes.appraise(root)[0]
    assert report["novel_count"] == 1 and report["low_risk_count"] == 1
    assert report["verdict"] == "theoretically-progressive"
    assert "content, but cheap" in views.programmes_view(root)


# --- elimination is comparative (Lakatos 1970, pp. 34, 36, 69) ----------------
#
# The correction that matters most. `degenerating` appraises the series; only
# an out-predicting rival is grounds to drop it. These tests pin the two apart.


def _winner_and_loser(tmp_path) -> Path:
    """RP1: degenerating, nothing on the record. RP2: progressive, one
    corroborated novel prediction. RP1 declares RP2 its rival."""
    root = make_notebook(tmp_path)
    add_claims(root, 4)
    programmes.add_programme(root, "Ours", ["C1"], ["C2"])
    barren(root, "RP1", programmes.BARREN_RUN_FOR_DEGENERATION)
    programmes.add_programme(root, "Theirs", ["C3"], ["C4"])
    programmes.record_shift(root, "RP2", "Hit", hits=["C4"])
    add_fc(root, ["claim:C3"])
    opened_on(root, "FC1", "2026-01-05")
    forecast.resolve_forecast(root, "FC1", "yes", note="It held")
    page = find(root, "RP1")
    page.fm["rivals"] = ["RP2"]
    pages.write_page(page.path, page.fm, page.body)
    return root


def test_a_degenerating_programme_with_no_better_rival_is_asked_for_nothing(tmp_path):
    """"[I]n spite of hundreds of known anomalies we do not regard it as
    falsified (that is, eliminated) until we have a better one" (1970, p. 36).
    So the appraisal is reported and no signature is demanded: no rival
    predicting more is most of why the programme is still rationally held."""
    root = make_notebook(tmp_path)
    add_claims(root, 4)
    programmes.add_programme(root, "Theirs", ["C3"], ["C4"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C4"])
    programmes.add_programme(root, "Ours", ["C1"], ["C2"], rivals=["RP1"])
    barren(root, "RP2", programmes.BARREN_RUN_FOR_DEGENERATION, first_hit="C2")
    ours = programmes.appraise(root, "RP2")[0]
    assert ours["verdict"] == "degenerating"
    assert ours["outpaced_by"] == []
    found = codes(root)
    assert "degenerating-programme" in found
    assert "superseded-programme" not in found
    out = flat(root, "RP2")
    assert "no rival on record is predicting more" in out
    assert "Nothing here needs signing for" in out
    # And the finding itself asks for no signature.
    line = next(f for f in run_doctor(root) if f.code == "degenerating-programme")
    assert "acknowledge" not in line.message
    assert "nothing here needs signing for" in line.message.lower()


def test_a_rival_that_predicts_more_is_what_turns_the_appraisal_into_a_decision(tmp_path):
    """The one objective reason Lakatos gives for rejecting a programme: "a
    rival research programme which explains the previous success of its rival
    and supersedes it by a further display of heuristic power" (p. 69)."""
    root = _winner_and_loser(tmp_path)
    ours = programmes.appraise(root, "RP1")[0]
    assert ours["verdict"] == "degenerating"
    assert ours["outpaced_by"] == ["RP2"]
    assert ours["rival_verdicts"] == {"RP2": "progressive"}
    found = codes(root)
    assert "superseded-programme" in found
    assert "degenerating-programme" not in found
    line = next(f for f in run_doctor(root) if f.code == "superseded-programme")
    assert "RP2 is predicting more" in line.message
    # The clause flip cannot compute is named rather than quietly assumed.
    assert "which flip cannot check for you" in line.message
    assert "flip programme acknowledge RP1" in line.message


def test_supersession_needs_strictly_more_corroborated_content(tmp_path):
    """"[S]uperseded by a theory with higher corroborated content" (p. 34) —
    higher, so a tie is not a supersession."""
    root = _winner_and_loser(tmp_path)
    # Give the degenerating programme a corroborated win of its own, so the
    # counts tie at 1. It is still degenerating (its tail is barren) but it is
    # no longer being out-predicted, so nothing is asked of it.
    add_fc(root, ["claim:C1"])
    opened_on(root, "FC2", "2026-01-05")
    forecast.resolve_forecast(root, "FC2", "yes", note="It held")
    ours = programmes.appraise(root, "RP1")[0]
    assert ours["verdict"] == "degenerating"
    assert ours["corroborated_count"] == 1 and ours["outpaced_by"] == []
    assert "superseded-programme" not in codes(root)


def test_a_rival_that_has_itself_gone_quiet_supersedes_nothing(tmp_path):
    """The second clause is "a further display of heuristic power", present
    tense. A rival coasting on an old win is not displaying anything."""
    root = _winner_and_loser(tmp_path)
    assert programmes.appraise(root, "RP1")[0]["outpaced_by"] == ["RP2"]
    barren(root, "RP2", programmes.BARREN_RUN_FOR_DEGENERATION, first_hit="C4")
    every = {r["id"]: r for r in programmes.appraise(root)}
    assert every["RP2"]["verdict"] == "degenerating"
    assert every["RP2"]["corroborated_count"] == 1  # still ahead on the total
    assert every["RP1"]["outpaced_by"] == []  # and superseding nothing
    assert "superseded-programme" not in codes(root)


def test_rivalry_is_read_both_ways_so_a_notebook_cannot_duck_the_comparison(tmp_path):
    """Lakatos's comparison is between programmes, not between a programme and
    a list it keeps. RP1 declares RP2; RP2 is appraised against RP1 anyway."""
    root = _winner_and_loser(tmp_path)
    theirs = programmes.appraise(root, "RP2")[0]
    assert theirs["rivals"] == []  # RP2 declared nobody
    assert theirs["rival_verdicts"] == {"RP1": "degenerating"}
    assert theirs["outpaced_by"] == []  # RP1 is behind, not ahead


def test_a_verdict_is_never_asserted_from_a_single_page(tmp_path):
    """`appraise_programme` sees one page and so cannot answer the comparative
    question; only `appraise`, which sees the notebook, may fill it in."""
    root = _winner_and_loser(tmp_path)
    alone = programmes.appraise_programme(root, find(root, "RP1"))
    assert alone["verdict"] == "degenerating"  # the appraisal is per-programme
    assert alone["outpaced_by"] == [] and alone["rival_verdicts"] == {}


# ---------------------------------------------------------------- acknowledgment


def test_acknowledgment_is_refused_on_anything_not_degenerating(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    with pytest.raises(SystemExit) as e:
        programmes.acknowledge(root, "RP1", "Signing early")
    assert "appraises 'unappraised', not degenerating" in str(e.value)


def test_acknowledgment_needs_a_reason(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    barren(root, "RP1", programmes.BARREN_RUN_FOR_DEGENERATION)
    with pytest.raises(SystemExit) as e:
        programmes.acknowledge(root, "RP1", "")
    assert "click-through" in str(e.value)


def test_a_signed_programme_stops_being_doctors_business(tmp_path):
    """Holding a line of thinking that is producing nothing is a legitimate
    research decision. What flip refuses is letting it stay implicit — so the
    finding goes away when it is signed for, and comes back at the next
    barren shift."""
    root = _winner_and_loser(tmp_path)
    assert "superseded-programme" in codes(root)
    programmes.acknowledge(root, "RP1", "The measurement that would test the core is not "
                                        "fielded yet; holding until it is")
    assert "superseded-programme" not in codes(root)
    assert programmes.appraise(root)[0]["acknowledged"] is True
    programmes.record_shift(root, "RP1", "Another barren occasion", hits=["C2"])
    assert "superseded-programme" in codes(root)


def test_a_signature_names_the_rival_it_was_signed_against(tmp_path):
    """The decision worth recording is not "I am holding a programme that has
    gone quiet" — Lakatos says that needs no defence without a better rival —
    it is "I am holding it while RP2 predicts more"."""
    root = _winner_and_loser(tmp_path)
    _page, record = programmes.acknowledge(root, "RP1", "RP2 does not recover what we got right")
    assert record["outpaced_by"] == ["RP2"]
    assert programmes.appraise(root, "RP1")[0]["acknowledged"] is True


def test_a_signature_goes_stale_when_a_new_rival_pulls_ahead(tmp_path):
    """A signature collected when only RP2 was ahead does not cover RP3. That
    is a different decision, and the one that actually needs making."""
    root = _winner_and_loser(tmp_path)
    programmes.acknowledge(root, "RP1", "Holding against RP2 on purpose")
    assert "superseded-programme" not in codes(root)
    # A third programme appears and out-predicts RP1 too.
    third = claims.add_claim(root, "A third line of thinking entirely", []).id
    spare = claims.add_claim(root, "Its auxiliary", []).id
    programmes.add_programme(root, "A newcomer", [third], [spare], rivals=["RP1"])
    programmes.record_shift(root, "RP3", "Hit", hits=[spare])
    add_fc(root, [f"claim:{third}"])
    opened_on(root, "FC2", "2026-01-05")
    forecast.resolve_forecast(root, "FC2", "yes", note="It held")
    report = programmes.appraise(root, "RP1")[0]
    assert report["outpaced_by"] == ["RP2", "RP3"]
    assert report["acknowledged"] is False  # the old signature does not cover RP3
    assert "superseded-programme" in codes(root)


# ---------------------------------------------------------------- doctor


def test_doctor_flags_a_programme_with_no_core(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    pages.write_page(
        root / "analysis" / "mood.md",
        {"type": "Programme", "id": "RP1", "aliases": ["RP1"], "hard_core": [],
         "protective_belt": ["C1"]},
        "A mood\n",
    )
    assert "empty-core" in codes(root)


def test_doctor_flags_a_core_member_that_is_not_a_claim_and_one_that_is_nothing(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    add_fc(root, [])
    pages.write_page(
        root / "analysis" / "impure.md",
        {"type": "Programme", "id": "RP1", "aliases": ["RP1"],
         "hard_core": ["FC1"], "protective_belt": ["C9"]},
        "Impure\n",
    )
    found = codes(root)
    assert "impure-core" in found  # FC1 exists, but a bet is not a proposition
    assert "dangling-core" in found  # C9 resolves to nothing — legal, counted


def test_doctor_flags_core_belt_overlap(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    pages.write_page(
        root / "analysis" / "both.md",
        {"type": "Programme", "id": "RP1", "aliases": ["RP1"],
         "hard_core": ["C1"], "protective_belt": ["C1"]},
        "Both\n",
    )
    assert "core-belt-overlap" in codes(root)


def test_doctor_flags_shifts_that_travel_backwards_or_into_the_future(tmp_path):
    """A shift's date decides which forecasts count as novel content, so an
    out-of-order shift does not produce a wrong verdict — it produces a
    manufactured one."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "First", hits=["C2"])
    programmes.record_shift(root, "RP1", "Second", hits=["C2"])
    page = find(root, "RP1")
    page.fm["shifts"][0]["at"] = "2026-06-01T00:00:00Z"
    page.fm["shifts"][1]["at"] = "2026-01-01T00:00:00Z"
    pages.write_page(page.path, page.fm, page.body)
    assert codes(root).count("bad-shift-order") == 1
    page = find(root, "RP1")
    page.fm["shifts"][1]["at"] = "2999-01-01T00:00:00Z"
    pages.write_page(page.path, page.fm, page.body)
    assert "bad-shift-order" in codes(root)


def test_doctor_flags_an_anomaly_no_shift_records(tmp_path):
    """A programme that took a hit and never said what absorbed it is either a
    repair nobody wrote down or a programme that quietly shrank."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    claims.set_claim_status(root, "C2", "superseded")
    assert "unshifted-anomaly" in codes(root)
    programmes.record_shift(root, "RP1", "That is what hit it", hits=["C2"])
    assert "unshifted-anomaly" not in codes(root)


def test_doctor_refuses_a_graded_or_scored_programme(tmp_path):
    """The two-object rule, programme side: grades belong to sources and
    claims, probabilities to forecasts, and a programme gets neither."""
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    pages.write_page(
        root / "analysis" / "scored.md",
        {"type": "Programme", "id": "RP1", "aliases": ["RP1"], "hard_core": ["C1"],
         "probability": 0.7, "grade": "A"},
        "Scored\n",
    )
    findings = [f for f in run_doctor(root) if f.code == "two-object"]
    assert len(findings) == 2
    assert all(f.level == "ERROR" for f in findings)


def test_doctor_reframes_under_verified_findings_on_a_hard_core_claim(tmp_path):
    """Nobody has failed to audit a hard core claim, and auditing is not what
    it is waiting for. The cause line says so, then names the price."""
    root = make_notebook(tmp_path)
    add_claims(root, 2, load_bearing=True)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "Hit", hits=["C2"])
    findings = run_doctor(root)
    assert findings[0].code == "held-by-decision"
    msg = findings[0].message
    assert "C1 form the hard core of RP1" in msg
    assert "held by methodological decision" in msg
    assert "0 novel prediction(s) registered across 1 problemshift(s)" in msg
    # The symptoms stay: the reframe explains them, it does not delete them.
    assert "unaudited-claim" in [f.code for f in findings]


def test_the_reframe_stays_quiet_when_there_is_nothing_to_explain(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)  # not load-bearing: no unaudited-claim to reframe
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    assert "held-by-decision" not in codes(root)


def test_doctor_flags_a_foreign_belief_written_in_the_notebooks_own_voice(tmp_path):
    """A belief kept as data sits beside the evidence rather than inheriting
    its voice. `asserted` on a foreign programme's core is the notebook
    asserting it, not recording that somebody else holds it."""
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Their line", ["C1"], ["C2"], held_by="the movement")
    assert "belief-as-assertion" in codes(root)
    claims.set_claim_status(root, "C1", "unconfirmed")
    assert "belief-as-assertion" not in codes(root)


def test_a_notebooks_own_programme_never_draws_the_belief_finding(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 2)
    programmes.add_programme(root, "Ours", ["C1"], ["C2"])
    assert "belief-as-assertion" not in codes(root)


def test_a_programme_free_notebook_runs_the_check_and_says_nothing(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    assert not [c for c in codes(root) if c.startswith(("empty-core", "degenerating"))]


# ---------------------------------------------------------------- views and CLI


def test_the_view_says_what_the_programme_owes(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    barren(root, "RP1", programmes.BARREN_RUN_FOR_DEGENERATION)
    out = views.programmes_view(root)
    assert "VERDICT: degenerating" in out
    assert "HARD CORE (held by methodological decision, not by evidence)" in out
    assert "ceased to anticipate novel facts" in flat(root)
    assert 'flip forecast add "…" --bears-on claim:C1' in out
    assert max(len(line) for line in out.splitlines()) <= 120


def test_a_shift_is_labelled_by_what_it_bought_never_by_having_accommodated(tmp_path):
    """Correction 3, at the surface. Every theory in the series is added "in
    order to accommodate some anomaly" (1970, p. 33), so "accommodation" names
    the baseline and cannot name the failure. The label says what was bought."""
    root = make_notebook(tmp_path)
    add_claims(root, 3)
    programmes.add_programme(root, "Held", ["C1"], ["C2"])
    programmes.record_shift(root, "RP1", "The paper does not say it", hits=["C2"],
                            absorbed_by=["C3"])
    out = views.programmes_view(root)
    assert "· no novel content ·" in out
    assert "accommodation" not in out
    add_fc(root, ["claim:C1"])
    out = views.programmes_view(root)
    assert "· content-increasing ·" in out
    assert "accommodation" not in out


def test_the_empty_view_teaches_the_object(tmp_path):
    root = make_notebook(tmp_path)
    out = views.programmes_view(root)
    assert "no research programmes declared" in out
    assert "flip programme add" in out


def test_show_programmes_is_exclusive_with_the_other_lanes(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    programmes.add_programme(root, "Held", ["C1"])
    ok = invoke(["--notebook", str(root), "show", "--programmes"])
    assert ok.exit_code == 0 and "RP1" in ok.output
    clash = invoke(["--notebook", str(root), "show", "--programmes", "--claims"])
    assert clash.exit_code != 0
    assert "--claims/--stale/--forecasts/--programmes" in str(clash.output) + str(clash.exception)


def test_cli_round_trip(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 4)
    nb = ["--notebook", str(root)]
    add = invoke([*nb, "programme", "add", "The difficulty is relational",
                  "--hard-core", "C1", "--belt", "C2"])
    assert add.exit_code == 0, add.output
    assert "RP1 pursued · held by self · core: C1 · belt: C2" in add.output
    assert invoke([*nb, "programme", "belt", "RP1", "C3"]).exit_code == 0
    shift = invoke([*nb, "programme", "shift", "RP1", "The paper does not say it",
                    "--hits", "C2", "--absorbed-by", "C4"])
    assert shift.exit_code == 0 and "hits C2 · absorbed by C4" in shift.output
    listed = invoke([*nb, "programme", "list"])
    assert "RP1 · pursued · held by self · core: C1 · belt: 3 · shifts: 1" in listed.output
    # One barren shift is not yet a verdict.
    appraised = invoke([*nb, "programme", "appraise", "RP1"])
    assert appraised.exit_code == 0 and "VERDICT: unappraised" in appraised.output
    early = invoke([*nb, "programme", "acknowledge", "RP1", "--note", "Too soon"])
    assert early.exit_code != 0
    for i in range(programmes.BARREN_RUN_FOR_DEGENERATION - 1):
        assert invoke([*nb, "programme", "shift", "RP1", f"Nothing again {i}"]).exit_code == 0
    data = json.loads(invoke([*nb, "programme", "appraise", "--json"]).output)
    assert data["programmes"][0]["verdict"] == "degenerating"
    assert data["programmes"][0]["shifts"][0]["absorbed_by"] == ["C4"]
    assert data["programmes"][0]["outpaced_by"] == []
    ack = invoke([*nb, "programme", "acknowledge", "RP1", "--note", "Holding on purpose"])
    assert ack.exit_code == 0 and "degenerating acknowledged at 3 problemshift(s)" in ack.output


def test_appraise_refuses_an_unknown_programme_with_the_known_list(tmp_path):
    root = make_notebook(tmp_path)
    add_claims(root, 1)
    programmes.add_programme(root, "Held", ["C1"])
    out = invoke(["--notebook", str(root), "programme", "appraise", "RP9"])
    assert out.exit_code != 0
    assert "known: RP1" in str(out.output) + str(out.exception)


def test_programme_list_is_empty_and_says_so(tmp_path):
    root = make_notebook(tmp_path)
    out = invoke(["--notebook", str(root), "programme", "list"])
    assert out.exit_code == 0 and "no research programmes declared" in out.output
