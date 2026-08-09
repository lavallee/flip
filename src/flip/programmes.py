"""Research programmes as entity pages — analysis/<slug>.md, ids RP# (SPEC §7).

The appraisal layer over claims and forecasts. Claims track truth and
forecasts track calibration; neither can say whether a *line of thinking* is
worth staying on. Lakatos's answer is that the unit of appraisal is not the
theory but the programme over time: a **hard core** held by methodological
decision rather than by evidence, and a **protective belt** of auxiliary
claims that absorb the anomalies.

Primary throughout: Lakatos, Imre (1970), 'Falsification and the Methodology
of Scientific Research Programmes', in J. Worrall and G. Currie (eds), *The
Methodology of Scientific Research Programmes: Philosophical Papers Volume 1*,
Cambridge University Press (1978), pp. 8-101. Page numbers below are that
edition's. Every quotation in this module and in SPEC §7 is checkable against
it; the design was once built from a summary instead, and the summary was
wrong in three places that reached shipped behaviour.

**Accommodation is the baseline, not the failure mode.** This is the thing a
summary is most likely to get backwards. Lakatos's series is defined as one
in which *every* step accommodates: "each subsequent theory results from
adding auxiliary clauses to (or from semantical reinterpretations of) the
previous theory in order to accommodate some anomaly" (p. 33). Absorbing a
hit is what a protective belt is *for*. What separates a progressive series
from a degenerating one is not whether a modification accommodated but
whether it *also* bought excess content: "let us call a problemshift
progressive if it is both theoretically and empirically progressive, and
degenerating if it is not" (p. 34). So nothing here scores accommodation as a
defect. The signal is the **absence of novel content**, and the vocabulary
says `content-increasing` / `no novel content` rather than
`progressive` / `accommodation`.

That gives flip the distinction its claim vocabulary could not express. A
claim that cited a paper which does not contain it is an **anomaly**: a belt
member in a non-surviving status, absorbed by whatever replaced it. A claim
nobody has ever tested is a **hard core** member: unconfirmed by
construction, and not a defect. Both were `superseded`/`needs-2nd` before;
they are different objects here, and the difference is declared, not guessed.

Three rules hold the design together:

- **The core is declared once.** There is no command that edits `hard_core`,
  because a programme with a different core is a different programme (open a
  successor with `flip programme add`). The belt grows — that is its job.
- **A shift never absorbs into the core.** `flip programme shift` refuses an
  `--absorbed-by` naming a core claim: absorbing anomalies is exactly what
  the belt is for, and a core that moves under fire was never held by
  decision.
- **The verdict is derived, never stored** (the `derive_grade` doctrine).
  Nothing on the page says "degenerating"; `appraise` computes it from the
  recorded shifts and the dated forecast record every time. The one thing
  stored is `acknowledged:` — a signature on a verdict at a moment, which is
  a decision, not a cache.

**Appraisal and elimination are two different questions.** flip answers the
first and refuses to answer the second on its own, because Lakatos separates
them explicitly: "a degenerating problemshift is no more a sufficient reason
to eliminate a research programme than some old-fashioned 'refutation' or a
Kuhnian 'crisis'. Can there be any objective (as opposed to socio-
psychological) reason to reject a programme…? Our answer, in outline, is that
such an objective reason is provided by a rival research programme which
explains the previous success of its rival and supersedes it by a further
display of heuristic power" (p. 69); and "in spite of hundreds of known
anomalies we do not regard it as falsified (that is, eliminated) until we
have a better one" (p. 36). So `degenerating` is an appraisal of the series
and nothing more. The finding that asks the operator for a decision is
`superseded-programme`, and it needs an out-predicting rival on the record.
See `_outpaced_by`.

**Novel prediction vs. retrodiction is decided on timing, and only on
timing.** A forecast counts as this programme's content when it `bears_on` a
core or belt claim; it is attributed to the last problemshift whose `at` does
not follow its `opened` date. It counts as *content* while it is open, when
it resolved yes, and when it resolved **no** — a refuted risky prediction is
still excess empirical content, and a design that penalized being wrong would
only teach the desk to bet on certainties. It counts as *corroborated*
content only when the resolution landed strictly after the day the bet was
registered. Opened and resolved on the same day, it is a **retrodiction**:
named in the appraisal and scored zero, because a bet placed on a race
already run buys no excess content — the fact was in hand before the bet was.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import manifest, pages, util
from .forecast import RESOLUTIONS

# `status` on a programme is a pursuit state, never a truth state: a programme
# is appraised, not graded and not scored (the two-object rule, SPEC §7).
PROGRAMME_STATUSES = ("pursued", "shelved", "abandoned")

# The four appraisal verdicts, in order of what they owe (SPEC §7). Derived —
# `appraise` recomputes them; no page stores one.
VERDICTS = ("progressive", "theoretically-progressive", "degenerating", "unappraised")

# How many *consecutive* problemshifts must register no novel content before
# flip will say a programme has "ceased to anticipate novel facts".
#
# Lakatos names the condition and names no number. The condition, verbatim:
# "unlike Poincaré, we maintain that if and when the programme ceases to
# anticipate novel facts, its hard core might have to be abandoned: that is,
# our hard core, unlike Poincaré's, may crumble under certain conditions"
# (p. 49). So there *is* an abandonment condition and it is close to what this
# module already computes — a programme that has stopped buying content.
#
# He also warns, on the same page, against reading it off quickly: "While
# 'theoretical progress' (in the sense here described) may be verified
# immediately, 'empirical progress' cannot, and in a research programme we may
# be frustrated by a long series of 'refutations' before ingenious and lucky
# content-increasing auxiliary hypotheses turn a chain of defeats — with
# hindsight — into a resounding success story."
#
# Those two are not in tension once you notice that the same paragraph
# resolves them, by demanding the two kinds of progress at different rates:
# "we must require that each step of a research programme be consistently
# content-increasing… All we need in addition to this is that at least every
# now and then the increase in content should be seen to be retrospectively
# corroborated… We do not demand that each step produce immediately an
# observed new fact. Our term 'intermittently' gives sufficient rational scope
# for dogmatic adherence to a programme in face of prima facie 'refutations'."
#
# That is the whole design of the verdict, and flip follows it exactly:
#   - CORROBORATION is never demanded per shift. `theoretically-progressive`
#     is a good standing, not a warning, and no finding fires on it. That is
#     "intermittently", and it is where the hindsight caution lives.
#   - CONTENT is demanded of every step, which is what "consistently
#     content-increasing" says and what "verified immediately" licenses.
#
# The one thing that is ours and not his is the run length. He asks for
# content at *each* step, so his letter is 1; we use 3, and the reason is a
# fact about notebooks rather than about science. A shift is recorded on the
# day the belt moved; the bet the modification suggests is registered whenever
# the operator next sits down to write one. A run of one barren shift is
# therefore indistinguishable from ordinary lag, and a run of two can still be
# one interrupted week. Three consecutive occasions on which the belt moved
# and nothing was risked is the shortest run that cannot be read as a gap —
# and it is counted in shifts, not days, so it is three declared
# modifications, not three of anything the calendar hands out for free.
#
# Where his letter is 1 and ours is 3, we are being *more* permissive than he
# is, deliberately, and SPEC §7 says so rather than implying he licensed it.
BARREN_RUN_FOR_DEGENERATION = 3

# Claim statuses that make a belt (or core) member an ANOMALY the programme
# has taken. `unconfirmed` is deliberately absent: nobody having tested a
# claim is the state a hard core lives in, not a hit it absorbed — that
# distinction is the whole reason this module exists.
ANOMALOUS_STATUSES = ("superseded", "retracted", "false-positive")

# A forecast this far from even carries little risk, so corroborating it buys
# the programme little. Reported beside the content count, never subtracted
# from it: flip counts content, humans judge whether it was worth having.
LOW_RISK_MARGIN = 0.1

_DESCRIPTION_MAX = 160
_CLAIM_REF_RE = re.compile(r"^claim:(\S+)$")


def _description(text: str) -> str:
    s = " ".join(str(text).split())
    if len(s) <= _DESCRIPTION_MAX:
        return s
    return s[: _DESCRIPTION_MAX - 1].rstrip() + "…"


def _programme_pages(root: Path) -> list[pages.Page]:
    return [
        p for p in pages.iter_pages(root, "analysis") if p.fm.get("type") == "Programme"
    ]


def _claim_pages(root: Path) -> list[pages.Page]:
    return [p for p in pages.iter_pages(root, "claims") if p.fm.get("type") == "Claim"]


def _find_programme(root: Path, rp: str) -> pages.Page:
    """The analysis/ page carrying `rp`, or an actionable refusal."""
    page = next((p for p in _programme_pages(root) if p.id == rp), None)
    if page is None:
        known = ", ".join(p.id for p in _programme_pages(root) if p.id) or "none yet"
        raise SystemExit(
            f"no research programme '{rp}' in analysis/ (known: {known}); declare one "
            "with `flip programme add`"
        )
    return page


def _resolve_claims(root: Path, refs: list[str], what: str) -> list[str]:
    """Claim ids for the given refs, deduped and in order, or one refusal.

    A programme's core and belt are propositions, so every member must be a
    Claim page — the reasoning lives in claims/ with a status and a citation
    trail, and the programme only points (class purity at file level, the same
    rule a Cluster's `inference_link` follows, SPEC §7).
    """
    wanted = [str(r).strip() for r in pages.as_list(refs) if str(r).strip()]
    if not wanted:
        return []
    claim_ids = {p.id for p in _claim_pages(root) if p.id}
    unknown = [r for r in wanted if r not in claim_ids]
    if unknown:
        listed = ", ".join(sorted(claim_ids, key=_id_sort)) or "none yet"
        raise SystemExit(
            f"{what} names {', '.join(unknown)}, which resolve(s) to no claims/ Claim page "
            f"(known: {listed}); a programme's core and belt are propositions and every "
            "member is a Claim — write it with `flip claim add`, then point the programme "
            "at it (class purity, SPEC §7)"
        )
    return list(dict.fromkeys(wanted))


def _id_sort(entity_id: str) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(entity_id))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(entity_id), 0)


def _finish(root: Path) -> None:
    from . import views

    manifest.touch_updated(root)
    views.regenerate(root)


# --- declaration ----------------------------------------------------------------


def add_programme(
    root: Path,
    name: str,
    hard_core: list[str],
    belt: list[str] | None = None,
    *,
    held_by: str | None = None,
    rivals: list[str] | None = None,
    note: str | None = None,
) -> pages.Page:
    """Declare a research programme, allocating the next RP#.

    Refusals before any write: an empty `hard_core` (a programme without a
    core is a mood — name the claim or claims you intend to hold whatever the
    evidence does), a core or belt member that is not an existing Claim, and a
    claim declared in both (a proposition is either held by decision or up for
    revision under fire; declaring it both ways makes the appraisal
    meaningless).

    `held_by` is what makes a *foreign* programme recordable: leave it unset
    and the programme is the notebook's own; set it to whoever holds it ("the
    2020-audit movement") and the page becomes a reconstruction of somebody
    else's core and belt, kept as data beside the evidence that contradicts
    it. The claims keep their own statuses either way — flip never asks a
    page to be both a belief and an assertion.
    """
    root = util.require_notebook_root(root)
    name = " ".join(str(name or "").split())
    if not name:
        raise SystemExit(
            "empty programme name; state the line of thinking in one sentence — it is "
            "what the hard core commits to"
        )
    core = _resolve_claims(root, hard_core, "hard core")
    if not core:
        raise SystemExit(
            "programme has no hard core; a programme without a core is a mood, not a "
            "research programme (SPEC §7) — name at least one claim you intend to hold "
            "by decision whatever the evidence does (`--hard-core C7`)"
        )
    belt_ids = _resolve_claims(root, belt, "protective belt")
    overlap = [c for c in belt_ids if c in core]
    if overlap:
        raise SystemExit(
            f"{', '.join(overlap)} declared in both the hard core and the protective belt; "
            "a proposition is either held by methodological decision or exposed to "
            "revision under fire, never both — pick one (the core is what you will not "
            "give up; everything else belongs in the belt)"
        )

    rp = pages.allocate_id(root, "RP")
    fm: dict = {
        "type": "Programme",
        "id": rp,
        "aliases": [rp],
        "description": _description(name),
        "name": name,
        "held_by": str(held_by) if held_by else "self",
        "hard_core": core,
        "protective_belt": belt_ids,
    }
    if rivals:
        fm["rivals"] = [str(r) for r in pages.as_list(rivals) if str(r).strip()]
    fm["declared"] = util.today()
    fm["status"] = "pursued"
    fm["shifts"] = []
    fm["acknowledged"] = []
    fm["generated"] = util.generated_now()

    parts = [name]
    if note:
        parts.append(f"_{note}_")
    body = "\n\n".join(parts) + "\n"
    directory = root / "analysis"
    slug = pages.unique_slug(directory, pages.slugify(name, fallback=rp.lower()))
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    _finish(root)
    return pages.Page(path=path, fm=fm, body=body)


def extend_belt(root: Path, rp: str, claim_ids: list[str]) -> tuple[pages.Page, list[str]]:
    """Add auxiliary claims to a programme's protective belt.

    The belt is the part that moves, so this is the only membership command:
    there is deliberately no counterpart for the hard core. Changing a core
    means you are pursuing a different programme, and the honest record of
    that is a new RP#, not an edit that quietly rewrites what was held.

    Refuses a claim already in the core (it is held by decision — it cannot
    also be the part that gives) and refuses when every named claim is already
    in the belt. Returns (page, newly added ids).
    """
    root = util.require_notebook_root(root)
    page = _find_programme(root, rp)
    wanted = _resolve_claims(root, claim_ids, "protective belt")
    if not wanted:
        raise SystemExit(
            "no claims given; pass at least one claims/ id to add to the belt, e.g. C18"
        )
    core = [str(c) for c in pages.as_list(page.fm.get("hard_core"))]
    clash = [c for c in wanted if c in core]
    if clash:
        raise SystemExit(
            f"{', '.join(clash)} already in {rp}'s hard core; a core claim cannot also be "
            "belt — the core is what the programme will not give up, the belt is what it "
            f"gives instead (declare a successor programme if the core has changed)"
        )
    belt = [str(c) for c in pages.as_list(page.fm.get("protective_belt"))]
    added = [c for c in wanted if c not in belt]
    if not added:
        raise SystemExit(
            f"{rp}'s protective belt already holds {', '.join(wanted)}; nothing to add"
        )
    page.fm["protective_belt"] = belt + added
    pages.write_page(page.path, page.fm, page.body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body), added


def record_shift(
    root: Path,
    rp: str,
    occasion: str,
    hits: list[str] | None = None,
    absorbed_by: list[str] | None = None,
) -> tuple[pages.Page, dict]:
    """Record one problemshift on a programme, append-only.

    A problemshift is the unit of appraisal: an occasion on which the belt
    moved, what it moved in response to (`hits` — core or belt claims the
    anomaly struck), and what took the weight (`absorbed_by` — the auxiliary
    claims written in reply, added to the belt here if they are not in it
    already). Recording a shift IS how the belt grows.

    Two refusals carry the doctrine. `absorbed_by` may not name a hard core
    claim: absorbing anomalies is what the belt is for, and a core that
    quietly moves under fire was never held by decision. `hits` may only name
    claims the programme actually holds — an anomaly that strikes nothing in
    the core or belt is somebody else's anomaly, and counting it here would
    manufacture a shift.

    Nothing about the appraisal is written: whether this shift produced novel
    content or merely accommodated is derived from the dated forecast record
    at `appraise` time, so it cannot be asserted here and cannot go stale.
    """
    root = util.require_notebook_root(root)
    page = _find_programme(root, rp)
    occasion = " ".join(str(occasion or "").split())
    if not occasion:
        raise SystemExit(
            "empty problemshift; say in one sentence what happened — the occasion is the "
            "part a later reader cannot reconstruct from the claim statuses"
        )
    core = [str(c) for c in pages.as_list(page.fm.get("hard_core"))]
    belt = [str(c) for c in pages.as_list(page.fm.get("protective_belt"))]
    hit_ids = _resolve_claims(root, hits, "hits")
    outside = [c for c in hit_ids if c not in core and c not in belt]
    if outside:
        held = ", ".join(core + belt) or "nothing yet"
        raise SystemExit(
            f"{', '.join(outside)} is not in {rp}'s hard core or protective belt "
            f"(it holds: {held}); an anomaly that strikes nothing the programme holds is "
            "not this programme's anomaly — add the claim to the belt first "
            f"(`flip programme belt {rp} {outside[0]}`) or drop it from --hits"
        )
    absorbed = _resolve_claims(root, absorbed_by, "absorbed-by")
    into_core = [c for c in absorbed if c in core]
    if into_core:
        raise SystemExit(
            f"cannot absorb an anomaly into {rp}'s hard core ({', '.join(into_core)}); "
            "the protective belt is what absorbs hits and the core is what it protects "
            "(SPEC §7) — name the auxiliary claim written in reply, or declare a "
            "successor programme if the core itself has changed"
        )
    new_belt = belt + [c for c in absorbed if c not in belt]

    record: dict = {"at": util.utc_now(), "occasion": occasion}
    if hit_ids:
        record["hits"] = hit_ids
    if absorbed:
        record["absorbed_by"] = absorbed
    record["by"] = util.detect_actor()
    shifts = pages.as_list(page.fm.get("shifts"))
    shifts.append(record)
    page.fm["shifts"] = shifts
    page.fm["protective_belt"] = new_belt
    pages.write_page(page.path, page.fm, page.body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body), record


def acknowledge(root: Path, rp: str, note: str) -> tuple[pages.Page, dict]:
    """Sign for a degenerating programme you intend to keep pursuing.

    The operator's prerogative, written down: holding a line of thinking that
    is producing no novel content is a legitimate research decision, and flip
    will not retract it for you. What it will not do is let the decision stay
    implicit. An acknowledgment records the verdict as it stood, the number of
    problemshifts it stood over, **which rivals were out-predicting it at the
    time**, who signed and why; `flip doctor` stops reporting the programme
    until the next barren shift lands *or a new rival pulls ahead*, and then
    asks again. The signature is a decision, not a cached verdict — `appraise`
    still recomputes from the record every time.

    Recording `outpaced_by` is what makes the signature mean something. The
    decision worth writing down is not "I am holding a programme that has gone
    quiet" — Lakatos is explicit that this needs no defence in the absence of
    a better rival (p. 36, p. 69) — it is "I am holding it *while RP2 is
    predicting more than it is*". A signature that did not name the rival
    could not go stale when a new one arrived.

    Refused on any programme that is not currently degenerating: there is
    nothing to sign for, and a signature collected in advance is exactly the
    click-through this is designed not to be.
    """
    root = util.require_notebook_root(root)
    page = _find_programme(root, rp)
    note = " ".join(str(note or "").split())
    if not note:
        raise SystemExit(
            "acknowledgment needs a --note; an unexplained signature is a click-through — "
            "say why the programme is worth staying on with no novel content on the record"
        )
    report = appraise(root, rp)[0]
    if report["verdict"] != "degenerating":
        raise SystemExit(
            f"{rp} appraises '{report['verdict']}', not degenerating; there is nothing to "
            f"acknowledge — acknowledgment is the signature on a programme whose last "
            f"{BARREN_RUN_FOR_DEGENERATION} problemshift(s) bought no novel content and "
            "which is being pursued anyway"
        )
    record = {
        "at": util.utc_now(),
        "verdict": report["verdict"],
        "shifts": report["shift_count"],
        "outpaced_by": list(report["outpaced_by"]),
        "by": util.detect_actor(),
        "note": note,
    }
    records = pages.as_list(page.fm.get("acknowledged"))
    records.append(record)
    page.fm["acknowledged"] = records
    pages.write_page(page.path, page.fm, page.body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body), record


# --- appraisal (derived) ----------------------------------------------------------


def _forecast_rows(root: Path) -> list[dict]:
    return [
        {**p.fm, "slug": p.slug}
        for p in pages.iter_pages(root, "forecasts")
        if p.fm.get("type") == "Forecast"
    ]


def _resolution_dates(root: Path) -> dict[str, str]:
    """forecast id → the day its resolution landed, from log/resolutions.jsonl.

    The scoring ledger is append-only and written by `flip forecast resolve`,
    which makes it the dated record novelty is decided against. A forecast
    resolved by hand leaves no row; `_bucket` falls back to its last update.
    """
    out: dict[str, str] = {}
    for row in util.read_jsonl(root / RESOLUTIONS):
        fid = str(row.get("forecast") or "")
        ts = str(row.get("ts") or "")[:10]
        if fid and ts:
            out[fid] = ts
    return out


def _resolved_on(fm: dict, ledger: dict[str, str]) -> str:
    """The day a resolved forecast was called: the scoring row, else the last
    `updates:` record carrying an outcome, else "" (undatable)."""
    fid = str(fm.get("id") or "")
    if fid in ledger:
        return ledger[fid]
    for record in reversed(pages.as_list(fm.get("updates"))):
        if isinstance(record, dict) and record.get("outcome"):
            return str(record.get("at") or "")[:10]
    return ""


def _bucket(fm: dict, ledger: dict[str, str]) -> str:
    """Which kind of content one forecast is for the programme that owns it.

    - `open` — registered and unsettled. Content: the bet is exposed.
    - `corroborated` — resolved yes, strictly after the day it was opened.
    - `refuted` — resolved no, strictly after the day it was opened. Still
      content: a risky prediction that failed is excess empirical content,
      and scoring it as nothing would only teach the desk to bet on
      certainties.
    - `retrodiction` — opened and resolved on the same day (or earlier).
      Scored zero and named: a bet placed on a race already run is an
      accommodation wearing a prediction's clothes.
    - `annulled` — resolved void. The question stopped being askable, so it
      scores nothing here for the same reason it scores nothing in Brier.
    """
    status = str(fm.get("status", "open"))
    if status == "open":
        return "open"
    if status == "void":
        return "annulled"
    if status == "superseded":
        return "annulled"
    opened = str(fm.get("opened") or "")
    called = _resolved_on(fm, ledger)
    if opened and called and called <= opened:
        return "retrodiction"
    return "corroborated" if status == "resolved-yes" else "refuted"


# Buckets that count as excess empirical content the programme actually bought.
CONTENT_BUCKETS = ("open", "corroborated", "refuted")


def _bears_on_claims(fm: dict) -> list[str]:
    """The claim refs a forecast bears on, untyped (`claim:C7` → `C7`)."""
    out = []
    for entry in pages.as_list(fm.get("bears_on")):
        m = _CLAIM_REF_RE.match(str(entry))
        if m:
            out.append(m.group(1))
    return out


def _risky(fm: dict) -> bool:
    """A forecast far enough from a foregone conclusion to be worth winning."""
    try:
        p = float(fm.get("probability"))
    except (TypeError, ValueError):
        return True  # unscored is not evidence of timidity; doctor flags the page
    return LOW_RISK_MARGIN <= p <= 1.0 - LOW_RISK_MARGIN


def _attribute(opened: str, shift_days: list[str]) -> int:
    """Index of the problemshift a forecast belongs to: the last shift that had
    already happened when the bet was registered, or -1 for content that
    predates every shift. Attribution is by date alone — nothing is declared,
    so nothing can be declared falsely."""
    index = -1
    for i, day in enumerate(shift_days):
        if day and opened and day <= opened:
            index = i
    return index


def appraise_programme(
    root: Path, page: pages.Page, claim_rows: list[dict] | None = None
) -> dict:
    """Appraise one programme: the derived verdict and everything behind it.

    Derived on every call, stored nowhere (the `derive_grade` doctrine, SPEC
    §5.4/§7). The verdict is read off the content the programme has registered
    against its own core and belt:

    - **degenerating** — the last `BARREN_RUN_FOR_DEGENERATION` problemshifts
      registered no novel content: the programme has "cease[d] to anticipate
      novel facts" (p. 49). Checked *first*, and against the tail rather than
      the lifetime total, because the question is whether the programme is
      still buying content — one corroborated bet years ago cannot answer it,
      and a verdict that could never be revoked once earned would be the
      machine for never being wrong this module exists to avoid.
    - **progressive** — the tail is still content-increasing and at least one
      novel prediction has resolved yes with the bet on the record before the
      surface was read. Theoretically *and* (intermittently) empirically
      progressive, which is Lakatos's conjunction (p. 34).
    - **theoretically-progressive** — the tail is content-increasing but
      nothing has corroborated yet. A *good* standing, not a warning: "We do
      not demand that each step produce immediately an observed new fact"
      (p. 49). Nothing in doctor fires on it.
    - **unappraised** — flip declines to render a verdict: either nothing has
      happened yet, or the barren run is real but still shorter than the
      threshold. A derivative needs two points, and this one is a derivative
      of a series.
    """
    fm = page.fm
    core = [str(c) for c in pages.as_list(fm.get("hard_core"))]
    belt = [str(c) for c in pages.as_list(fm.get("protective_belt"))]
    members = list(dict.fromkeys(core + belt))
    if claim_rows is None:
        claim_rows = [{**p.fm} for p in _claim_pages(root)]
    by_id = {str(c.get("id")): c for c in claim_rows}
    ledger = _resolution_dates(root)

    shifts = [s for s in pages.as_list(fm.get("shifts")) if isinstance(s, dict)]
    shift_days = [str(s.get("at") or "")[:10] for s in shifts]

    # Content: every forecast bearing on a claim this programme holds,
    # attributed to a shift by the day it was opened.
    content: list[dict] = []
    for row in _forecast_rows(root):
        if not set(_bears_on_claims(row)) & set(members):
            continue
        opened = str(row.get("opened") or "")
        content.append(
            {
                "id": str(row.get("id") or "?"),
                "description": str(row.get("description", "")),
                "opened": opened,
                "resolves_by": str(row.get("resolves_by") or ""),
                "probability": row.get("probability"),
                "status": str(row.get("status", "open")),
                "bucket": _bucket(row, ledger),
                "risky": _risky(row),
                "bears_on": [c for c in _bears_on_claims(row) if c in members],
                "shift": _attribute(opened, shift_days),
            }
        )
    content.sort(key=lambda r: (r["opened"], _id_sort(r["id"])))

    per_shift: list[dict] = []
    for i, shift in enumerate(shifts):
        mine = [c for c in content if c["shift"] == i]
        novel = [c for c in mine if c["bucket"] in CONTENT_BUCKETS]
        per_shift.append(
            {
                "at": str(shift.get("at") or ""),
                "occasion": str(shift.get("occasion") or ""),
                "hits": [str(h) for h in pages.as_list(shift.get("hits"))],
                "absorbed_by": [str(a) for a in pages.as_list(shift.get("absorbed_by"))],
                "by": str(shift.get("by") or ""),
                "novel": [c["id"] for c in novel],
                "corroborated": [c["id"] for c in novel if c["bucket"] == "corroborated"],
                "retrodictions": [c["id"] for c in mine if c["bucket"] == "retrodiction"],
                # Named for what it did or did not buy, never for whether it
                # accommodated: every shift accommodates (p. 33).
                "content_increasing": bool(novel),
            }
        )

    novel_all = [c for c in content if c["bucket"] in CONTENT_BUCKETS]
    corroborated = [c for c in novel_all if c["bucket"] == "corroborated"]
    retrodictions = [c for c in content if c["bucket"] == "retrodiction"]

    # The trailing run of problemshifts that registered nothing. This, and not
    # the lifetime totals, is what "ceases to anticipate novel facts" is about.
    barren_run = 0
    for entry in reversed(per_shift):
        if entry["content_increasing"]:
            break
        barren_run += 1

    if barren_run >= BARREN_RUN_FOR_DEGENERATION:
        verdict = "degenerating"
    elif corroborated:
        verdict = "progressive"
    elif novel_all:
        verdict = "theoretically-progressive"
    else:
        verdict = "unappraised"

    anomalies = [
        {"id": c, "status": str(by_id.get(c, {}).get("status", "")), "in_core": c in core}
        for c in members
        if str(by_id.get(c, {}).get("status", "")) in ANOMALOUS_STATUSES
    ]
    recorded_hits = {h for s in per_shift for h in s["hits"]}
    unshifted = [a for a in anomalies if a["id"] not in recorded_hits]

    acks = [a for a in pages.as_list(fm.get("acknowledged")) if isinstance(a, dict)]
    last_ack = acks[-1] if acks else None
    signed = bool(
        last_ack
        and str(last_ack.get("verdict")) == verdict
        and int(last_ack.get("shifts", -1)) == len(shifts)
    )

    return {
        "id": page.id,
        "slug": page.slug,
        "path": page.path.relative_to(root).as_posix(),
        "name": str(fm.get("name") or fm.get("description", "")),
        "held_by": str(fm.get("held_by") or "self"),
        "status": str(fm.get("status", "pursued")),
        "declared": str(fm.get("declared") or ""),
        "verdict": verdict,
        "rivals": [str(r) for r in pages.as_list(fm.get("rivals"))],
        # Both filled by `appraise`, which is the only caller that sees every
        # programme and so the only one that can answer the comparative
        # question. Nothing that reads a single page may claim supersession.
        "rival_verdicts": {},
        "outpaced_by": [],
        "hard_core": [
            {
                "id": c,
                "status": str(by_id.get(c, {}).get("status", "")),
                "corroboration": by_id.get(c, {}).get("independent_corroboration", 0),
                "description": str(by_id.get(c, {}).get("description", "")),
            }
            for c in core
        ],
        "protective_belt": [
            {
                "id": c,
                "status": str(by_id.get(c, {}).get("status", "")),
                "description": str(by_id.get(c, {}).get("description", "")),
            }
            for c in belt
        ],
        "shifts": per_shift,
        "shift_count": len(shifts),
        "content": content,
        "novel_count": len(novel_all),
        "corroborated_count": len(corroborated),
        "retrodiction_count": len(retrodictions),
        "low_risk_count": sum(1 for c in novel_all if not c["risky"]),
        "barren_run": barren_run,
        "barren_run_threshold": BARREN_RUN_FOR_DEGENERATION,
        "anomalies": anomalies,
        "unshifted_anomalies": [a["id"] for a in unshifted],
        "acknowledged": signed,
        "acknowledgment": last_ack,
    }


def _outpaced_by(report: dict, rival: dict) -> bool:
    """Is `rival` superseding `report` in the sense that licenses elimination?

    Lakatos's elimination criterion is comparative, and it is the half a
    summary is most likely to drop: "in spite of hundreds of known anomalies
    we do not regard it as falsified (that is, eliminated) until we have a
    better one" (p. 36), and "We regard a theory in the series 'falsified'
    when it is superseded by a theory with higher corroborated content"
    (p. 34). So flip asks two things of a would-be superseder, one from each
    clause of the criterion at p. 69 ("a rival research programme which
    explains the previous success of its rival and supersedes it by a further
    display of heuristic power"):

    - **higher corroborated content** — strictly more corroborated novel
      predictions than the programme it is displacing. Strictly, so a tie is
      not a supersession.
    - **a further display of heuristic power** — the rival must itself be
      `progressive` right now. A rival whose own tail has gone barren is not
      displaying anything, whatever its lifetime totals say.

    The clause flip *cannot* check is "explains the previous success of its
    rival". No arrangement of claim ids settles whether one programme
    recovers another's results, so flip never asserts supersession outright:
    the doctor finding names the rival and asks, and SPEC §7 records the gap.
    """
    return (
        rival["id"] != report["id"]
        and rival["verdict"] == "progressive"
        and int(rival["corroborated_count"]) > int(report["corroborated_count"])
    )


def _link_rivals(every: list[dict]) -> None:
    """Fill in each report's rival verdicts and the set out-predicting it.

    Rivalry is read **both ways**: a programme is appraised against the rivals
    it declared *and* against every programme that declared it. Lakatos's
    comparison is between programmes, not between a programme and a list it
    keeps, and a one-directional reading would let a notebook duck a
    supersession by leaving the newcomer out of its own `rivals:`.
    """
    by_id = {str(r["id"]): r for r in every}
    inbound: dict[str, set[str]] = {str(r["id"]): set() for r in every}
    for report in every:
        for other in report["rivals"]:
            if other in inbound:
                inbound[other].add(str(report["id"]))
    for report in every:
        rid = str(report["id"])
        against = sorted(set(report["rivals"]) | inbound[rid], key=_id_sort)
        report["rival_verdicts"] = {
            r: by_id[r]["verdict"] if r in by_id else "unknown" for r in against
        }
        report["outpaced_by"] = [
            r for r in against if r in by_id and _outpaced_by(report, by_id[r])
        ]
        # An acknowledgment signed when nobody was ahead does not cover a
        # rival that has since pulled ahead: that is a different decision,
        # and it is the one Lakatos says actually needs making.
        if report["acknowledged"]:
            covered = {
                str(x) for x in pages.as_list((report["acknowledgment"] or {}).get("outpaced_by"))
            }
            if set(report["outpaced_by"]) - covered:
                report["acknowledged"] = False


def appraise(root: Path, rp: str | None = None,
             claim_rows: list[dict] | None = None) -> list[dict]:
    """Appraise every research programme in the notebook (or one), id order.

    Read-only, and the only place the progressive/degenerating question is
    answered. `flip show --programmes` and `flip programme appraise` both
    render this; nothing writes it back.

    It is also the only place the *comparative* question can be answered, and
    that question is the one that matters: a programme is not eliminated for
    degenerating. "[A] degenerating problemshift is no more a sufficient
    reason to eliminate a research programme than some old-fashioned
    'refutation' or a Kuhnian 'crisis'… such an objective reason is provided
    by a rival research programme which explains the previous success of its
    rival and supersedes it by a further display of heuristic power" (p. 69).
    So every report carries `outpaced_by`, and a degenerating programme with
    that list empty is still the best account on the desk — which is not a
    footnote to the verdict, it is most of the reason the programme is
    rationally held.
    """
    root = util.require_notebook_root(root)
    if claim_rows is None:
        claim_rows = [{**p.fm} for p in _claim_pages(root)]
    every = sorted(
        (appraise_programme(root, p, claim_rows) for p in _programme_pages(root)),
        key=lambda r: _id_sort(str(r.get("id", ""))),
    )
    _link_rivals(every)
    if rp is None:
        return every
    _find_programme(root, rp)  # refuses with the known-RP# list
    return [r for r in every if r["id"] == rp]


def list_programmes(root: Path) -> list[dict]:
    """Every analysis/ Programme page as a frontmatter dict (+ slug and
    root-relative path), id order. Read-only, and no appraisal — use
    `appraise` for the verdict, which is derived rather than stored."""
    out = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in _programme_pages(root)
    ]
    return sorted(out, key=lambda r: _id_sort(str(r.get("id", ""))))
