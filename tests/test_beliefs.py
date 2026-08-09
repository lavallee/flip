"""Tests for flip.beliefs — the Belief class (SPEC §7.1).

The thing under test is a separation, so most of these tests are about what
does NOT happen: a belief that never corroborates the claim it is about, a
measurement that is graded without any of it reaching the proposition, a
stance that moves without the belief record moving, and a status vocabulary
that cannot express a verdict on the world.

The case the class was built from is real. A notebook superseded four claims
after reading their sources — every one a citation failure, a proposition
attributed to a paper that does not contain it — while its actual central
hypothesis had never been tested by anything. flip's vocabulary flattened
"cited a paper that doesn't say this" and "nobody has ever tested this" into
one undifferentiated non-verified state, and the flattening made a citation
problem read as a hypothesis problem. The `working` belief with stance
`unexamined` is the record that was missing, and `test_the_muse_case_*` are
that case end to end.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from flip import beliefs, claims, forecast, pages, scaffold, sources, views
from flip.cli import main
from flip.doctor import CHECK_CODES, run_doctor


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep every test away from the real ~/.flip and the host's git identity."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def make_notebook(tmp_path, kind: str = "scout", slug: str = "demo"):
    return scaffold.create_notebook(tmp_path / slug, slug, kind)


def add_source(root, source_id: str, independence: str = "independent", basis="measured"):
    """A judged references/ page, written directly — capture is exercised
    elsewhere, and what these tests need is the judgment behind a survey."""
    fm = {
        "type": "Source",
        "id": source_id,
        "aliases": [source_id],
        "title": f"Instrument {source_id}",
        "independence": independence,
        "support": {"basis": basis, "method": "stated"},
        "status": "captured",
    }
    pages.write_page(root / "references" / f"{source_id.lower()}.md", fm, "body\n")
    return fm


ATTRIBUTED = {
    "holders": "school board members in the county",
    "function": "Explains a budget vote they already made, without requiring "
                "anyone to have been wrong.",
}
WORKING = {
    "falsified_by": "A matched-perplexity reader study showing no difference.",
}


def add_belief(root, text="Test scores fell after the 2019 reform", **kw):
    kind = kw.pop("belief_kind", "attributed")
    args = dict(ATTRIBUTED if kind == "attributed" else WORKING)
    args.update(kw)
    return beliefs.add_belief(root, text, kind, **args)


# --- the two axes the class exists to keep apart ---------------------------------


def test_a_belief_records_holders_and_never_the_truth_of_what_is_held(tmp_path):
    """The core insight, as a page: "38% of X hold P" is a fact about X. The
    frontmatter carries the holders, the proposition, and the notebook's stance
    on the proposition — and carries no key that could be read as a verdict on
    it."""
    root = make_notebook(tmp_path)
    page = add_belief(root)
    assert page.fm["type"] == "Belief"
    assert page.id == "B1"
    assert page.fm["holders"] == "school board members in the county"
    assert page.fm["stance"] == "unexamined"  # the honest default
    assert page.fm["status"] == "active"
    # None of the claim/forecast judgment vocabulary appears anywhere.
    for forbidden in ("independent_corroboration", "load_bearing", "grade",
                      "probability", "verified", "sources"):
        assert forbidden not in page.fm


def test_stance_and_status_are_different_questions(tmp_path):
    """A belief the record contradicts is not a retracted belief. Moving the
    stance leaves the record of the believing exactly where it was — which is
    the whole point: if people define situations as real, they are real in
    their consequences, so a belief the evidence cuts against is a live cause
    and worth more custody than one nobody acts on, not less."""
    root = make_notebook(tmp_path)
    page = add_belief(root)
    moved = beliefs.set_stance(root, page.id, "contradicted", note="the data says otherwise")
    assert moved.fm["stance"] == "contradicted"
    assert moved.fm["status"] == "active"  # untouched
    assert [r["stance"] for r in moved.fm["stance_history"]] == ["unexamined", "contradicted"]
    assert "## Stance → contradicted" in moved.body
    assert "the data says otherwise" in moved.body


def test_the_status_vocabulary_cannot_express_a_verdict_on_the_world(tmp_path):
    """`verified`, `false-positive` and `superseded` are claim statuses, and
    the refusal says so rather than listing three legal values and leaving the
    operator to guess why theirs is missing."""
    root = make_notebook(tmp_path)
    page = add_belief(root)
    for attempted in ("verified", "false-positive", "superseded"):
        with pytest.raises(SystemExit) as e:
            beliefs.set_status(root, page.id, attempted)
        message = str(e.value)
        assert "active, dormant, retracted" in message
        assert "verdicts on a proposition" in message
        assert "flip belief stance" in message


def test_retraction_needs_a_note_because_of_what_it_could_be_misread_as(tmp_path):
    """Retraction is the only belief status that asserts an error, and the
    error is in our record of the believing. Without a note it reads, to the
    next person, as the proposition having been disproved."""
    root = make_notebook(tmp_path)
    page = add_belief(root)
    with pytest.raises(SystemExit) as e:
        beliefs.set_status(root, page.id, "retracted")
    assert "record of the BELIEVING" in str(e.value)
    ok = beliefs.set_status(root, page.id, "retracted", note="wrong population; it was the PTA")
    assert ok.fm["status"] == "retracted"
    assert ok.fm["status_history"][-1]["note"].startswith("wrong population")


# --- each kind owes one field, and the fields point opposite ways ----------------


def test_an_attributed_belief_must_name_its_function(tmp_path):
    """Prevalence sizes the room; function is the field an intervention is
    built from. The refusal states the reason — on identity-loaded topics
    better-informed holders are frequently more polarized, so "they lack the
    facts" is the one explanation that reliably fails."""
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as e:
        beliefs.add_belief(root, "P", "attributed", holders="someone")
    message = str(e.value)
    assert "--function" in message
    assert "more polarized" in message


def test_a_working_belief_must_name_its_falsifier(tmp_path):
    """Holding a hypothesis here costs nothing — it corroborates nothing and
    gates nothing — which is exactly why the falsifier is the price of
    admission."""
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as e:
        beliefs.add_belief(root, "P", "working")
    assert "--falsified-by" in str(e.value)
    assert "commitment wearing a hypothesis's clothes" in str(e.value)


def test_a_falsifier_on_an_attributed_belief_is_refused(tmp_path):
    """A falsifier is what would make US drop a belief, and we are not the ones
    holding an attributed one. The refusal names both honest alternatives."""
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as e:
        beliefs.add_belief(root, "P", "attributed", holders="them", function="f",
                           falsified_by="x")
    assert "we are not the ones holding this one" in str(e.value)
    assert "separate `working` belief" in str(e.value)


def test_a_working_belief_defaults_its_holder_to_the_actor(tmp_path):
    """The notebook is holding it; saying so twice is ceremony."""
    root = make_notebook(tmp_path)
    page = add_belief(root, belief_kind="working")
    assert page.fm["holders"] == "human:test"


# --- a belief never corroborates the claim it is about ---------------------------


def test_citing_a_belief_as_a_claim_source_is_refused_before_any_write(tmp_path):
    """The category error in the direction that does damage. Refused on the
    write path so nothing has to be un-done, and the message names the two
    honest moves instead."""
    root = make_notebook(tmp_path)
    add_belief(root)
    with pytest.raises(SystemExit) as e:
        claims.add_claim(root, "Test scores fell after the 2019 reform", ["B1"])
    message = str(e.value)
    assert 'how "many people think X" becomes "X"' in message
    assert "flip belief about B1" in message
    assert not list((root / "claims").glob("test-scores*.md"))  # nothing written


def test_claim_source_add_refuses_a_belief_with_the_right_reason(tmp_path):
    """"unknown source id" would be true and useless here: the id resolves
    perfectly, to a page that must never count as evidence."""
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    add_belief(root)
    claims.add_claim(root, "Scores fell", ["A1"])
    with pytest.raises(SystemExit) as e:
        claims.add_claim_sources(root, "C1", ["B1"])
    assert "that is a belief" in str(e.value)
    assert "no references/ page carries them" not in str(e.value)


def test_a_dangling_belief_shaped_id_stays_a_legal_dangling_citation(tmp_path):
    """Only an id flip can SEE is a belief is refused. `B9` carried by nothing
    is an ordinary dangling cite — legal in OKF, counted by doctor (SPEC §6.1)
    — and refusing it would be flip guessing at a prefix."""
    root = make_notebook(tmp_path)
    page = claims.add_claim(root, "Scores fell", ["B9"])
    assert claims.source_ids(page.fm) == ["B9"]


def test_about_links_the_pair_without_moving_anything(tmp_path):
    """`about` is a pointer and nothing else: the claim keeps its own status,
    its own sources, and its own corroboration count."""
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    claim = claims.add_claim(root, "Test scores fell after the 2019 reform", ["A1"])
    belief = add_belief(root)
    linked = beliefs.link_about(root, belief.id, claim.id)
    assert linked.fm["about"] == "C1"
    after = next(c for c in claims.list_claims(root) if c["id"] == "C1")
    assert after["status"] == "asserted"
    assert after["independent_corroboration"] == 1  # unchanged by the link
    # and the pointer lands where a reader meets it, not below the history
    keys = list(linked.fm)
    assert keys.index("about") < keys.index("stance")


def test_about_must_point_at_a_claim(tmp_path):
    """Pointing one belief at another records the same side twice and leaves
    the proposition unstated."""
    root = make_notebook(tmp_path)
    add_belief(root)
    add_belief(root, "Another thing entirely")
    with pytest.raises(SystemExit) as e:
        beliefs.link_about(root, "B1", "B2")
    assert "records the same side twice" in str(e.value)
    with pytest.raises(SystemExit) as e:
        beliefs.link_about(root, "B1", "C7")
    assert "the proposition's world-side lives in claims/" in str(e.value)


# --- the measurement is graded; the proposition is not ---------------------------


def test_a_measurement_is_counted_by_the_claim_bar_and_nothing_else(tmp_path):
    """A survey is a source like any other: captured, graded, and counted by
    claims.corroboration_count — the one shared implementation. What it
    corroborates is that people hold the proposition."""
    root = make_notebook(tmp_path)
    add_source(root, "A1", independence="independent")
    add_source(root, "A2", independence="self-reported")
    belief = add_belief(root)
    page, uncountable = beliefs.measure_belief(
        root, belief.id, "38%", of="county residents", as_of="2025-06",
        sources=["A1", "A2"],
    )
    assert page.fm["measurement_corroboration"] == 1  # A2 is not independent
    assert uncountable == []
    assert page.fm["measurements"][0]["value"] == "38%"
    # The key is named apart from the claim's on purpose.
    assert "independent_corroboration" not in page.fm


def test_the_uncountable_companion_rides_with_every_count(tmp_path):
    """A wrong number is worse than a missing one — only the missing one
    prompts a look (SPEC §5.4). A source still carrying pre-0.8 independence
    vocabulary is named alongside the count it silently dropped out of."""
    root = make_notebook(tmp_path)
    add_source(root, "A1", independence="original")  # pre-0.8 spelling
    belief = add_belief(root)
    _page, uncountable = beliefs.measure_belief(root, belief.id, "38%", sources=["A1"])
    assert uncountable == ["A1"]
    result = invoke(["--notebook", str(root), "belief", "measure", "B1",
                     "--value", "40%", "--source", "A1"])
    assert result.exit_code == 0
    assert "could not be counted either way" in result.output


def test_a_measurement_with_no_source_is_refused(tmp_path):
    """A prevalence number with nothing behind it is a number someone
    remembered, and `belief measure` is not a place to invent a dangling
    citation."""
    root = make_notebook(tmp_path)
    belief = add_belief(root)
    with pytest.raises(SystemExit) as e:
        beliefs.measure_belief(root, belief.id, "38%", sources=[])
    assert "a number someone remembered" in str(e.value)
    with pytest.raises(SystemExit) as e:
        beliefs.measure_belief(root, belief.id, "38%", sources=["A9"])
    assert "capture the measurement with `flip add-source`" in str(e.value)


def test_the_measurement_value_stays_a_string(tmp_path):
    """Same rule as a claim's `value`: an integer n silently masquerades as the
    base, and "3 of 11 board members" is a legal measurement."""
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    belief = add_belief(root)
    page, _ = beliefs.measure_belief(root, belief.id, "3 of 11 board members",
                                     sources=["A1"])
    assert page.fm["measurements"][0]["value"] == "3 of 11 board members"


# --- doctor ---------------------------------------------------------------------


def codes(root) -> list[str]:
    return [f.code for f in run_doctor(root)]


def test_every_belief_check_code_is_registered(tmp_path):
    """The check registry is a documented API disciplines reference by code
    (SPEC §6). A code doctor can emit that the registry doesn't know is a code
    no discipline can gate on."""
    for code in ("belief-as-evidence", "belief-two-object", "unfunctioned-belief",
                 "unfalsifiable-belief", "unmeasured-prevalence", "measurement-drift",
                 "dangling-about", "impure-about", "untested-belief"):
        assert code in CHECK_CODES


def test_doctor_catches_a_belief_cited_as_evidence_by_hand(tmp_path):
    """The write paths refuse it, so reaching doctor means it was written by
    hand or by another tool — which is the case doctor exists for."""
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    claim = claims.add_claim(root, "Scores fell", ["A1"])
    add_belief(root)
    claim.fm["sources"] = [{"id": "A1"}, {"id": "B1"}]
    pages.write_page(claim.path, claim.fm, claim.body)
    findings = [f for f in run_doctor(root) if f.code == "belief-as-evidence"]
    assert len(findings) == 1
    assert findings[0].level == "ERROR"
    assert "flip claim source rm C1 B1" in findings[0].message


def test_doctor_keeps_judgment_vocabulary_off_belief_pages(tmp_path):
    """The two-object rule with a third column. Every one of these keys says
    the same wrong thing — that the page's proposition has been weighed here."""
    root = make_notebook(tmp_path)
    page = add_belief(root)
    page.fm["grade"] = "A"
    page.fm["probability"] = 0.7
    page.fm["independent_corroboration"] = 2
    pages.write_page(page.path, page.fm, page.body)
    found = [f for f in run_doctor(root) if f.code == "belief-two-object"]
    assert {f.level for f in found} == {"ERROR"}
    assert len(found) == 3
    assert any("`measurement_corroboration`" in f.message for f in found)


def test_doctor_names_the_field_each_kind_owes(tmp_path):
    root = make_notebook(tmp_path)
    attributed = add_belief(root)
    attributed.fm.pop("function")
    pages.write_page(attributed.path, attributed.fm, attributed.body)
    working = add_belief(root, "A held thing", belief_kind="working")
    working.fm.pop("falsified_by")
    pages.write_page(working.path, working.fm, working.body)
    found = codes(root)
    assert "unfunctioned-belief" in found
    assert "unfalsifiable-belief" in found


def test_doctor_names_an_untested_working_belief_without_calling_it_broken(tmp_path):
    """The finding a live hypothesis needs and a claim status could never give
    it: held, unexamined, and with nothing in the notebook that would ever move
    it. A WARN, because the state is legal and is the point of the class — it
    is also the state a hypothesis quietly dies in."""
    root = make_notebook(tmp_path)
    add_belief(root, "The relational account is right", belief_kind="working")
    found = [f for f in run_doctor(root) if f.code == "untested-belief"]
    assert len(found) == 1
    assert found[0].level == "WARN"
    assert "nothing in this notebook would ever move it" in found[0].message
    # Naming where the evidence would land silences it.
    claims.add_claim(root, "The relational account is right", [])
    beliefs.link_about(root, "B1", "C1")
    assert "untested-belief" not in codes(root)


def test_a_forecast_can_bear_on_a_belief_and_that_counts_as_a_test(tmp_path):
    """"Will prevalence exceed 40% by 2028" is a bet about believers,
    resolvable on a survey — the one honest way a forecast reaches a belief
    without anything counting toward the proposition."""
    root = make_notebook(tmp_path)
    add_belief(root, "The reform worked", belief_kind="working")
    forecast.add_forecast(
        root, "Will a replication report a null?", "2199-01-01", ["journals"],
        "The study is retracted", 0.4, 0.5, bears_on=["belief:B1"],
    )
    found = codes(root)
    assert "untested-belief" not in found
    assert "dangling-bears-on" not in found
    assert "untyped-ref" not in found


def test_doctor_recomputes_measurement_corroboration(tmp_path):
    """Computed, never hand-set — exactly like a claim's, and flagged the same
    way when the stored number drifts."""
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    belief = add_belief(root)
    page, _ = beliefs.measure_belief(root, belief.id, "38%", sources=["A1"])
    page.fm["measurement_corroboration"] = 7
    pages.write_page(page.path, page.fm, page.body)
    found = [f for f in run_doctor(root) if f.code == "measurement-drift"]
    assert len(found) == 1
    assert "stored measurement_corroboration 7 != recomputed 1" in found[0].message


def test_doctor_explains_a_zero_rather_than_leaving_it_standing(tmp_path):
    """Zero for "nobody has judged these yet" and zero for "the population is
    the only witness to its own beliefs" are different situations with
    different fixes, and the second is often the honest ceiling."""
    root = make_notebook(tmp_path)
    add_source(root, "A1", independence="self-reported")
    belief = add_belief(root)
    beliefs.measure_belief(root, belief.id, "38%", sources=["A1"])
    found = [f for f in run_doctor(root) if f.code == "unmeasured-prevalence"]
    assert len(found) == 1
    assert "the honest ceiling" in found[0].message
    assert "never about the proposition" in found[0].message


def test_doctor_checks_the_about_pointer_both_ways(tmp_path):
    root = make_notebook(tmp_path)
    page = add_belief(root)
    page.fm["about"] = "C9"
    pages.write_page(page.path, page.fm, page.body)
    assert "dangling-about" in codes(root)
    page.fm["about"] = "B1"
    pages.write_page(page.path, page.fm, page.body)
    found = [f for f in run_doctor(root) if f.code == "impure-about"]
    assert found and found[0].level == "ERROR"


def test_belief_ids_share_the_one_allocator(tmp_path):
    """B# is disjoint from every other prefix, allocated through
    pages.allocate_id, and never reused — deleting the page does not free it
    (SPEC §9)."""
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    claims.add_claim(root, "Scores fell", ["A1"])
    first = add_belief(root)
    assert first.id == "B1"
    first.path.unlink()
    second = add_belief(root, "Something else")
    assert second.id == "B2"
    assert pages.PREFIX_DIR["B"] == "beliefs"
    assert "beliefs" in pages.ENTITY_DIRS


# --- surfaces -------------------------------------------------------------------


def test_the_view_shows_the_belief_and_the_record_side_by_side(tmp_path):
    """Holding both things is worth nothing if no view ever shows them
    together."""
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    claims.add_claim(root, "Test scores fell after the 2019 reform", ["A1"])
    belief = add_belief(root)
    beliefs.link_about(root, belief.id, "C1")
    beliefs.set_stance(root, belief.id, "contradicted", because=["C1"])
    out = views.beliefs_view(root)
    assert "stance contradicted" in out
    assert "C1 is asserted" in out
    assert "nothing above corroborates the proposition it states" in out
    data = views.beliefs_view(root, as_data=True)
    assert data["beliefs"][0]["about_status"] == "asserted"


def test_the_cli_surface_end_to_end(tmp_path):
    root = make_notebook(tmp_path)
    add_source(root, "A1")
    nb = ["--notebook", str(root)]
    assert invoke(nb + ["belief", "add", "Scores fell", "--kind", "attributed",
                        "--holders", "the board", "--function", "explains the vote"]
                  ).exit_code == 0
    assert invoke(nb + ["belief", "measure", "B1", "--value", "38%",
                        "--source", "A1"]).exit_code == 0
    stance = invoke(nb + ["belief", "stance", "B1", "contradicted"])
    assert stance.exit_code == 0
    assert "the believing is unchanged" in stance.output
    listed = invoke(nb + ["belief", "list", "--json"])
    rows = json.loads(listed.output)
    assert rows[0]["stance"] == "contradicted"
    assert rows[0]["measurement_corroboration"] == 1
    shown = invoke(nb + ["show", "--beliefs"])
    assert "ATTRIBUTED" in shown.output
    clash = invoke(nb + ["show", "--beliefs", "--claims"])
    assert clash.exit_code != 0


def test_beliefs_appear_in_the_generated_listings(tmp_path):
    root = make_notebook(tmp_path)
    add_belief(root)
    assert "# Beliefs" in (root / "beliefs" / "index.md").read_text()
    assert "[Beliefs](beliefs/)" in (root / "index.md").read_text()


# --- the case the class was built from ------------------------------------------


def test_the_muse_case_separates_a_citation_failure_from_an_untested_thesis(tmp_path):
    """End to end, on the real shape.

    A claim superseded because its source did not contain the proposition, and
    a central hypothesis nothing has tested, are two different records with two
    different next actions — and under the old vocabulary they were both
    "not verified". Here the first stays a Claim and keeps `superseded`
    (correct: the citation failed); the second becomes a `working` Belief at
    stance `unexamined` (correct: nobody has looked), and doctor's advice
    differs accordingly.
    """
    root = make_notebook(tmp_path, kind="pursuit", slug="muse-shaped")
    add_source(root, "P1", independence="independent")
    misattributed = claims.add_claim(
        root,
        "Machine-generated text sits in a lower-perplexity region than human text",
        ["P1"],
        notes="The word 'perplexity' appears zero times in P1.",
    )
    claims.set_claim_status(root, misattributed.id, "superseded")

    thesis = beliefs.add_belief(
        root,
        "Reading model prose runs the intention-attribution query and returns null",
        "working",
        falsified_by="Readers rating authored and generated passages matched for "
                     "perplexity, where the relational account predicts a difference.",
    )
    assert thesis.fm["stance"] == "unexamined"
    assert thesis.fm["status"] == "active"

    found = {f.code: f for f in run_doctor(root)}
    # The citation failure is settled and silent; the untested thesis is named.
    assert "untested-belief" in found
    assert found["untested-belief"].path.startswith("beliefs/")
    assert "belief-as-evidence" not in found
    # Neither record borrowed anything from the other.
    assert claims.list_claims(root)[0]["status"] == "superseded"
    assert beliefs.list_beliefs(root)[0]["stance"] == "unexamined"


def test_a_belief_later_supported_is_still_a_belief(tmp_path):
    """Nothing happens to the belief. The proposition gets verified through the
    ordinary machinery on its own Claim, the stance moves to `supported`, and
    the record of who believed it — and when, and why it worked for them —
    stays exactly as it was. A belief that turns out true is still a belief;
    there is no promotion path, and adding one would be the category error
    running the other way."""
    root = make_notebook(tmp_path)
    add_source(root, "A1", independence="independent")
    add_source(root, "A2", independence="independent")
    claim = claims.add_claim(root, "Test scores fell after the 2019 reform",
                             ["A1", "A2"])
    belief = add_belief(root)
    beliefs.link_about(root, belief.id, claim.id)
    claims.set_claim_status(root, claim.id, "verified")
    moved = beliefs.set_stance(root, belief.id, "supported", because=[claim.id])
    assert moved.fm["stance"] == "supported"
    assert moved.fm["status"] == "active"
    assert moved.fm["belief_kind"] == "attributed"
    assert moved.fm["holders"] == "school board members in the county"
    assert not hasattr(beliefs, "promote_belief")
    row = views.beliefs_view(root, as_data=True)["beliefs"][0]
    assert (row["stance"], row["about_status"]) == ("supported", "verified")


def test_a_stance_change_must_point_at_something_reachable(tmp_path):
    """A stance change with an unreachable reason is the one most worth
    auditing later."""
    root = make_notebook(tmp_path)
    belief = add_belief(root)
    with pytest.raises(SystemExit) as e:
        beliefs.set_stance(root, belief.id, "contradicted", because=["C9"])
    assert "resolves to no page in this notebook" in str(e.value)
    ok = beliefs.set_stance(root, belief.id, "contradicted",
                            note="reasoned from the county budget, not a page")
    assert ok.fm["stance_history"][-1]["note"].startswith("reasoned")


def test_grading_reaches_the_measurement_and_stops_there(tmp_path):
    """The seam, stated as an assertion: upgrading the survey behind a belief
    moves the belief's measurement count and moves nothing about the claim the
    belief is about."""
    root = make_notebook(tmp_path)
    fm = add_source(root, "A1", independence="self-reported")
    claim = claims.add_claim(root, "Test scores fell after the 2019 reform", [])
    belief = add_belief(root)
    beliefs.link_about(root, belief.id, claim.id)
    beliefs.measure_belief(root, belief.id, "38%", sources=["A1"])
    before = next(c for c in claims.list_claims(root) if c["id"] == "C1")

    fm["independence"] = "independent"
    pages.write_page(root / "references" / "a1.md", fm, "body\n")
    assert sources.derive_grade(fm) == "A"
    after_belief = beliefs.list_beliefs(root)[0]
    recomputed = beliefs.measurement_corroboration([fm], after_belief)
    assert recomputed == 1
    after_claim = next(c for c in claims.list_claims(root) if c["id"] == "C1")
    assert after_claim["independent_corroboration"] == before["independent_corroboration"] == 0
