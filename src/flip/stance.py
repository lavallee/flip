"""Stance and exposure — the attitude, and the test record (SPEC §7.1).

flip's claim `status` is truth-tracking, and it is right for facts. It cannot
say two things a reporter's notebook needs to say.

**One: it collapses every un-verified claim into the same state.** A claim
whose cited paper turns out not to contain it, and a claim nobody has ever
tested, both sit outside `verified` and read the same on every surface. Those
are not the same situation and they do not have the same next action — one
needs the citation repaired, the other needs an experiment run — and a
notebook that flattens them will read a citation failure as a hypothesis
failure, which is a real epistemic harm and not a cosmetic one.

**Two: it has no room for holding a position the evidence has not reached.**
An operator pursuing an original line of thinking is not asserting a fact and
is not retracting one; they are putting a hypothesis on the docket of cases to
be tried, which is Peirce's abduction (CP 5.602: abduction "commits us to
nothing; it merely causes a hypothesis to be set down upon our docket of cases
to be tried") and is the ordinary way inquiry starts. Nor can the notebook
record that someone *else* believes something the notebook takes to be false —
and a widely-held false belief is a real causal force whose structure points at
interventions, so it is data.

This module makes those two axes first-class and **orthogonal**:

- **Exposure** — what has been asked of the claim, DERIVED from an authored
  record of tests. `misattributed` is not `refuted` is not `bent`.
- **Stance** — what position is taken toward the claim, and BY WHOM. Authored,
  because a position is an act, and acts can only be reported.

They are orthogonal on purpose. A claim can be severely tested and rejected by
the notebook (that is what a documented false belief looks like); a claim can
be bent and pursued (that is what a live hypothesis looks like). Neither
combination is expressible in `status` alone, and both are common.

## What the sources say, and where this design leaves them

Every framework sentence below was read against a captured primary. An earlier
draft of this module cited both authors for positions they do not hold, so the
citations here carry page numbers and the departures are named as departures.

**Mayo has one failing verdict, not a spectrum.** SIST p.5, the weak severity
requirement: *"One does not have evidence for a claim if nothing has been done
to rule out ways the claim may be false. If data x agree with a claim C but the
method used is practically guaranteed to find such agreement, and had little or
no capability of finding flaws with C even if they exist, then we have bad
evidence, no test (BENT)."* Both halves of that sentence land in one word.
An earlier draft of this module ranked `untested` above `weakly-tested` as two
rungs of a gradient and cited her for it; there is no such gradient. `bent` is
the one verdict, and it is her acronym.

**An unrecorded severity grades low, not neutral.** SIST p.201: *"But if it
cannot be computed, it's also awful, since the onus on the researcher is to
satisfy the minimal requirement for evidence… If we cannot compute the severity
even approximately, I'll say it's low, along with an explanation as to why:
It's low because we don't have a clue how to compute it!"* So "nobody recorded
anything" is not a blank waiting to be filled in. It is the worst reading this
axis has, and `explain_exposure` is required to attach the reason — which is
the second half of what she asks for and the half a badge usually drops.

**Severity is relative to a specified error, and the capability condition runs
both ways.** SIST p.65: a severe test is *"a test that C probably would have
failed, if false in a specified manner"* — hence `error` is required and is a
severity input, not documentation. SIST p.16, Arguing from Error: *"There is
evidence an error is absent to the extent that a procedure with a very high
capability of signaling the error, **if and only if** it is present,
nevertheless detects no error."* The "only if" is a second condition and it is
the one an unaided reading always drops: a probe that fires whether or not the
error is there discriminates nothing, however diligently it was run. `tests:`
records both directions (`would_detect`, `if_absent`) and a record missing
either is BENT.

**Peirce's price is verifiability, not economy.** An earlier draft charged a
`falsifier` for `pursuing` and called it the economy of research. That is the
wrong doctrine and it points the wrong way: CP 1.136, the sentence immediately
after "Do not block the way of inquiry", says *"Although it is better to be
methodical in our investigations, and to consider the economics of research,
yet there is no positive sin against logic in trying any theory which may come
into our heads"*, and CP 7.220 makes cheapness a reason to give a hypothesis
*precedence* "even if it be barely admissible for other reasons". Economy is a
sort key. It cannot gate anything. What does gate is CP 5.197: *"Any
hypothesis, therefore, may be admissible, in the absence of any special reasons
to the contrary, provided it be capable of experimental verification, and only
insofar as it is capable of such verification."* And it asks for something
sharper than "what would move you" — CP 2.89: verification *"must consist in
basing upon the hypothesis predictions as to the results of experiments,
especially those of such predictions as appear to be otherwise least likely to
be true"*; CP 1.120: *"The best hypothesis… is the one which can be the most
readily refuted if it is false. This far outweighs the trifling merit of being
likely."*

**The joint result.** Peirce wants the prediction that would be least likely to
come out right if the hypothesis were false. Mayo wants the probe that would
not have signalled if the error were absent. Those are the same condition
approached from opposite ends, arrived at seventy years apart by people with
nothing else in common, and it is the strongest thing the two frameworks
jointly give this tool: **a claim owes an observation that would come out
differently depending on whether it is right.** `falsifier` on a stance is that
observation promised; `if_absent` on a test is that observation delivered.

**Where this departs from both.** (1) The probe taxonomy is flip's, not Mayo's
— she has no notion of an attribution error, because in her setting the claim
and its evidence are the same object. Keeping `attribution` separate is this
module's own contribution and its whole origin. (2) `untestable` as a verdict
is Peirce's admissibility condition (CP 5.197), not Mayo's severity; it says
the claim as posed is not the kind of thing that goes on the docket. (3) flip
checks the *presence* of `error`, `would_detect`, `if_absent` and `against`,
never their truth — no more than it can check `support.method`. A severe test
here means an operator wrote four specific things, and an operator who writes
four plausible lies gets a severe test. That is a real limit and it is stated
in SPEC §7.1 rather than buried.

**Letting go is comparative.** Lakatos, p.69: *"a degenerating problemshift is
no more a sufficient reason to eliminate a research programme than some
old-fashioned 'refutation' or a Kuhnian 'crisis'… such an objective reason is
provided by a rival research programme which explains the previous success of
its rival and supersedes it by a further display of heuristic power."* So
nothing here fires on a timer, and `superseded` is not a status a claim can
reach alone: `rivals:` names what answers the same question, `superseded_by:`
names what won, and doctor compares the two on exposure. Lakatos also requires
that the rival explain the predecessor's successes, which no tool can check —
so the comparison is reported, never enforced.

**Authored vs derived**, since flip's doctrine is that verdicts are derived and
never stored (`derive_grade`, `capture_fidelity`): stance records, test records
and rival records are authored — they describe acts someone performed, the same
way `support.method` describes how evidence was produced. `exposure` and a
test's `severity` are derived — they are what those descriptions add up to, and
they change when the record changes. Neither is written to a page. `flip claim
exposure` prints the derivation the way `flip grade --explain` does, and doctor
errors on a page that stores one.
"""

from __future__ import annotations

from . import pages

# Who holds a stance. `notebook` is reserved: it is the notebook's own
# position, the one every existing surface implicitly assumed was the only
# kind there is. Any other string names someone else, and a stance held by
# someone else is an assertion ABOUT them (see `unsourced_holders`).
NOTEBOOK_HOLDER = "notebook"

# The stance vocabulary (SPEC §7.1). Four values, and the test each has to
# pass to earn a place is the same one flip's other enums pass: it must name a
# situation the others cannot, and it must change what happens next.
#
#   pursuing    the notebook is working FROM this claim ahead of the evidence,
#               because it would explain something. Peirce's docket of cases
#               to be tried (CP 5.602). This is the value the whole module
#               exists for — without it, "unconfirmed but being worked on" has
#               to masquerade as either `asserted` (overclaiming) or
#               `unconfirmed` (which reads as abandoned).
#   holding     the notebook's position: it would defend this and the piece
#               may lean on it. The attitude an ordinary `asserted` claim was
#               always silently assumed to carry — worth spelling now that it
#               is one option among four.
#   abstaining  a position was considered and deliberately not taken. Distinct
#               from carrying no stance at all, which means nobody has
#               decided; the same distinction the capture ledger draws between
#               `not-captured` (looked, found nothing) and no row at all.
#   rejecting   the notebook takes this to be false and keeps it anyway,
#               because someone holds it or because its failure is
#               informative. NOT `status: retracted` — retraction says the
#               notebook withdraws its own assertion, rejection says the
#               claim is a live object in the world that the notebook
#               disbelieves.
STANCES = ("pursuing", "holding", "abstaining", "rejecting")

# The two stances that run ahead of, or against, the evidence — the two that
# cost a falsifier (CP 5.197, 2.89; see the module docstring). `holding` and
# `abstaining` track the evidence and so already have an exit written by the
# evidence itself; these two do not, and an unfalsifiable pursuit and an
# unfalsifiable rejection are the two ways a notebook stops being able to
# learn. Peirce's corollary — do not block the way of inquiry (CP 1.135) —
# is what makes the rejecting half of that rule his and not an invention:
# a rejection with no way back barricades the road exactly as a dogma does.
PRICED_STANCES = ("pursuing", "rejecting")

# What a test PROBES — the class of error it went looking for (SPEC §7.1).
# Three values, and the discipline that keeps it three is that each one has a
# DIFFERENT REPAIR. The fine grain of *which* error lives in the record's
# free-text `error`, which is now a severity input; the enum only has to carry
# what changes the next action.
#
#   attribution  does the cited source actually contain the proposition
#                attributed to it? The only probe runnable without leaving the
#                notebook, and the one that fails most often, because a
#                plausible citation is exactly what nobody re-reads. Repair:
#                fix the citation. Says nothing about the world.
#   substance    is the proposition true of the world? The probe every reader
#                assumes is the one that ran. Repair: the claim is wrong;
#                supersede it.
#   scope        does it hold outside the conditions its evidence covers?
#                Sentence-level evidence carried to document-level conclusions
#                fails here, and calling that a refutation would be wrong —
#                the finding stands, the claim overreached it. Repair: narrow
#                the claim to what the evidence covers.
#
# `derivation` was a fourth value and has been removed. A claim that is true of
# its inputs but does not follow from them is a real failure, but its repair —
# restate the claim so it follows, or supersede it — is `substance`'s repair,
# and an enum value that changes nothing about what happens next is a word the
# operator has to learn for free. The free-text `error` says "it does not
# follow from the inputs" better than an enum slot ever did.
TEST_PROBES = ("attribution", "substance", "scope")

# What a test FOUND. A description of an event, not a verdict on the claim —
# the verdict is `exposure`, derived below.
#
#   survived      the test looked for the error and did not find it.
#   failed        the test found the error.
#   inconclusive  the test ran and could not tell. Never severe: a test that
#                 could not tell is by definition one that would not reliably
#                 have detected the error. It is kept as a distinct result so
#                 that an operator who learned nothing is not forced to write
#                 down `survived`, which is a different and much stronger
#                 sentence.
#   untestable    the attempt concluded the claim AS POSED admits no test.
#                 A finding about the claim's formulation, not about the
#                 world; the repair is to re-pose the claim, not to run
#                 another test. This is Peirce's admissibility condition
#                 (CP 5.197) rather than anything of Mayo's.
TEST_RESULTS = ("survived", "failed", "inconclusive", "untestable")

# What a single test was worth. Two values, and the second one is Mayo's own
# word rather than a softer one, because the softer one was the bug: `weak`
# reads as "a bit less good than severe" and invites a gradient she does not
# have. SIST p.5 puts "nothing was done" and "something was done that could not
# have found the flaw" in the same bucket and names it bad evidence, no test.
SEVERITIES = ("severe", "bent")

# The derived digest of a claim's test record — a summary, never a store.
# Five terms, down from seven; `untested`, `weakly-tested` and `contested` are
# gone, and each removal is a correction rather than a simplification.
#
#   bent             no severe test on record. Nobody looked, or what ran could
#                    not have found the error, or two severe tests of the same
#                    probe contradict each other so the audit itself has
#                    failed. One verdict, because SIST p.5 gives one verdict —
#                    and the WORST reading on this axis, not a neutral floor
#                    (SIST p.201). `explain_exposure` always says which road
#                    into it was taken, because "low, along with an explanation
#                    as to why" is the whole prescription and the explanation
#                    is the half that gets dropped.
#                    (Replaces `untested`, `weakly-tested` and `contested`.)
#   severely-tested  at least one test that would probably have caught the
#                    error, and it didn't. The strongest thing this axis says.
#   misattributed    a severe attribution test failed: the claim is wrong
#                    about what its source says. It says NOTHING about whether
#                    the proposition is true, and conflating the two is the
#                    harm this module was built to stop.
#   refuted          a severe test of substance or scope failed: the claim is
#                    wrong about the world, or about its own reach.
#   untestable       an attempt concluded the claim as posed admits no test.
#                    Not a degree of testedness: a finding that the claim is
#                    not yet the kind of thing that goes on the docket.
EXPOSURES = (
    "bent",
    "severely-tested",
    "misattributed",
    "refuted",
    "untestable",
)

# Which test-record fields decide severity, and which are documentation. The
# same disclosure `GRADE_INPUTS` makes for the letter: discoverable only by
# reading the derivation until it was written down. `error` moved into the
# inputs when the design was corrected against SIST p.65 — severity is always
# severity for a SPECIFIED error, so a test with no error named cannot be
# severe however carefully everything else was filled in.
SEVERITY_INPUTS = ("probe", "result", "error", "would_detect", "if_absent", "against")
SEVERITY_DOCUMENTATION = ("note", "at", "by")


def stance_records(fm: dict) -> list[dict]:
    """Every stance recorded on a claim, in the order they were taken.

    Append-only, like `verified:` — a stance is an act with a date and an
    actor, and overwriting one would erase the fact that the notebook used to
    think otherwise, which is usually the most interesting thing on the page.
    """
    return [r for r in pages.as_list(fm.get("stances")) if isinstance(r, dict)]


def notebook_stance(fm: dict) -> dict | None:
    """The notebook's current stance on a claim — the most recent record whose
    holder is `notebook` — or None when the notebook has taken none.

    None is not `abstaining`: it means nobody has decided, which is the
    ordinary state of most claims and is not a finding.
    """
    own = [r for r in stance_records(fm) if str(r.get("holder", NOTEBOOK_HOLDER)) == NOTEBOOK_HOLDER]
    return own[-1] if own else None


def foreign_stances(fm: dict) -> list[dict]:
    """Stances held by someone other than the notebook, in order.

    This is where a belief the notebook does not share gets recorded as data:
    the holder is named, the `because` carries the belief's own reasoning, and
    `sources` carry the evidence that the holder holds it. The notebook's own
    verdict on the proposition stays where it belongs — in `status`, in the
    grades of the sources, and in `exposure`.
    """
    return [
        r for r in stance_records(fm)
        if str(r.get("holder", NOTEBOOK_HOLDER)) != NOTEBOOK_HOLDER
    ]


def unsourced_holders(fm: dict) -> list[str]:
    """Holders whose CURRENT foreign stance cites nothing to show they hold it.

    "People believe X" is an assertion about people, and flip has no way to
    make a free-text `holder` answerable to anything. Naming the ones with no
    receipt is the honest half of what it can do; the other half is saying so
    in the docs (SPEC §7.1) rather than pretending the field is evidence.

    Only the LAST record per holder counts. The list is append-only, so a
    stance first written without a receipt and later rewritten with one leaves
    both on the page — and reading every record meant the finding could never
    be cleared. It fired on a real notebook after the evidence had been cited,
    naming a defect that had already been fixed and pointing at the exact
    command that had just fixed it. A lint nobody can satisfy is one everybody
    learns to skip. The superseded record still stands on the page, which is
    the point of append-only: it says the notebook once asserted this with
    nothing behind it.
    """
    latest: dict[str, dict] = {}
    for r in foreign_stances(fm):
        latest[str(r.get("holder") or "?")] = r
    return [h for h, r in latest.items() if not pages.as_list(r.get("sources"))]


def unpriced_stances(fm: dict) -> list[dict]:
    """Stance records that owe a falsifier and don't carry one.

    Peirce's verifiability condition, unpaid (CP 5.197). `flip claim stance`
    refuses to write one of these, so finding one means a page was hand-edited
    or arrived from elsewhere — which is exactly when a lint earns its keep.
    """
    return [
        r for r in stance_records(fm)
        if str(r.get("stance")) in PRICED_STANCES and not str(r.get("falsifier") or "").strip()
    ]


def test_records(fm: dict) -> list[dict]:
    """Every test recorded against a claim, in the order they were run.

    Append-only for the same reason `verified:` is: a test that failed and was
    later superseded by a better one is part of the claim's history, and the
    exposure derivation reads the whole list rather than the last row.
    """
    return [r for r in pages.as_list(fm.get("tests")) if isinstance(r, dict)]


def severity_gaps(record: dict) -> list[str]:
    """Which of the four authored severity conditions a test record fails, in
    the order they are asked for. Empty means the test is severe.

    Split out from `test_severity` because Mayo's prescription for an
    uncomputable severity is "low, along with an explanation as to why" (SIST
    p.201) and the explanation has to come from the same place as the verdict,
    or the two drift and only one of them is shown.

    The four conditions, and the sentence each one is:

    - `error` — "a test that C probably would have failed, if false **in a
      specified manner**" (SIST p.65). Severity is always severity for a
      particular way of being wrong; a test with no error named is a reading.
    - `would_detect` — "a procedure with a very high capability of signaling
      the error **if** it is present" (SIST p.16).
    - `if_absent` — "…**and only if** it is present" (SIST p.16). The second
      half, and the one an unaided reading drops: a probe that fires either
      way discriminates nothing. It is also where Peirce arrives from the
      other side, asking for the prediction "otherwise least likely to be
      true" (CP 2.89).
    - `against` — the thing that did the testing has to be locatable, or the
      other three are a description of an experiment nobody can find.
    """
    gaps = []
    if str(record.get("probe")) not in TEST_PROBES:
        gaps.append("probe")
    for field in ("error", "would_detect", "if_absent"):
        if not str(record.get(field) or "").strip():
            gaps.append(field)
    if not pages.as_list(record.get("against")):
        gaps.append("against")
    return gaps


def test_severity(record: dict) -> str:
    """How much a single test would have told us — `severe` or `bent`,
    DERIVED from the record, never stored.

    Severe means all four of `severity_gaps`' conditions hold and the test
    actually reached a verdict (`survived` or `failed`). Everything else is
    `bent` — Mayo's word, "bad evidence, no test" (SIST p.5) — and the word is
    deliberately not a softer one. An earlier draft called it `weak`, which
    reads as a rung below severe and invited exactly the gradient she does not
    have: SIST p.5 puts "nothing has been done to rule out ways the claim may
    be false" and "the method… had little or no capability of finding flaws
    with C even if they exist" into the same verdict.

    `inconclusive` is always bent whatever else the record says: a test that
    could not tell is a test that would not reliably have detected the error.
    `untestable` is bent too — it is a finding about the claim's formulation
    rather than a test of the claim.

    The four fields do the same work `independence`/`basis`/`method` do for a
    source letter: authored descriptions of what was done, with the verdict
    computed off them. flip cannot check that a `would_detect` line is *true*
    — no more than it can check `support.method` — but requiring it written is
    what separates "I looked" from "I looked with something that would have
    found it, and would not have said so otherwise".
    """
    if str(record.get("result")) not in ("survived", "failed"):
        return "bent"
    return "bent" if severity_gaps(record) else "severe"


def _severe_probes(records: list[dict], result: str) -> set[str]:
    return {
        str(r.get("probe")) for r in records
        if str(r.get("result")) == result and test_severity(r) == "severe"
    }


def derive_exposure(fm: dict) -> str:
    """What a claim's test record adds up to — one of EXPOSURES, DERIVED and
    never stored (the same discipline as `derive_grade` and
    `capture_fidelity`).

    The order below is the precedence, and it is the design's whole argument
    in six lines:

    1. A severe failure with no severe survival on the same probe decides the
       claim, and WHICH probe failed decides the word: `misattributed` when
       only attribution failed (wrong about a source, silent about the world),
       `refuted` when substance or scope failed. A survival on one probe never
       repairs a failure on another — the probes are disjoint on purpose.
    2. Every failing probe also has a severe survival → `bent`. Two severe
       tests of one probe cannot both be right, so at least one of them is not
       what it claims to be and the audit has failed. Mayo is explicit that
       the computations assume a test "has passed (or would pass) an audit,
       else these computations go out the window" (SIST p.201). An earlier
       draft called this `contested`, which read as a stable middle an
       operator could sit in; it is not a reading at all.
    3. A severe survival with no failure → `severely-tested`.
    4. Otherwise, if any attempt concluded the claim as posed admits no test →
       `untestable`. It outranks `bent` because the repair is different (re-pose
       the claim, do not run another test) but never outranks a severe survival:
       a claim something severely tested is testable, whatever an older attempt
       concluded.
    5. Otherwise → `bent`. That covers no tests at all, tests that could not
       have caught the error, and failures from instruments that could have
       been wrong. One verdict, per SIST p.5 — and the worst one on this axis,
       not a neutral default, per SIST p.201.
    """
    records = test_records(fm)
    severe_failed = _severe_probes(records, "failed")
    severe_survived = _severe_probes(records, "survived")
    undisputed = severe_failed - severe_survived
    if undisputed:
        return "misattributed" if undisputed == {"attribution"} else "refuted"
    if severe_failed:
        return "bent"
    if severe_survived:
        return "severely-tested"
    if any(str(r.get("result")) == "untestable" for r in records):
        return "untestable"
    return "bent"


def bent_reason(fm: dict) -> str | None:
    """Why a bent claim is bent, or None when it isn't bent.

    This function exists because of SIST p.201 and nothing else. Mayo does not
    say "call it low"; she says *"I'll say it's low, along with an explanation
    as to why: It's low because we don't have a clue how to compute it!"* The
    explanation is not decoration on the verdict, it is half of it, and a
    surface that renders `bent` without it has kept the easy half.

    Three roads in, and they need different next actions, which is exactly why
    they are not three different verdicts: the verdict is what the claim is
    worth, and it is the same either way.
    """
    if derive_exposure(fm) != "bent":
        return None
    records = test_records(fm)
    if not records:
        return (
            "nothing has been asked of this claim. That is not a neutral starting "
            "point — it is the worst reading this axis has, because the onus is on "
            "whoever is making the claim and nobody has discharged it yet"
        )
    if _severe_probes(records, "failed"):
        return (
            "two severe tests of the same probe contradict each other, so at least one "
            "of them is not the test it claims to be and the audit has failed. There is "
            "no reading here until you say which one was wrong and why"
        )
    return (
        "tests ran, and not one of them would reliably have caught the error. A method "
        "with little capability of finding flaws tells you nothing whichever way it came "
        "out, so a failure recorded by one is not weak evidence against the claim — it is "
        "no evidence, in either direction"
    )


def failed_attribution_sources(fm: dict) -> list[str]:
    """The sources a severe attribution test ran against and failed, deduped.

    What "the claim is wrong about what this source says" points AT. The claim
    usually still cites them, and it must not: the repair is either to unlink
    the source or to restate the claim in the source's own words. Both moves
    need this list.
    """
    out: list[str] = []
    for record in test_records(fm):
        if str(record.get("probe")) != "attribution" or str(record.get("result")) != "failed":
            continue
        if test_severity(record) != "severe":
            continue
        for ref in pages.as_list(record.get("against")):
            text = str(ref).strip()
            if text and text not in out:
                out.append(text)
    return out


# Exposures where a severe test found the claim wrong. `flip claim status …
# verified` refuses on these: a count of independent sources cannot outvote a
# test that went looking for the error and found it.
REFUTING_EXPOSURES = ("misattributed", "refuted")


# --- rivals: the unit of comparison (SPEC §7.1) ----------------------------------


def rival_records(fm: dict) -> list[dict]:
    """Claims the notebook has named as answering the same question as this
    one, in the order they were named: `{claim, because, at, by}`.

    Lakatos, p.69: *"a degenerating problemshift is no more a sufficient reason
    to eliminate a research programme than some old-fashioned 'refutation' or a
    Kuhnian 'crisis'… such an objective reason is provided by a rival research
    programme which explains the previous success of its rival and supersedes
    it by a further display of heuristic power."* Letting go is comparative:
    you let go when something better exists, never on a timer and never because
    a run of bad results made you tired.

    A stance sits on one claim, so "C7 is doing worse than C12" is meaningless
    until something says the two answer the same question. That is all this
    list is: the authored assertion that they do. `because` carries the
    question in the operator's own words, because flip cannot infer it and
    should not pretend a shared source or a shared word implies it. The
    relation is written symmetrically — naming a rival names you as one — since
    a comparison that only one side can see is not a comparison.

    What flip cannot do, and does not: check that the named rival is a real
    one. Lakatos additionally requires that the successor explain the
    predecessor's successes, which is a judgment about content that no tool has
    access to. So every rival-derived finding in doctor reports the comparison
    and asks for a decision; none of them makes one.
    """
    return [
        r for r in pages.as_list(fm.get("rivals"))
        if isinstance(r, dict) and str(r.get("claim") or "").strip()
    ]


def rival_ids(fm: dict) -> list[str]:
    """Just the claim ids of the declared rivals, deduped, in order."""
    out: list[str] = []
    for record in rival_records(fm):
        cid = str(record.get("claim")).strip()
        if cid and cid not in out:
            out.append(cid)
    return out


def superseded_by(fm: dict) -> str | None:
    """The claim this one conceded to, or None.

    Written only by `flip claim supersede`, which is the only way to reach
    `status: superseded` — because a claim that has been let go of without
    naming what replaced it is the exact move Lakatos says is not available
    (p.69). A dead claim with no forwarding address is also just a worse
    notebook: the next reader hits the tombstone and has to re-derive the
    successor from scratch.
    """
    value = str(fm.get("superseded_by") or "").strip()
    return value or None


def explain_exposure(fm: dict) -> dict:
    """Why this claim derives the exposure it does (`flip claim exposure`).

    Returns {exposure, reason, next, tests, stance, holders, rivals}: `tests`
    is one row per record with its derived severity and why it landed there,
    `reason` the rule that fired, and `next` the shortest honest path to a
    stronger exposure. The twin of `explain_grade`, and for the same reason —
    a derivation nobody can see is a verdict wearing a computation's clothes.
    """
    exposure = derive_exposure(fm)
    rows = []
    for record in test_records(fm):
        severity = test_severity(record)
        gaps = severity_gaps(record)
        result = str(record.get("result") or "")
        if severity == "severe":
            why = (
                "named the error, says how it would have shown up, says what it would "
                "have shown otherwise, and is locatable"
            )
        elif result == "inconclusive":
            why = "inconclusive — a test that could not tell would not have detected the error"
        elif result == "untestable":
            why = "a finding about how the claim is posed, not a test of the claim"
        elif "if_absent" in gaps and len(gaps) == 1:
            why = (
                "missing if_absent — nothing says this probe would have come out "
                "differently had the error been absent, and a probe that fires either "
                "way discriminates nothing"
            )
        elif gaps:
            why = f"missing {', '.join(gaps)} — it may simply have missed the error"
        else:
            why = "bent"
        rows.append(
            {
                "probe": str(record.get("probe") or "?"),
                "result": result or "?",
                "severity": severity,
                "why": why,
                "error": str(record.get("error") or ""),
                "against": [str(a) for a in pages.as_list(record.get("against"))],
                "at": str(record.get("at") or ""),
            }
        )

    cid = str(fm.get("id") or "the claim")
    test_cmd = (
        f"`flip claim test {cid} --probe attribution|substance|scope "
        '--error "<the specific way of being wrong>" '
        '--would-detect "<how it would have shown up>" '
        '--if-absent "<what it would have shown instead, had the error not been there>" '
        "--against <ref> --result survived|failed`"
    )
    if exposure == "bent":
        reason = "bad evidence, no test — " + str(bent_reason(fm))
        nxt = "run a test that could have come out the other way, and record it: " + test_cmd
    elif exposure == "misattributed":
        cited = failed_attribution_sources(fm)
        reason = (
            "a severe attribution test failed: the claim is not what its source says. This "
            "is silent on whether the proposition is TRUE — no one has tested that"
        )
        nxt = (
            f"restate the claim in {', '.join(cited) or 'the source'}'s own words, or unlink "
            f"it (`flip claim source rm {cid} {cited[0] if cited else '<id>'}`) and open the "
            f"claim that says what the source says — then `flip claim supersede {cid} --by "
            "<C#>`, which is the only way this claim is allowed to be let go of"
        )
    elif exposure == "refuted":
        reason = (
            "a severe test of substance or scope failed: the claim is wrong about the "
            "world, or about its own reach"
        )
        nxt = (
            f"a refutation on its own does not settle what to do — name the claim that "
            f"survives what this one failed and concede to it (`flip claim rival {cid} <C#> "
            f"--because …`, then `flip claim supersede {cid} --by <C#>`), or record why the "
            f"notebook still holds it (`flip claim stance {cid} pursuing --because … "
            "--falsifier …`). Holding a refuted claim is allowed; holding it silently is not"
        )
    elif exposure == "severely-tested":
        reason = (
            "a test that would probably have caught the error ran, and did not catch it — "
            "the strongest thing this axis says"
        )
        nxt = (
            "severely-tested is the ceiling here; corroboration is a separate axis "
            f"(`flip claim source add {cid} <id>`)"
        )
    else:
        reason = "an attempt concluded the claim AS POSED admits no test"
        nxt = (
            f"re-pose it so it forbids something (`flip claim add \"…\"`, then `flip claim "
            f"supersede {cid} --by <the new C#>`); another test of the same wording will "
            "not help"
        )

    own = notebook_stance(fm)
    return {
        "exposure": exposure,
        "reason": reason,
        "next": nxt,
        "tests": rows,
        "stance": dict(own) if own else None,
        "holders": [dict(r) for r in foreign_stances(fm)],
        "rivals": [dict(r) for r in rival_records(fm)],
        "superseded_by": superseded_by(fm),
    }
