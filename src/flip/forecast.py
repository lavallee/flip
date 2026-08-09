"""Forecasts as entity pages — forecasts/<slug>.md (SPEC §7).

The forward-looking half of the two-object rule: Claims are verified before
shipping and never carry probabilities; Forecasts ship early at low
confidence, update in the open, and get scored. Each forecast is one
markdown page: frontmatter carries the bet (question, probability,
confidence — two scalars, never merged), its resolution wiring (resolves_by,
resolves_via, resolution_source_ladder, resolver, annul_if), and an
append-only `updates:` list; the body carries the reasoning. A forecast with
no date is refused — no undated forecasts — and every forecast names the
condition that would annul it.

Resolution is the product: `resolve_forecast` flips the status, appends the
final update, writes a `forecast-resolve` event to log/log.jsonl, and
appends one row to the append-only log/resolutions.jsonl — the scoring
record (prior · posterior · shift · confidence · source) that `calibration`
reads back. Declined generated questions land in log/declined-forecasts.jsonl
with an optional `fold_into` pointer recording where the useful part went.

Clusters (`type: Cluster`, ids CL#) are unscored decision questions:
`probability: null` by construction, ordered proxy Forecasts, and an
`inference_link` that must point at a Claim page — the link reasoning lives
in claims/ with a grade; the cluster only points (class purity at file
level, SPEC §7). Ids are never reused: allocation goes through
pages.allocate_id, same as every other entity.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

from . import manifest, pages, util

FORECAST_STATUSES = ("open", "resolved-yes", "resolved-no", "void", "superseded")
PREDICTABILITY = ("white", "gray-light", "gray-dark", "black")

# Append-only ledgers this module owns (SPEC §7). resolutions.jsonl is the
# scoring record — one row per resolved forecast, the RS schema; declined-
# forecasts.jsonl is the fold — generated questions turned away, with where
# their useful part went.
RESOLUTIONS = Path("log") / "resolutions.jsonl"
DECLINED = Path("log") / "declined-forecasts.jsonl"
LOG = Path("log") / "log.jsonl"

# Brier is reported only once the record has volume: below this many scored
# resolutions the mean squared error is noise, not calibration (SPEC §7).
BRIER_MIN_RESOLUTIONS = 5

# Terminal outcome → (status, posterior). Void has no posterior: the question
# stopped being askable, so nothing is scored.
_OUTCOMES = {
    "yes": ("resolved-yes", 1.0),
    "no": ("resolved-no", 0.0),
    "void": ("void", None),
}

# bears_on entries are typed edges — the type keeps class purity checkable
# (a claim citing a forecast without a typed edge draws a doctor finding).
# `belief:` joined the grammar with the Belief class (SPEC §7.1): "will X's
# prevalence exceed 40% by 2028" is a bet about believers, resolvable on a
# survey, and it is the one honest way a forecast can bear on a belief without
# anything ever counting toward the proposition believed.
BEARS_ON_RE = re.compile(r"^(claim|cluster|question|belief):\S+$")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DESCRIPTION_MAX = 160


def _description(text: str) -> str:
    s = " ".join(str(text).split())
    if len(s) <= _DESCRIPTION_MAX:
        return s
    return s[: _DESCRIPTION_MAX - 1].rstrip() + "…"


def _require_text(value: str | None, what: str, hint: str) -> str:
    value = (value or "").strip()
    if not value:
        raise SystemExit(f"{what}; {hint}")
    return value


def _scalar(value, name: str) -> float:
    """Parse probability/confidence: a float in [0, 1], stored as a float.

    Two scalars, never merged (SPEC §7): probability is the estimate,
    confidence is how much the estimate rests on.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SystemExit(
            f"{name} {value!r} is not a number; pass a probability-like scalar "
            "in [0, 1], e.g. 0.3"
        ) from None
    if not 0.0 <= number <= 1.0:
        raise SystemExit(
            f"{name} {number} is out of range; probabilities and confidences "
            "live in [0, 1]"
        )
    return number


def _parse_day(value) -> date | None:
    """A YYYY-MM-DD string as a date, else None."""
    s = str(value or "")
    if not _DATE_RE.match(s):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _forecast_pages(root: Path) -> list[pages.Page]:
    return [
        p for p in pages.iter_pages(root, "forecasts") if p.fm.get("type") == "Forecast"
    ]


def _find_forecast(root: Path, fid: str) -> pages.Page:
    """The forecasts/ page carrying `fid`, or an actionable refusal."""
    page = next((p for p in _forecast_pages(root) if p.id == fid), None)
    if page is None:
        known = ", ".join(p.id for p in _forecast_pages(root) if p.id) or "none yet"
        raise SystemExit(
            f"no forecast '{fid}' in forecasts/ (known: {known}); add one with "
            "`flip forecast add`"
        )
    return page


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10)."""
    from . import views

    views.regenerate(root)


def _finish(root: Path) -> None:
    manifest.touch_updated(root)
    _regenerate_views(root)


def add_forecast(
    root: Path,
    question: str,
    resolves_by: str | None,
    resolves_via: list[str] | None,
    annul_if: str | None,
    probability,
    confidence,
    *,
    resolution_criteria: str | None = None,
    resolution_source_ladder: list[str] | None = None,
    resolver: str | None = None,
    base_rate: str | None = None,
    predictability: str | None = None,
    bears_on: list[str] | None = None,
    generated_by: str | None = None,
    horizon=None,
) -> pages.Page:
    """Open a forecast page with status "open", allocating the next FC#.

    Refusals before any write: a forecast with no `resolves_by` (no undated
    forecasts — an undated bet can never be scored), no `annul_if` (annulment
    conditions are mandatory: most real forecasts need one, and discovering
    that at resolution time is too late), a probability/confidence outside
    [0, 1], or a `bears_on` entry that isn't a typed ref
    (claim:/cluster:/question:/belief:). `base_rate` stays a string — it
    carries its own numerator and denominator as stated, never a bare number
    (SPEC §7).
    """
    root = util.require_notebook_root(root)
    question = _require_text(
        question, "empty forecast question", "state the bet in one sentence"
    )
    if not str(resolves_by or "").strip():
        raise SystemExit(
            "forecast has no resolves_by — no undated forecasts (SPEC §7): an "
            "undated bet can never be scored; pass the resolution date (YYYY-MM-DD)"
        )
    if _parse_day(resolves_by) is None:
        raise SystemExit(
            f"resolves_by {resolves_by!r} is not a date; pass YYYY-MM-DD "
            "(e.g. 2027-03-31)"
        )
    annul_if = _require_text(
        annul_if,
        "forecast has no annul_if — annulment conditions are mandatory (SPEC §7)",
        "state the condition under which the question stops being askable",
    )
    prob = _scalar(probability, "probability")
    conf = _scalar(confidence, "confidence")
    if predictability is not None and predictability not in PREDICTABILITY:
        raise SystemExit(
            f"invalid predictability '{predictability}' "
            f"(one of: {', '.join(PREDICTABILITY)})"
        )
    bears = [str(b) for b in pages.as_list(bears_on)]
    for entry in bears:
        if not BEARS_ON_RE.match(entry):
            raise SystemExit(
                f"bears_on entry {entry!r} is not a typed ref — every edge names "
                "its class (claim:<ref>, cluster:<ref>, question:<ref>, belief:<ref>) "
                "so class "
                "purity stays checkable (SPEC §7)"
            )
    vias = [str(s) for s in pages.as_list(resolves_via) if str(s).strip()]
    ladder = [str(s) for s in pages.as_list(resolution_source_ladder) if str(s).strip()]

    fid = pages.allocate_id(root, "FC")
    fm: dict = {
        "type": "Forecast",
        "id": fid,
        "aliases": [fid],
        "description": _description(question),
        "question": question,
    }
    if resolution_criteria:
        fm["resolution_criteria"] = resolution_criteria
    fm["resolves_by"] = str(resolves_by)
    fm["resolves_via"] = vias
    if ladder:
        fm["resolution_source_ladder"] = ladder
    if resolver:
        fm["resolver"] = str(resolver)
    fm["probability"] = prob
    fm["confidence"] = conf
    if base_rate:
        fm["base_rate"] = str(base_rate)
    if predictability:
        fm["predictability"] = predictability
    fm["annul_if"] = annul_if
    if bears:
        fm["bears_on"] = bears
    if generated_by:
        fm["generated_by"] = str(generated_by)
    if horizon is not None:
        fm["horizon"] = horizon
    fm["opened"] = util.today()
    fm["freeze"] = util.today()
    fm["status"] = "open"
    fm["updates"] = []
    fm["generated"] = util.generated_now()

    body = question + "\n"
    directory = root / "forecasts"
    slug = pages.unique_slug(directory, pages.slugify(question, fallback=fid.lower()))
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    _finish(root)
    return pages.Page(path=path, fm=fm, body=body)


def update_forecast(
    root: Path,
    fid: str,
    probability=None,
    confidence=None,
    note: str | None = None,
) -> pages.Page:
    """Move a forecast's current probability/confidence, append-only.

    Appends one {at, probability?, confidence?, note?, by} record to
    `updates:` — records are added, never edited — and sets the current
    probability/confidence keys so the frontmatter always shows the live
    estimate. Refuses on any non-open status: a resolved forecast is scored
    history, and history doesn't move.
    """
    root = util.require_notebook_root(root)
    page = _find_forecast(root, fid)
    status = str(page.fm.get("status", "open"))
    if status != "open":
        raise SystemExit(
            f"forecast {fid} is '{status}', not open — a scored forecast never "
            "moves again; open a successor with `flip forecast add` instead"
        )
    if probability is None and confidence is None and note is None:
        raise SystemExit(
            "nothing to record; pass --probability, --confidence, and/or --note"
        )
    record: dict = {"at": util.utc_now()}
    if probability is not None:
        prob = _scalar(probability, "probability")
        record["probability"] = prob
        page.fm["probability"] = prob
    if confidence is not None:
        conf = _scalar(confidence, "confidence")
        record["confidence"] = conf
        page.fm["confidence"] = conf
    if note:
        record["note"] = str(note)
    record["by"] = util.detect_actor()
    updates = pages.as_list(page.fm.get("updates"))
    updates.append(record)
    page.fm["updates"] = updates
    pages.write_page(page.path, page.fm, page.body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


def resolve_forecast(
    root: Path, fid: str, outcome: str, note: str | None = None
) -> pages.Page:
    """Resolve a forecast: yes | no | void. The scoring moment (SPEC §7).

    Flips the status (resolved-yes / resolved-no / void), appends the final
    record to `updates:`, writes a `forecast-resolve` event to log/log.jsonl,
    and appends the scoring row to the append-only log/resolutions.jsonl:
    ts · forecast · topic · bears_on · prior · evidence · posterior · shift ·
    confidence · source. A void resolution scores nothing (posterior and
    shift are null) — the question stopped being askable. Re-resolution is
    refused: resolutions are final.
    """
    root = util.require_notebook_root(root)
    if outcome not in _OUTCOMES:
        raise SystemExit(
            f"invalid outcome '{outcome}' (one of: {', '.join(_OUTCOMES)})"
        )
    page = _find_forecast(root, fid)
    status = str(page.fm.get("status", "open"))
    if status != "open":
        raise SystemExit(
            f"forecast {fid} is already '{status}'; resolutions are final — "
            "open a successor with `flip forecast add` if the question lives on"
        )
    new_status, posterior = _OUTCOMES[outcome]
    prior = _scalar(page.fm.get("probability"), "probability")
    confidence = page.fm.get("confidence")
    shift = None if posterior is None else posterior - prior
    ts = util.utc_now()
    actor = util.detect_actor()

    record: dict = {"at": ts, "outcome": outcome}
    if note:
        record["note"] = str(note)
    record["by"] = actor
    updates = pages.as_list(page.fm.get("updates"))
    updates.append(record)
    page.fm["updates"] = updates
    page.fm["status"] = new_status
    pages.write_page(page.path, page.fm, page.body)

    util.append_jsonl(
        root / RESOLUTIONS,
        {
            "ts": ts,
            "forecast": fid,
            "topic": str(page.fm.get("description", "")),
            "bears_on": [str(b) for b in pages.as_list(page.fm.get("bears_on"))],
            "prior": prior,
            "evidence": str(note or ""),
            "posterior": posterior,
            "shift": shift,
            "confidence": confidence,
            "source": ", ".join(
                str(s) for s in pages.as_list(page.fm.get("resolves_via"))
            ),
        },
    )
    util.append_jsonl(
        root / LOG,
        {"ts": ts, "text": f"forecast-resolve {fid}: {outcome}", "actor": actor},
    )
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)


def decline_forecast(
    root: Path, text: str, reason: str, fold_into: str | None = None
) -> dict:
    """Record a declined generated question in log/declined-forecasts.jsonl.

    The fold: a declined generation is negative coverage, not garbage — a
    good share turn out to be load-bearing elsewhere (an annul_if clause, a
    sharper sibling). `fold_into` names the existing forecast that absorbed
    the useful part, and is refused when it doesn't resolve — the fold points
    at the record, never at a wish. Returns the row written.
    """
    root = util.require_notebook_root(root)
    text = _require_text(text, "empty declined-question text", "pass the question that was declined")
    reason = _require_text(reason, "empty reason", "say why it was declined — the payload")
    if fold_into is not None:
        _find_forecast(root, str(fold_into))  # refuses with the known-FC# list
    row: dict = {"ts": util.utc_now(), "text": text, "reason": reason,
                 "disposition": "declined"}
    if fold_into is not None:
        row["fold_into"] = str(fold_into)
    row["actor"] = util.detect_actor()
    util.append_jsonl(root / DECLINED, row)
    _finish(root)
    return row


def due_forecasts(root: Path, within_days: int = 30) -> list[dict]:
    """Open forecasts whose resolves_by is past or within `within_days`.

    The loop any agent runtime needs without flip owning cadence (SPEC §7):
    flip records, runners run. Each row is the page frontmatter plus slug,
    root-relative path, and `days_left` (negative = overdue), sorted by
    resolves_by. Read-only.
    """
    today = _today()
    out: list[dict] = []
    for page in _forecast_pages(root):
        if str(page.fm.get("status", "open")) != "open":
            continue
        day = _parse_day(page.fm.get("resolves_by"))
        if day is None:
            continue  # undated open forecast: doctor's finding, not a due row
        days_left = (day - today).days
        if days_left <= within_days:
            out.append(
                {
                    **page.fm,
                    "slug": page.slug,
                    "path": page.path.relative_to(root).as_posix(),
                    "days_left": days_left,
                }
            )
    out.sort(key=lambda r: str(r.get("resolves_by", "")))
    return out


def calibration(root: Path) -> dict:
    """The running record: counts, sharpness, and Brier-once-volume-allows.

    Reads log/resolutions.jsonl (yes/no rows are scored; void rows are
    counted, never scored) plus the open forecast pages. Both scores ship
    labeled (SPEC §7): sharpness = resolved_yes / (resolved_yes +
    resolved_no), None when nothing is scored; brier = mean of
    (prior − posterior)² over scored rows, None below
    BRIER_MIN_RESOLUTIONS — the volume rule.
    """
    rows = util.read_jsonl(root / RESOLUTIONS)
    scored = [r for r in rows if r.get("posterior") in (0.0, 1.0)]
    resolved_yes = sum(1 for r in scored if r.get("posterior") == 1.0)
    resolved_no = len(scored) - resolved_yes
    void = sum(1 for r in rows if r.get("posterior") is None)
    n_scored = len(scored)
    sharpness = resolved_yes / n_scored if n_scored else None
    brier = (
        sum((float(r.get("prior", 0.0)) - float(r["posterior"])) ** 2 for r in scored)
        / n_scored
        if n_scored >= BRIER_MIN_RESOLUTIONS
        else None
    )
    open_count = sum(
        1 for p in _forecast_pages(root) if str(p.fm.get("status", "open")) == "open"
    )
    return {
        "open": open_count,
        "resolved_yes": resolved_yes,
        "resolved_no": resolved_no,
        "void": void,
        "sharpness": sharpness,
        "brier": brier,
        "n_scored": n_scored,
    }


def add_cluster(
    root: Path,
    decision_question: str,
    proxies: list[str],
    inference_link: str | None,
    horizon=None,
) -> pages.Page:
    """Open a cluster page — an unscored decision question — allocating CL#.

    A cluster carries `scored: false` and `probability: null` by
    construction: the decision question is the one the desk cannot resolve,
    and it never gets a number. `proxies` are the ordered resolvable
    Forecasts standing under it — each must exist. `inference_link` is the
    reasoning that connects proxies to decision, and it must be an existing
    Claim id: the link lives in claims/ with a grade, the cluster only
    points (class purity at file level, SPEC §7).
    """
    root = util.require_notebook_root(root)
    decision_question = _require_text(
        decision_question, "empty decision question",
        "state the decision the cluster bounds",
    )
    proxy_ids = [str(p) for p in pages.as_list(proxies) if str(p).strip()]
    if not proxy_ids:
        raise SystemExit(
            "cluster has no proxies; name at least one resolvable forecast "
            "(FC#) standing under the decision question"
        )
    known = {p.id for p in _forecast_pages(root) if p.id}
    missing = [p for p in proxy_ids if p not in known]
    if missing:
        listed = ", ".join(sorted(known)) or "none yet"
        raise SystemExit(
            f"unknown proxy forecast(s) {', '.join(missing)}: no forecasts/ page "
            f"carries them (known: {listed}); add them with `flip forecast add` first"
        )
    if inference_link is not None:
        link = str(inference_link)
        claim_ids = {
            p.id
            for p in pages.iter_pages(root, "claims")
            if p.id and p.fm.get("type") == "Claim"
        }
        if link not in claim_ids:
            listed = ", ".join(sorted(claim_ids)) or "none yet"
            raise SystemExit(
                f"inference_link '{link}' is not an existing claim id (known: "
                f"{listed}); the link reasoning lives in claims/ with a grade — "
                "add it with `flip claim add`, then point the cluster at it "
                "(class purity, SPEC §7)"
            )

    cid = pages.allocate_id(root, "CL")
    fm: dict = {
        "type": "Cluster",
        "id": cid,
        "aliases": [cid],
        "description": _description(decision_question),
        "decision_question": decision_question,
        "scored": False,
        "probability": None,  # a decision question carries no number, by construction
        "proxies": proxy_ids,
        "inference_link": str(inference_link) if inference_link is not None else None,
    }
    if horizon is not None:
        fm["horizon"] = horizon
    fm["opened"] = util.today()
    fm["status"] = "open"
    fm["generated"] = util.generated_now()

    body = decision_question + "\n"
    directory = root / "forecasts"
    slug = pages.unique_slug(
        directory, pages.slugify(decision_question, fallback=cid.lower())
    )
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    _finish(root)
    return pages.Page(path=path, fm=fm, body=body)


def _id_sort_key(fm: dict) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(fm.get("id", "")))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(fm.get("id", "")), 0)


def list_forecasts(root: Path) -> list[dict]:
    """Every forecasts/ page (Forecasts and Clusters) as frontmatter dicts
    (+ slug and root-relative path), id order. Read-only."""
    out = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in pages.iter_pages(root, "forecasts")
        if p.fm.get("type") in ("Forecast", "Cluster")
    ]
    return sorted(out, key=_id_sort_key)
