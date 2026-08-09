"""Tests for flip.stance — the attitude axis and the test record (SPEC §7.1).

These tests are about a distinction, not a feature. flip's `status` fuses two
questions — what has been asked of a claim, and what the notebook does with it
— and the cost of the fusion is that a claim whose cited paper turns out not to
contain it renders exactly like a claim nobody has ever tested. The tests below
are written to fail if that fusion ever comes back: the two situations must
derive different words, the words must be computed rather than stored, and
holding a position ahead of the evidence must cost a written way to be shown
wrong.

Several tests here were rewritten when the design was audited against its own
citations. Where that happened the test says what it used to assert and why the
old assertion was wrong, because a test amended without its reason is
indistinguishable from a test weakened to make a build pass. The four
corrections, each with the sentence that forced it:

- `untested` and `weakly-tested` were two rungs of a gradient attributed to
  Mayo. She has no gradient: SIST p.5 puts "nothing has been done to rule out
  ways the claim may be false" and a method that "had little or no capability
  of finding flaws with C even if they exist" into one verdict, bad evidence,
  no test. One word now: `bent`.
- An unrecorded severity rendered as the neutral-sounding `untested`. SIST
  p.201: "if it cannot be computed, it's also awful… I'll say it's low, along
  with an explanation as to why." Bad, with its reason attached.
- Severity was computed without reading the specified error, and the capability
  condition was one-directional. SIST p.65: "if false in a specified manner."
  SIST p.16: "a very high capability of signaling the error, if and only if it
  is present."
- `unexamined-position` fired on `holding` only, so switching to `pursuing`
  silenced it — and `pursuing` was a terminal state with no tests on record.
  The design had an incentive gradient pointing at its own blind spot.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import claims, doctor, pages, stance
from flip.cli import main

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: t
kind: scout
status: {status}
created: 2020-01-01
updated: 2020-01-01
---
# t
"""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    (tmp_path / "index.md").write_text(MANIFEST_MD.format(status="active"), encoding="utf-8")
    src = {
        "type": "Source", "id": "P1", "aliases": ["P1"], "title": "the paper",
        "local": "sources/raw/P1.pdf", "grade": "A", "status": "captured",
        "independence": "independent", "freshness": "fresh",
        "support": {"basis": "measured", "method": "one line"},
    }
    pages.write_page(tmp_path / "references" / "paper.md", src, "# the paper\n")
    pages.write_page(
        tmp_path / "references" / "second.md",
        {**src, "id": "P2", "aliases": ["P2"], "title": "another paper"},
        "# another paper\n",
    )
    return tmp_path.resolve()


def fm_of(root: Path, claim_id: str) -> dict:
    page = pages.find_by_id(root, claim_id)
    assert page is not None
    return page.fm


def severe(probe: str, result: str, against: list[str] | None = None) -> dict:
    """A test record with all four severity conditions satisfied."""
    return {
        "probe": probe,
        "error": "the specific way of being wrong",
        "would_detect": "how it would have shown up",
        "if_absent": "what it would have shown instead, had the error not been there",
        "result": result,
        "against": against or ["P1"],
    }


def run_test(root: Path, claim_id: str, probe: str, result: str, **kw) -> None:
    """Record a severe test through the real write path."""
    claims.record_test(
        root, claim_id, probe, kw.pop("error", "the specific way of being wrong"), result,
        would_detect=kw.pop("would_detect", "how it would have shown up"),
        if_absent=kw.pop("if_absent", "what it would have shown otherwise"),
        against=kw.pop("against", ["P1"]), **kw,
    )


# --- severity: what makes a test worth having survived -------------------------


def test_a_test_is_severe_only_when_it_could_have_caught_the_error():
    # Mayo's requirement in four authored fields: it named the error class
    # (`probe`) and the specific error (`error` — "if false in a specified
    # manner", SIST p.65), it said how the error would have surfaced, it said
    # what the probe would have shown otherwise, and the thing that did the
    # testing is reachable.
    assert stance.test_severity(severe("substance", "survived")) == "severe"
    for missing in ("error", "would_detect", "if_absent"):
        record = {**severe("substance", "survived"), missing: ""}
        assert stance.test_severity(record) == "bent", missing
        assert stance.severity_gaps(record) == [missing]
    assert stance.test_severity({**severe("substance", "survived"), "against": []}) == "bent"
    assert stance.test_severity({**severe("substance", "survived"), "probe": "vibes"}) == "bent"


def test_a_probe_that_fires_either_way_is_not_severe():
    # The correction that added `if_absent`. SIST p.16, Arguing from Error:
    # "a procedure with a very high capability of signaling the error, IF AND
    # ONLY IF it is present". The design used to check only the first half, so
    # "I read the paper carefully and it looked fine" — which is exactly the
    # reading that would also have looked fine had the paper been wrong —
    # earned the same `severe` as a test that could have come out the other
    # way. That was the single most permissive thing in the derivation.
    one_way = {**severe("attribution", "survived")}
    del one_way["if_absent"]
    assert stance.test_severity(one_way) == "bent"
    assert stance.severity_gaps(one_way) == ["if_absent"]


def test_the_failing_verdict_is_bent_not_a_lesser_grade():
    # AMENDED. This used to assert `weak`, on the theory that a test which
    # could have missed the error was a rung below a severe one. Mayo has no
    # such rung — SIST p.5 gives one verdict for both "nothing has been done"
    # and "something was done that could not have found the flaw" — and the
    # softer word was doing real damage, because a gradient invites an
    # operator to feel they are climbing it.
    assert set(stance.SEVERITIES) == {"severe", "bent"}
    assert "weak" not in stance.SEVERITIES
    assert stance.test_severity({}) == "bent"


def test_inconclusive_and_untestable_are_never_severe():
    # A test that could not tell is by definition one that would not reliably
    # have detected the error; `untestable` is a finding about how the claim is
    # posed, not a test of the claim. Neither may ever carry severe's weight.
    assert stance.test_severity(severe("substance", "inconclusive")) == "bent"
    assert stance.test_severity(severe("substance", "untestable")) == "bent"


# --- exposure: the derivation the whole design exists for ----------------------


def test_no_tests_at_all_is_bent_and_not_a_neutral_state():
    # AMENDED, and this is the correction that mattered most. The old
    # assertion was `derive_exposure({}) == "untested"` — a word that reads as
    # "not got to yet" and sat at the bottom of a seven-term ladder, so an
    # unrecorded claim rendered as a neutral floor. SIST p.201: "if it cannot
    # be computed, it's ALSO AWFUL, since the onus on the researcher is to
    # satisfy the minimal requirement for evidence… I'll say it's low, along
    # with an explanation as to why." Bad, with the reason attached — both
    # halves, which is why bent_reason is asserted here and not separately.
    assert stance.derive_exposure({}) == "bent"
    assert stance.derive_exposure({"tests": []}) == "bent"
    assert "untested" not in stance.EXPOSURES
    assert "weakly-tested" not in stance.EXPOSURES
    assert "nothing has been asked of this claim" in stance.bent_reason({})
    assert "worst reading" in stance.bent_reason({})


def test_bent_says_which_road_it_took_in():
    # Three ways to be bent, one verdict, three next actions. The verdict is
    # single because what the claim is WORTH is the same either way; the reason
    # differs because what to do about it does not.
    nothing = {}
    blunt = {"tests": [{**severe("substance", "survived"), "if_absent": ""}]}
    disputed = {"tests": [severe("substance", "failed", ["P1"]),
                          severe("substance", "survived", ["P2"])]}
    assert all(stance.derive_exposure(fm) == "bent" for fm in (nothing, blunt, disputed))
    assert "nothing has been asked" in stance.bent_reason(nothing)
    assert "not one of them would reliably have caught the error" in stance.bent_reason(blunt)
    assert "audit has failed" in stance.bent_reason(disputed)
    assert stance.bent_reason({"tests": [severe("substance", "survived")]}) is None


def test_severe_tests_of_one_probe_disagreeing_is_bent_not_a_middle_state():
    # AMENDED. This used to derive `contested`, a seventh term that read as a
    # stable place to sit — and which an operator pursuing something could sit
    # in indefinitely. Two severe tests of one probe cannot both be right, so
    # at least one is not the test it claims to be, and Mayo is explicit that
    # the readings assume a test "has passed (or would pass) an audit, else
    # these computations go out the window" (SIST p.201). A failed audit is
    # not a reading; it is the absence of one.
    fm = {"tests": [severe("substance", "failed", ["P1"]),
                    severe("substance", "survived", ["P2"])]}
    assert stance.derive_exposure(fm) == "bent"
    assert "contested" not in stance.EXPOSURES


def test_a_failure_from_a_blunt_instrument_is_bent_not_contested():
    # AMENDED for the same reason. A failure recorded by a test that could not
    # have detected the error is not weak evidence against the claim; it is no
    # evidence, in either direction. SIST p.5's "practically guaranteed"
    # sentence is symmetric — a method with little capability of finding flaws
    # tells you nothing whichever way it came out.
    fm = {"tests": [{**severe("substance", "failed"), "would_detect": ""}]}
    assert stance.derive_exposure(fm) == "bent"


def test_a_failed_attribution_test_is_misattributed_not_refuted():
    # The distinction the muse notebook needed and did not have: the claim is
    # wrong about what its source SAYS, which is silent on whether the claim is
    # true. Rendering this as a refutation is the epistemic harm.
    fm = {"tests": [severe("attribution", "failed")]}
    assert stance.derive_exposure(fm) == "misattributed"
    assert stance.failed_attribution_sources(fm) == ["P1"]


def test_a_failed_substance_or_scope_test_is_refuted():
    # AMENDED only by the loss of `derivation`, which was a fourth probe whose
    # failure had no repair of its own — "it does not follow from the inputs"
    # is repaired the way substance is, and an enum value that changes nothing
    # about the next action is a word learned for free.
    for probe in ("substance", "scope"):
        assert stance.derive_exposure({"tests": [severe(probe, "failed")]}) == "refuted"
    assert stance.TEST_PROBES == ("attribution", "substance", "scope")


def test_attribution_and_substance_failing_together_is_the_worse_word():
    # Both are true, and "refuted" is the one a reader must not miss.
    fm = {"tests": [severe("attribution", "failed"), severe("substance", "failed")]}
    assert stance.derive_exposure(fm) == "refuted"


def test_a_failure_on_one_probe_is_not_softened_by_a_survival_on_another():
    # Passing a substance test does not repair a misquotation. The probes are
    # disjoint on purpose and the derivation must keep them that way.
    fm = {"tests": [severe("attribution", "failed"), severe("substance", "survived")]}
    assert stance.derive_exposure(fm) == "misattributed"


def test_a_severe_survival_with_no_failures_is_severely_tested():
    assert stance.derive_exposure({"tests": [severe("substance", "survived")]}) \
        == "severely-tested"


def test_untestable_outranks_bent_but_not_a_severe_survival():
    # A claim something severely tested is testable, whatever an older attempt
    # concluded — otherwise a stale verdict outlives the evidence against it.
    # `untestable` survives the vocabulary cut on Peirce's ground rather than
    # Mayo's: CP 5.197 admits a hypothesis "only insofar as it is capable of
    # experimental verification", so this says the claim as posed does not go
    # on the docket at all, which is a different finding from a bad test.
    assert stance.derive_exposure({"tests": [severe("substance", "untestable")]}) == "untestable"
    fm = {"tests": [severe("substance", "untestable"), severe("substance", "survived")]}
    assert stance.derive_exposure(fm) == "severely-tested"


def test_the_vocabulary_is_five_words():
    # A smaller vocabulary that is faithful beats a larger one that is not.
    # Seven exposure terms went in; five come out, and every removal is a
    # correction rather than a tidy-up.
    assert stance.EXPOSURES == (
        "bent", "severely-tested", "misattributed", "refuted", "untestable",
    )


# --- authored vs derived --------------------------------------------------------


def test_exposure_is_never_written_to_the_page(root: Path):
    claims.add_claim(root, "a claim", ["P1"])
    run_test(root, "C1", "substance", "survived")
    fm = fm_of(root, "C1")
    assert "exposure" not in fm and "severity" not in fm
    assert stance.derive_exposure(fm) == "severely-tested"
    # and it moves when the record moves, which is the point of not storing it
    run_test(root, "C1", "attribution", "failed", error="not in the paper")
    assert stance.derive_exposure(fm_of(root, "C1")) == "misattributed"


def test_stance_and_test_records_are_append_only(root: Path):
    claims.add_claim(root, "a claim", [])
    claims.set_stance(root, "C1", "pursuing", "it explains the residual",
                      falsifier="the attribution experiment comes back null")
    claims.set_stance(root, "C1", "holding", "the experiment ran and it held")
    records = stance.stance_records(fm_of(root, "C1"))
    assert [r["stance"] for r in records] == ["pursuing", "holding"]
    # the current stance is the latest; the earlier one survives as history,
    # because "the notebook used to think otherwise" is usually the story
    assert stance.notebook_stance(fm_of(root, "C1"))["stance"] == "holding"
    assert records[0]["falsifier"]
    assert records[0]["by"] == "agent:test" and records[0]["at"].endswith("Z")


# --- the Peircean price ---------------------------------------------------------


def test_pursuing_without_a_falsifier_is_refused(root: Path):
    claims.add_claim(root, "a claim", [])
    with pytest.raises(SystemExit, match="needs --falsifier"):
        claims.set_stance(root, "C1", "pursuing", "it explains the residual")
    # nothing was written: a refused stance must not leave half a record
    assert "stances" not in fm_of(root, "C1")


def test_the_falsifier_refusal_cites_verifiability_not_economy(root: Path):
    # AMENDED. The refusal used to justify itself as "Peirce's price for the
    # licence to entertain a hypothesis", meaning the economy of research.
    # That is the wrong doctrine and it runs the other way: CP 1.136, the
    # sentence right after "Do not block the way of inquiry", says "there is
    # no positive sin against logic in trying any theory which may come into
    # our heads", and CP 7.220 makes cheapness a reason to give a hypothesis
    # PRECEDENCE. Economy is a sort key; it cannot gate anything. The gate is
    # CP 5.197's verifiability condition, and what it asks for is sharper than
    # "what would move you" — CP 2.89 wants the predictions "otherwise least
    # likely to be true".
    claims.add_claim(root, "a claim", [])
    with pytest.raises(SystemExit) as exc:
        claims.set_stance(root, "C1", "pursuing", "it explains the residual")
    message = str(exc.value)
    assert "CP 5.197" in message and "CP 2.89" in message
    assert "LEAST likely to come out that way if the position were wrong" in message
    assert "econom" not in message.lower()


def test_rejecting_also_costs_a_falsifier(root: Path):
    # The rule against blocking the way of inquiry (CP 1.135) runs in both
    # directions: an unfalsifiable rejection barricades the road exactly as an
    # unfalsifiable belief does.
    claims.add_claim(root, "a claim", [])
    with pytest.raises(SystemExit, match="needs --falsifier"):
        claims.set_stance(root, "C1", "rejecting", "the record contradicts it")


def test_holding_and_abstaining_need_no_falsifier(root: Path):
    # They track the evidence, so the evidence is already their exit; taxing
    # every ordinary claim with a falsifier would just produce ritual ones.
    claims.add_claim(root, "a claim", [])
    claims.set_stance(root, "C1", "holding", "three independent sources agree")
    claims.set_stance(root, "C1", "abstaining", "both readings are live and it does not "
                                                "bear on the decision")
    assert len(stance.stance_records(fm_of(root, "C1"))) == 2


def test_a_stance_always_needs_its_reasoning(root: Path):
    claims.add_claim(root, "a claim", [])
    with pytest.raises(SystemExit, match="needs --because"):
        claims.set_stance(root, "C1", "holding", "   ")


def test_invalid_stance_names_the_axis_it_is_not(root: Path):
    claims.add_claim(root, "a claim", [])
    with pytest.raises(SystemExit, match="invalid stance"):
        claims.set_stance(root, "C1", "verified", "because")


# --- the holder -----------------------------------------------------------------


def test_the_notebook_can_reject_what_someone_else_holds(root: Path):
    # The interesting case, and the one problem (2) needs: a belief that
    # contradicts the evidence, kept as data, with the notebook's own position
    # on the same page and neither overwriting the other.
    claims.add_claim(root, "the election was stolen", ["P1"])
    run_test(root, "C1", "substance", "failed",
             error="no evidence of decisive fraud",
             would_detect="certified counts and court findings",
             if_absent="at least one certified count overturned on audit")
    claims.set_stance(root, "C1", "rejecting", "every audit and court record says otherwise",
                      falsifier="a certified recount overturning a state result")
    claims.set_stance(root, "C1", "holding", "trust in the count collapsed first",
                      holder="a large share of US voters, 2020-", sources=["P2"])
    fm = fm_of(root, "C1")
    assert stance.derive_exposure(fm) == "refuted"
    assert stance.notebook_stance(fm)["stance"] == "rejecting"
    assert [r["holder"] for r in stance.foreign_stances(fm)] == ["a large share of US voters, 2020-"]
    assert stance.unsourced_holders(fm) == []


def test_an_unsourced_holder_is_reported_not_refused(root: Path):
    # "People believe X" is an assertion about people. flip cannot make a
    # free-text holder answerable to anything, so it names the gap rather than
    # blocking the record — the honest half of what it can do.
    claims.add_claim(root, "a claim", [])
    _page, unsourced = claims.set_stance(root, "C1", "holding", "widely repeated",
                                         holder="everyone on the internet")
    assert unsourced == ["everyone on the internet"]


# --- the test write path --------------------------------------------------------


def test_a_test_needs_the_error_it_looked_for(root: Path):
    claims.add_claim(root, "a claim", [])
    with pytest.raises(SystemExit, match="needs --error"):
        claims.record_test(root, "C1", "substance", "  ", "survived")


def test_invalid_probe_and_result_are_refused(root: Path):
    claims.add_claim(root, "a claim", [])
    with pytest.raises(SystemExit, match="invalid probe"):
        claims.record_test(root, "C1", "vibes", "e", "survived")
    with pytest.raises(SystemExit, match="invalid test result"):
        claims.record_test(root, "C1", "substance", "e", "disproven")
    # `derivation` was a probe and is not one now
    with pytest.raises(SystemExit, match="invalid probe"):
        claims.record_test(root, "C1", "derivation", "e", "survived")


def test_a_bent_test_is_still_worth_recording(root: Path):
    # Better a bent test honestly recorded than no record: the exposure says
    # plainly that it would not have caught the error. Refusing the write
    # would only get the four fields filled in with noise, which is worse —
    # flip can see an absent field and cannot see a fabricated one.
    claims.add_claim(root, "a claim", [])
    claims.record_test(root, "C1", "substance", "the error", "survived")
    assert stance.derive_exposure(fm_of(root, "C1")) == "bent"
    assert "not one of them would reliably have caught the error" in stance.bent_reason(fm_of(root, "C1"))


# --- interaction with the verification gate -------------------------------------


def test_verified_is_refused_on_a_misattributed_claim(root: Path):
    # The corroboration bar counts sources and cannot see that somebody went
    # looking for the error and found it — and a plausible citation is exactly
    # what makes a source countable in the first place.
    claims.add_claim(root, "a claim", ["P1", "P2"])
    run_test(root, "C1", "attribution", "failed", error="the word appears zero times")
    with pytest.raises(SystemExit, match="exposure is 'misattributed'"):
        claims.set_claim_status(root, "C1", "verified")
    assert fm_of(root, "C1")["status"] == "asserted"  # refusal writes nothing


def test_the_misattribution_refusal_says_it_is_not_a_verdict_on_truth(root: Path):
    claims.add_claim(root, "a claim", ["P1", "P2"])
    run_test(root, "C1", "attribution", "failed", error="the paper does not say this")
    with pytest.raises(SystemExit) as exc:
        claims.set_claim_status(root, "C1", "verified")
    assert "citation failure, not a verdict on whether the claim is true" in str(exc.value)
    assert "flip claim source rm C1 P1" in str(exc.value)


def test_a_severe_survival_does_not_open_the_gate(root: Path):
    # Tests may only ever close it. A test record is authored by the same hand
    # that authored the claim, so letting one satisfy the bar would let a
    # notebook verify itself by writing a sentence.
    claims.add_claim(root, "a claim", [])
    run_test(root, "C1", "substance", "survived", against=["sessions/x.md"])
    with pytest.raises(SystemExit, match="independent source"):
        claims.set_claim_status(root, "C1", "verified")


# --- letting go is comparative --------------------------------------------------


def test_superseded_cannot_be_reached_without_naming_a_successor(root: Path):
    # AMENDED. This test used to assert that `set_claim_status(C1,
    # "superseded")` simply worked, on the reasoning that superseding a
    # misattributed claim is the right move and must not be blocked by the
    # thing that discovered it. The move is still right; doing it without
    # naming the successor is not. Lakatos, p.69: "a degenerating problemshift
    # is no more a sufficient reason to eliminate a research programme than
    # some old-fashioned 'refutation'… such an objective reason is provided by
    # a rival research programme which explains the previous success of its
    # rival and supersedes it by a further display of heuristic power."
    # Elimination is comparative, so a bare status change records only that the
    # notebook got tired — which is the one reason he says is not a reason.
    claims.add_claim(root, "a claim", ["P1"])
    run_test(root, "C1", "attribution", "failed", error="not in the paper")
    with pytest.raises(SystemExit, match="superseding is comparative"):
        claims.set_claim_status(root, "C1", "superseded")
    assert fm_of(root, "C1")["status"] == "asserted"


def test_superseding_writes_the_pointer_the_rivalry_and_the_status(root: Path):
    claims.add_claim(root, "the broad claim", ["P1"])
    claims.add_claim(root, "the narrower claim that survives", ["P1"])
    run_test(root, "C1", "scope", "failed", error="it overreaches its evidence")
    run_test(root, "C2", "scope", "survived")
    page, note = claims.supersede_claim(
        root, "C1", "C2", "both answer how far the finding carries; C2 survives the scope "
                          "test C1 failed")
    assert page.fm["status"] == "superseded"
    assert stance.superseded_by(fm_of(root, "C1")) == "C2"
    # the rivalry is written to BOTH pages: a comparison only one side can see
    # is not a comparison, and the incumbent is the page anyone worried about
    # the incumbent opens
    assert stance.rival_ids(fm_of(root, "C1")) == ["C2"]
    assert stance.rival_ids(fm_of(root, "C2")) == ["C1"]
    assert note == ""  # the successor is severely tested; nothing to warn about


def test_superseding_by_something_no_better_tested_is_allowed_but_named(root: Path):
    # Lakatos's criterion also requires the successor to explain the
    # predecessor's successes, which flip has no access to — so this is a note
    # and never a refusal. The operator may know something the exposures do not.
    claims.add_claim(root, "the old claim", ["P1"])
    claims.add_claim(root, "the new claim", ["P1"])
    run_test(root, "C1", "substance", "failed", error="the effect is not there")
    _page, note = claims.supersede_claim(root, "C1", "C2", "both answer the same question")
    assert "That is a swap, not yet a supersession" in note
    assert "Lakatos p.69" in note


def test_declaring_rivals_needs_the_question_and_is_symmetric(root: Path):
    claims.add_claim(root, "one answer", [])
    claims.add_claim(root, "another answer", [])
    with pytest.raises(SystemExit, match="needs --because"):
        claims.declare_rivals(root, "C1", "C2", "  ")
    claims.declare_rivals(root, "C1", "C2", "what explains the residual")
    assert stance.rival_ids(fm_of(root, "C1")) == ["C2"]
    assert stance.rival_ids(fm_of(root, "C2")) == ["C1"]
    with pytest.raises(SystemExit, match="already declared rivals"):
        claims.declare_rivals(root, "C2", "C1", "what explains the residual")
    with pytest.raises(SystemExit, match="cannot be its own rival"):
        claims.declare_rivals(root, "C1", "C1", "x")


# --- listing --------------------------------------------------------------------


def test_list_claims_filters_by_exposure_and_stance(root: Path):
    claims.add_claim(root, "untested bet", [])
    claims.add_claim(root, "misquoted", ["P1"])
    claims.set_stance(root, "C1", "pursuing", "it explains the residual",
                      falsifier="the experiment returns null")
    run_test(root, "C2", "attribution", "failed", error="not in the paper")
    assert [c["id"] for c in claims.list_claims(root, exposure="bent")] == ["C1"]
    assert [c["id"] for c in claims.list_claims(root, exposure="misattributed")] == ["C2"]
    assert [c["id"] for c in claims.list_claims(root, stance_value="pursuing")] == ["C1"]
    # the derived word rides along as a view field, never as page state
    assert claims.list_claims(root)[0]["exposure"] == "bent"


def test_list_claims_rejects_unknown_stance_and_exposure(root: Path):
    with pytest.raises(SystemExit, match="invalid stance"):
        claims.list_claims(root, stance_value="believing")
    with pytest.raises(SystemExit, match="invalid exposure"):
        claims.list_claims(root, exposure="untested")


# --- doctor ---------------------------------------------------------------------


NEW_CODES = {"unpriced-stance", "unsourced-holder", "stored-exposure",
             "misattributed-citation", "unexamined-position",
             "losing-to-a-rival", "no-declared-rival"}


def codes(root: Path) -> list[str]:
    return [f.code for f in doctor.run_doctor(root)]


def find(root: Path, code: str) -> doctor.Finding:
    hits = [f for f in doctor.run_doctor(root) if f.code == code]
    assert hits, f"no {code} finding; got {codes(root)}"
    return hits[0]


def test_doctor_is_silent_on_claims_that_use_neither_key(root: Path):
    # The axis is opt-in. A lint that fires because a feature EXISTS teaches
    # operators to tune doctor out, which is how the findings that matter
    # become unreadable.
    claims.add_claim(root, "an ordinary claim", ["P1"], load_bearing=True)
    assert not NEW_CODES & set(codes(root))


def test_doctor_flags_a_stored_exposure(root: Path):
    claims.add_claim(root, "a claim", [])
    page = pages.find_by_id(root, "C1")
    page.fm["tests"] = [severe("substance", "survived")]
    page.fm["exposure"] = "severely-tested"
    pages.write_page(page.path, page.fm, page.body)
    finding = find(root, "stored-exposure")
    assert finding.level == "ERROR" and "DERIVED" in finding.message


def test_doctor_flags_a_hand_edited_unpriced_pursuit(root: Path):
    # flip refuses to write one, so finding one means the page came from
    # somewhere else — which is exactly when a lint earns its keep.
    claims.add_claim(root, "a claim", [], load_bearing=True)
    page = pages.find_by_id(root, "C1")
    page.fm["stances"] = [{"stance": "pursuing", "holder": "notebook", "because": "hunch"}]
    pages.write_page(page.path, page.fm, page.body)
    finding = find(root, "unpriced-stance")
    assert finding.level == "ERROR"  # load-bearing
    assert "what would move you off it" in finding.message


def test_doctor_flags_a_misattributed_claim_still_citing_the_source(root: Path):
    # muse's standing rule as a lint: a source may not be cited for a
    # proposition its own words do not contain.
    claims.add_claim(root, "a claim", ["P1"])
    run_test(root, "C1", "attribution", "failed", error="the word appears zero times")
    finding = find(root, "misattributed-citation")
    assert finding.level == "WARN" and "still cites it" in finding.message
    # unlinking the source is one of the two repairs, and it clears the finding
    claims.remove_claim_source(root, "C1", "P1")
    assert "misattributed-citation" not in codes(root)


def test_a_shipped_misattribution_is_an_error(root: Path):
    # While the notebook is active this is work in progress; once it is
    # published it is a claim a reader can neither see through nor forgive.
    claims.add_claim(root, "a claim", ["P1"])
    run_test(root, "C1", "attribution", "failed", error="not in the paper")
    (root / "index.md").write_text(MANIFEST_MD.format(status="published"), encoding="utf-8")
    assert find(root, "misattributed-citation").level == "ERROR"


def test_switching_to_pursuing_no_longer_silences_the_unexamined_warning(root: Path):
    # AMENDED, and this is correction 5. The old test asserted the opposite —
    # that moving from `holding` to `pursuing` CLEARED `unexamined-position` —
    # and it passed, which is how the design came to certify its own worst
    # incentive: `pursuing` was doctor-clean with zero tests on record, it was
    # terminal (nothing pointed out of it), and switching into it was the
    # documented way to silence the notebook's only warning about untested
    # belief. A gradient ran downhill toward the one state nothing could reach.
    #
    # Now the finding is about the CLAIM's exposure, not the stance word. Both
    # positions fire it, the wording of the advice differs, and the only exit
    # is the one the design actually wants: ask the claim something.
    claims.add_claim(root, "the central bet", [], load_bearing=True)
    claims.set_stance(root, "C1", "holding", "it is the only account that fits")
    assert "Holding is a defended position" in find(root, "unexamined-position").message

    claims.set_stance(root, "C1", "pursuing", "it is the only account that fits",
                      falsifier="attribution alone fails to move comprehension")
    still = find(root, "unexamined-position")
    assert "pursuing" in still.message
    assert "pursuing one indefinitely without ever getting a reading" in still.message

    # the one exit: a severe test. Any severe test — survived or failed —
    # gives the claim a reading, which is all this finding ever asked for.
    run_test(root, "C1", "substance", "failed", error="the effect is not there")
    assert "unexamined-position" not in codes(root)


def test_the_unexamined_warning_carries_the_reason_the_claim_is_bent(root: Path):
    # SIST p.201 again: low, ALONG WITH AN EXPLANATION AS TO WHY. A badge with
    # no reason is the half of her prescription that is easy to ship.
    claims.add_claim(root, "the central bet", [], load_bearing=True)
    claims.set_stance(root, "C1", "holding", "it is the only account that fits")
    assert "nothing has been asked of this claim" in find(root, "unexamined-position").message
    claims.record_test(root, "C1", "substance", "the effect is not there", "survived")
    assert "not one of them would reliably have caught the error" \
        in find(root, "unexamined-position").message


def test_doctor_names_a_pursued_claim_that_is_losing_to_a_declared_rival(root: Path):
    # Lakatos's criterion as a finding: not "you have been stuck for a while"
    # but "something you named as answering the same question is winning".
    claims.add_claim(root, "the incumbent", ["P1"], load_bearing=True)
    claims.add_claim(root, "the challenger", ["P1"])
    run_test(root, "C1", "substance", "failed", error="the effect is not there")
    run_test(root, "C2", "substance", "survived")
    claims.set_stance(root, "C1", "pursuing", "it still explains the residual",
                      falsifier="a preregistered replication with adequate power")
    assert "losing-to-a-rival" not in codes(root)  # no rivalry declared yet
    claims.declare_rivals(root, "C1", "C2", "what explains the residual")
    finding = find(root, "losing-to-a-rival")
    assert "C2" in finding.message and "severely tested" in finding.message
    assert finding.level == "WARN"  # never an ERROR: flip cannot check the rest of p.69
    assert "flip claim supersede C1 --by C2" in finding.message


def test_doctor_never_fires_the_rival_finding_on_a_timer(root: Path):
    # The whole content of C28: a degenerating run is not itself a reason.
    # A refuted claim with a rival that is ALSO bent gets nothing, however long
    # it sits there, because there is no comparison to report.
    claims.add_claim(root, "the incumbent", ["P1"], load_bearing=True)
    claims.add_claim(root, "the challenger", ["P1"])
    run_test(root, "C1", "substance", "failed", error="the effect is not there")
    claims.set_stance(root, "C1", "pursuing", "it still explains the residual",
                      falsifier="a preregistered replication with adequate power")
    claims.declare_rivals(root, "C1", "C2", "what explains the residual")
    assert "losing-to-a-rival" not in codes(root)


def test_doctor_names_a_pursued_position_with_no_rival_on_record(root: Path):
    # Q3. The honest version: a fact about the record, said as one.
    claims.add_claim(root, "the central bet", ["P1"], load_bearing=True)
    run_test(root, "C1", "substance", "survived")
    claims.set_stance(root, "C1", "pursuing", "it is the only account that fits",
                      falsifier="attribution alone fails to move comprehension")
    finding = find(root, "no-declared-rival")
    assert "a fact about the notebook, not about the world" in finding.message
    assert "no amount of evidence can make C1 lose to anything" in finding.message
    claims.add_claim(root, "the alternative I think is wrong", [])
    claims.declare_rivals(root, "C1", "C2", "what explains the residual")
    assert "no-declared-rival" not in codes(root)


def test_the_no_rival_finding_defers_to_the_nearer_problem(root: Path):
    # A claim nobody has tested has a nearer problem than a claim nobody has a
    # challenger for, and two findings on one line is how a doctor run stops
    # being read.
    claims.add_claim(root, "the central bet", [], load_bearing=True)
    claims.set_stance(root, "C1", "pursuing", "it is the only account that fits",
                      falsifier="attribution alone fails to move comprehension")
    assert "unexamined-position" in codes(root)
    assert "no-declared-rival" not in codes(root)


def test_doctor_names_a_belief_attributed_to_nobody_checkable(root: Path):
    claims.add_claim(root, "a claim", [])
    claims.set_stance(root, "C1", "holding", "widely repeated", holder="the public")
    assert "assertion about them" in find(root, "unsourced-holder").message


def test_doctor_flags_out_of_vocabulary_stance_and_probe(root: Path):
    claims.add_claim(root, "a claim", [])
    page = pages.find_by_id(root, "C1")
    page.fm["stances"] = [{"stance": "believing", "holder": "notebook", "because": "x"}]
    page.fm["tests"] = [{"probe": "vibes", "result": "meh", "error": "e"}]
    pages.write_page(page.path, page.fm, page.body)
    bad = [f for f in doctor.run_doctor(root) if f.code == "bad-enum"]
    assert len(bad) == 3  # stance, probe, result


def test_every_new_code_is_registered():
    for code in NEW_CODES:
        assert code in doctor.CHECK_CODES


# --- CLI ------------------------------------------------------------------------


def invoke(args: list[str], root: Path):
    return CliRunner().invoke(main, ["--notebook", str(root), *args])


def test_cli_round_trip_distinguishes_the_three_situations(root: Path):
    claims.add_claim(root, "wrong about a source", ["P1"])
    claims.add_claim(root, "never tested by anyone", [])
    claims.add_claim(root, "held against contrary evidence", ["P1"])

    assert invoke(["claim", "test", "C1", "--probe", "attribution",
                   "--error", "the word appears zero times",
                   "--would-detect", "reading P1 end to end for the term",
                   "--if-absent", "the term would appear in the abstract at least once",
                   "--against", "P1", "--result", "failed"], root).exit_code == 0
    assert invoke(["claim", "stance", "C2", "pursuing",
                   "--because", "it is the only account that fits the residual",
                   "--falsifier", "randomized attribution fails to move comprehension"],
                  root).exit_code == 0
    assert invoke(["claim", "test", "C3", "--probe", "substance",
                   "--error", "the effect may not replicate",
                   "--result", "failed"], root).exit_code == 0
    assert invoke(["claim", "stance", "C3", "pursuing",
                   "--because", "the failing test used an instrument that could be wrong",
                   "--falsifier", "a preregistered replication with adequate power"],
                  root).exit_code == 0

    out = invoke(["claim", "list"], root).output
    assert "C1 · asserted · wrong about a source · sources: P1 · misattributed" in out
    # AMENDED: C2 used to read `untested/pursuing` and C3 `contested/pursuing`.
    # Both are the same verdict now, and it is the bad one — which is the point.
    assert "C2 · asserted · never tested by anyone · sources: none · bent/pursuing" in out
    assert "held against contrary evidence · sources: P1 · bent/pursuing" in out


def test_cli_exposure_explains_the_derivation(root: Path):
    claims.add_claim(root, "a claim", ["P1"])
    invoke(["claim", "test", "C1", "--probe", "attribution", "--error", "not in the paper",
            "--would-detect", "reading it", "--if-absent", "it would have been on p.4",
            "--against", "P1", "--result", "failed"], root)
    out = invoke(["claim", "exposure", "C1"], root).output
    assert "exposure misattributed (derived, never stored)" in out
    assert "attribution · failed · severe" in out
    assert "silent on whether the proposition is TRUE" in out
    assert "notebook stance: none recorded" in out
    # a refuting exposure with nothing that could have won says so
    assert "rivals: none declared" in out


def test_cli_exposure_on_a_bent_claim_reads_as_bad(root: Path):
    # The rendering correction, end to end: no neutral badge, and the reason
    # travels with the verdict.
    claims.add_claim(root, "nobody has looked", [])
    out = invoke(["claim", "exposure", "C1"], root).output
    assert "exposure bent" in out
    assert "bad evidence, no test" in out
    assert "worst reading this axis has" in out


def test_cli_stance_refusal_teaches_the_price(root: Path):
    claims.add_claim(root, "a claim", [])
    result = invoke(["claim", "stance", "C1", "pursuing", "--because", "it explains a lot"], root)
    assert result.exit_code != 0
    assert "needs --falsifier" in result.output


def test_cli_supersede_round_trip(root: Path):
    claims.add_claim(root, "the broad claim", ["P1"])
    claims.add_claim(root, "the narrower one", ["P1"])
    result = invoke(["claim", "supersede", "C1", "--by", "C2",
                     "--because", "both answer how far the finding carries"], root)
    assert result.exit_code == 0
    assert "C1 → superseded by C2" in result.output
    assert fm_of(root, "C1")["status"] == "superseded"


def test_cli_exposure_on_an_unknown_claim_names_what_exists(root: Path):
    claims.add_claim(root, "a claim", [])
    result = invoke(["claim", "exposure", "C9"], root)
    assert result.exit_code != 0 and "known: C1" in result.output
