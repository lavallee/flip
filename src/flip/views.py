"""Computed views and generated at-rest projections (SPEC §10).

Views are computed, never canonical. Two surfaces live here:

- **`flip show`** — hot_view/claims_view/stale_view assemble windowed
  projections (open questions, claims needing work, dated sources, recent
  log, latest session) from the entity pages and JSONL ledgers. Each returns
  rendered plain text, or a plain dict when `as_data=True` (for `--json`).
- **`regenerate(root)`** — rewrites the at-rest equivalents after every
  mutation: `log.md` (newest-first view of log/log.jsonl), each entity
  directory's `index.md` listing, and the root `index.md` *body* (the OKF
  directory listing; the manifest frontmatter is preserved untouched).
  Deterministic: the same notebook state always produces the same bytes.

Reads are tolerant (pages.iter_pages_tolerant): one corrupt page never takes
down a view — `flip doctor` is where corruption gets reported.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from . import claims, pages, stance
from . import sources as sources_mod
from .manifest import Manifest, load_manifest, save_manifest
from .profiles import Profile, load_profile
from .util import age_months, idle_days, read_jsonl

# Claim status enum (SPEC §7), in display order.
CLAIM_STATUS_ORDER = (
    "asserted",
    "verified",
    "needs-2nd",
    "unconfirmed",
    "false-positive",
    "retracted",
    "superseded",
)
# Statuses that mean "this claim still needs verification work".
NEEDS_WORK_STATUSES = ("asserted", "needs-2nd")
RECENT_LOG_COUNT = 8
TRUNCATE_WIDTH = 80

# Caps on the two surfaces that grow with the notebook (measured: a 301-source
# corpus produced a 73 KB references/index.md — ~18 K tokens for a directory
# listing — and a hot view that was 74 % armed-trigger roster). A listing past
# the cap shows the newest entries and says how many more exist; the full
# roster lives in the list commands. `--json` surfaces stay complete.
INDEX_LIST_CAP = 50
HOT_ROSTER_CAP = 8

# Entity dir → the command that lists the full roster (named in cap footers).
_LIST_COMMANDS = {
    "references": "flip source list",
    "claims": "flip claim list",
    "questions": "flip question list",
    "commissions": "flip commission list",
}

# Derived cache of per-directory listing counts (plus the open-question count),
# so an incremental regenerate can rebuild the root index.md body without
# re-parsing every page in the unchanged directories. Purely derived: absent or
# corrupt, every directory is recounted from the pages. Refreshed whenever a
# directory's listing is rewritten.
VIEWCACHE = Path(".flip") / "viewcache.json"

LOG_JSONL = Path("log") / "log.jsonl"
LOG_MD = "log.md"

# Entity directory → (listing title, root-listing description builder input).
_DIR_TITLES = {
    "references": "References",
    "claims": "Claims",
    "decisions": "Decisions",
    "questions": "Questions",
    "forecasts": "Forecasts",
    "commissions": "Commissions",
    "sessions": "Sessions",
}

_ID_NUM = re.compile(r"(\d+)$")


def _trunc(text: object, width: int = TRUNCATE_WIDTH) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= width:
        return s
    return s[: width - 1].rstrip() + "…"


def _one_line(text: object) -> str:
    return " ".join(str(text or "").split())


def _id_num(entity_id: str) -> int:
    m = _ID_NUM.search(str(entity_id))
    return int(m.group(1)) if m else 0


def _read(root: Path, rel: Path | str) -> list[dict]:
    """Read an optional ledger; a corrupt line becomes an actionable exit."""
    try:
        return read_jsonl(root / rel)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line (flip doctor pinpoints it)") from None


def _pages(root: Path, dirname: str) -> list[pages.Page]:
    """Entity pages, filename order; corrupt pages skipped (doctor flags them)."""
    out, _errors = pages.iter_pages_tolerant(root, dirname)
    return out


def _profile_or_default(m: Manifest, root: Path) -> Profile:
    """Views tolerate an unresolvable kind; doctor is where that gets flagged."""
    try:
        return load_profile(m.kind, root)
    except SystemExit:
        return Profile(id=m.kind)


def _question_text(page: pages.Page) -> str:
    """The current question text: the body's lead prose up to the first '##'
    section (## Answer, or a dated Evidence/Re-posed/Closed/Dormant/Reopened
    block), else the description."""
    body = page.body.lstrip("\n")
    if body.startswith("## "):
        return str(page.fm.get("description", ""))
    head = body.split("\n## ", 1)[0].strip()
    return head or str(page.fm.get("description", ""))


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _review_pending(review_by: str) -> bool:
    """True while a dormant question's review date is still in the future.

    An unparseable or missing `review_by` returns False — the question lands
    on the roster NOW rather than being hidden by a value nobody can read
    (a lexicographic compare against garbage like "Q3 2026" would park it
    forever; failing loud onto the roster is the honest degradation).
    """
    try:
        return datetime.strptime(review_by, "%Y-%m-%d").strftime("%Y-%m-%d") > _today()
    except ValueError:
        return False


def _open_questions(root: Path, loaded: list[pages.Page] | None = None) -> list[dict]:
    """Question pages still on the working roster (missing status = open).

    Open questions always; dormant ones only once their `review_by` date has
    arrived (that is what parking means — before the date they stay out of
    the view, after it they resurface marked "review due"). Answered and
    closed pages never appear here; the ones with armed reopen triggers get
    their own view (_reopen_armed). A status OUTSIDE the vocabulary stays on
    the roster — a typo must degrade to visible (doctor names the bad enum),
    never to a question silently missing from every surface.

    `loaded` lets a caller that already parsed questions/ reuse those pages
    rather than paying the parse twice.
    """
    out = []
    for page in (loaded if loaded is not None else _pages(root, "questions")):
        if str(page.fm.get("type", "")) != "Question":
            continue
        status = str(page.fm.get("status", "open"))
        review_by = str(page.fm.get("review_by", ""))
        if status in ("answered", "closed"):
            continue
        if status == "dormant" and _review_pending(review_by):
            continue
        row = {
            "id": page.id,
            "text": _question_text(page),
            "ts": pages.generated_at(page.fm),
            "resolves_via": [str(s) for s in pages.as_list(page.fm.get("resolves_via"))],
        }
        if status == "dormant":
            row["status"] = status
            row["review_by"] = review_by
        out.append(row)
    out.sort(key=lambda q: _id_num(q["id"]))
    return out


def _reopen_armed(root: Path) -> list[dict]:
    """Settled questions (answered/closed) whose reopen_when triggers are armed.

    These are watchable, not dead: the row carries the written conditions so
    the view can show what would reopen each one.
    """
    out = []
    for page in _pages(root, "questions"):
        if str(page.fm.get("type", "")) != "Question":
            continue
        if str(page.fm.get("status", "open")) not in ("answered", "closed"):
            continue
        triggers = [str(t) for t in pages.as_list(page.fm.get("reopen_when"))]
        if not triggers:
            continue
        out.append(
            {
                "id": page.id,
                "status": str(page.fm.get("status")),
                "text": _question_text(page),
                "reopen_when": triggers,
            }
        )
    out.sort(key=lambda q: _id_num(q["id"]))
    return out


def _claim_rows(root: Path) -> list[dict]:
    """Claim pages as plain dicts (fm + slug + root-relative path), id order."""
    rows = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in _pages(root, "claims")
        if str(p.fm.get("type", "")) == "Claim"
    ]
    rows.sort(key=lambda r: _id_num(str(r.get("id", ""))))
    return rows


def _claims_needing_work(root: Path) -> list[dict]:
    claims = [c for c in _claim_rows(root) if c.get("status") in NEEDS_WORK_STATUSES]
    claims.sort(key=lambda c: not c.get("load_bearing", False))  # load-bearing first, stable
    return claims


def _source_rows(root: Path) -> list[dict]:
    rows = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in _pages(root, "references")
        if str(p.fm.get("type", "")) == "Source"
    ]
    rows.sort(key=lambda r: _id_num(str(r.get("id", ""))))
    return rows


def _latest_session(root: Path) -> str | None:
    sessions = root / "sessions"
    if not sessions.is_dir():
        return None
    files = [
        p
        for p in sessions.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and p.name not in pages.RESERVED
        and not p.name.startswith((".", "_"))
    ]
    if not files:
        return None
    newest = max(files, key=lambda p: p.name)  # names are UTC-stamped (SPEC §3)
    return newest.relative_to(root).as_posix()


def _stale_sources(rows: list[dict], freshness_months: int) -> list[dict]:
    """Sources judged dated, or whose page date is at/past the profile threshold."""
    today = datetime.now(timezone.utc).date()
    out = []
    for row in rows:
        if row.get("freshness") == "dated":
            out.append(row)
            continue
        age = age_months(row.get("date"), today)
        if age is not None and age >= freshness_months:
            out.append(row)
    return out


def _claim_line(c: dict, with_status: bool = False) -> str:
    parts = [str(c.get("id", "?"))]
    if with_status:
        parts.append(str(c.get("status", "")))
    if c.get("load_bearing"):
        parts.append("[load-bearing]")
    parts.append(_trunc(c.get("description", "")))
    sources = claims.source_ids(c)
    parts.append("sources: " + (", ".join(sources) if sources else "none"))
    # `n/a`, never 0, where the axis does not apply (SPEC §7): a claim citing
    # only what it is ABOUT has no witnesses to count, and a zero in this
    # column reads as thin evidence rather than as the wrong instrument. The
    # word in the parenthesis is the reason, because a blank with no reason is
    # the half of the lesson that is easy to ship.
    parts.append(
        "corroboration: "
        + (
            f"{c.get('independent_corroboration', 0)}"
            if claims.corroboration_applies(c)
            else "n/a (subject)"
        )
    )
    # The attitude axis rides along only where it is used (SPEC §7.1). A claim
    # in a notebook that has never recorded a stance, a test or a rivalry says
    # nothing new, and appending "bent" to every line in every notebook would
    # make the word mean "ordinary" — which is the inversion this design was
    # corrected for, arriving from the other direction.
    if c.get("stances") or c.get("tests") or c.get("rivals"):
        own = stance.notebook_stance(c)
        parts.append(
            stance.derive_exposure(c)
            + (f"/{own.get('stance')}" if own else "")
        )
    return " · ".join(parts)


def _roster_overflow(rows: list, command: str) -> list[str]:
    """The one-line footer under a capped hot-view roster, or nothing."""
    if len(rows) <= HOT_ROSTER_CAP:
        return []
    return [f"  … and {len(rows) - HOT_ROSTER_CAP} more — `{command}`"]


def hot_view(root: Path, as_data: bool = False) -> str | dict:
    """Current focus: open questions, claims needing work, recent activity."""
    m = load_manifest(root)
    profile = _profile_or_default(m, root)
    questions = _open_questions(root)
    armed = _reopen_armed(root)
    claims = _claims_needing_work(root)
    recent = _read(root, LOG_JSONL)[-RECENT_LOG_COUNT:]
    session = _latest_session(root)
    dated = _stale_sources(_source_rows(root), profile.freshness_months)
    idle = idle_days(m.updated)
    if as_data:
        return {
            "slug": m.slug,
            "kind": m.kind,
            "status": m.status,
            "updated": m.updated,
            "idle_days": idle,
            "open_questions": questions,
            "reopen_armed": armed,
            "claims_needing_work": claims,
            "recent_log": recent,
            "latest_session": session,
            "dated_sources": len(dated),
        }
    lines = [" · ".join([m.slug, m.kind, m.status + _idle_suffix(idle), m.updated])]
    # Each roster is capped: the hot view is the resume-here screen, and a
    # screen has a size by definition. Measured failure mode: a notebook whose
    # steady state was "everything answered, everything watched" rendered a
    # hot view that was 74 % armed-trigger roster, burying the one actionable
    # claim. The count and the full roster survive in the footer's command;
    # `--json` (as_data above) always carries everything.
    if questions:
        lines += ["", "OPEN QUESTIONS"]
        for q in questions[:HOT_ROSTER_CAP]:
            marker = ""
            if q.get("status") == "dormant":
                marker = f"  [dormant · review due {q.get('review_by', '')}]"
            elif not q.get("resolves_via"):
                marker = "  [unwatched — no resolves_via surface]"
            lines.append(f"  {q['id']} · {_trunc(q['text'])}" + marker)
        lines += _roster_overflow(questions, "flip question list")
    if armed:
        lines += ["", "REOPEN TRIGGERS ARMED"]
        lines += [
            f"  {q['id']} · {q['status']} · when: {_trunc('; '.join(q['reopen_when']))}"
            for q in armed[:HOT_ROSTER_CAP]
        ]
        lines += _roster_overflow(armed, "flip question list --armed")
    if claims:
        lines += ["", "CLAIMS NEEDING WORK"]
        lines += [
            f"  {_claim_line(c, with_status=True)}" for c in claims[:HOT_ROSTER_CAP]
        ]
        lines += _roster_overflow(claims, "flip claim list")
    if recent:
        lines += ["", "RECENT LOG"]
        lines += [
            f"  {e.get('ts', '')} · {e.get('actor', '')} · {_trunc(e.get('text', ''))}"
            for e in recent
        ]
    if session:
        lines += ["", "LATEST SESSION", f"  {session}"]
    if dated:
        lines += ["", f"DATED SOURCES: {len(dated)}"]
    return "\n".join(lines)


def claims_view(root: Path, as_data: bool = False) -> str | dict:
    """All claims grouped by status, enum order first, unknown statuses last."""
    load_manifest(root)  # fail early with an actionable error if this isn't a notebook
    claims = _claim_rows(root)
    groups: dict[str, list[dict]] = {}
    for c in claims:
        groups.setdefault(str(c.get("status", "unknown")), []).append(c)
    order = [s for s in CLAIM_STATUS_ORDER if s in groups]
    order += [s for s in groups if s not in CLAIM_STATUS_ORDER]
    if as_data:
        return {"total": len(claims), "by_status": {s: groups[s] for s in order}}
    if not claims:
        return "no claims recorded (claims/ is absent or empty)"
    lines: list[str] = []
    for status in order:
        lines.append(status.upper())
        lines += [f"  {_claim_line(c)}" for c in groups[status]]
        lines.append("")
    return "\n".join(lines).rstrip()


def stale_view(root: Path, as_data: bool = False) -> str | dict:
    """What has gone cold: dated sources, open questions, stuck claims."""
    m = load_manifest(root)
    profile = _profile_or_default(m, root)
    dated = _stale_sources(_source_rows(root), profile.freshness_months)
    questions = _open_questions(root)
    stuck = _claims_needing_work(root)
    if as_data:
        return {"dated_sources": dated, "open_questions": questions, "stuck_claims": stuck}
    lines: list[str] = []
    if dated:
        lines.append("DATED SOURCES")
        for row in dated:
            lines.append(
                f"  {row.get('id', '?')} · {_trunc(row.get('title', ''))}"
                f" · date: {row.get('date') or 'unknown'}"
                f" · freshness: {row.get('freshness', '?')}"
            )
        lines.append("")
    if questions:
        lines.append("OPEN QUESTIONS")
        lines += [
            f"  {q['id']} · {_trunc(q['text'])}"
            + ("" if q.get("resolves_via") else "  [unwatched — no resolves_via surface]")
            for q in questions
        ]
        lines.append("")
    if stuck:
        lines.append("STUCK CLAIMS")
        lines += [f"  {_claim_line(c, with_status=True)}" for c in stuck]
        lines.append("")
    if not lines:
        return "nothing stale"
    return "\n".join(lines).rstrip()


def forecasts_view(root: Path, as_data: bool = False) -> str | dict:
    """Open forecasts (due first) and the labeled calibration record (SPEC §7).

    Both scores ship labeled so nobody mistakes one for the other: sharpness
    is the resolved-yes share of scored resolutions; Brier appears only once
    the record has volume (forecast.BRIER_MIN_RESOLUTIONS) — before that it
    prints n/a, never a number computed on noise.
    """
    from . import forecast as forecast_mod

    load_manifest(root)  # fail early with an actionable error if this isn't a notebook
    due = forecast_mod.due_forecasts(root)
    due_ids = {str(r.get("id")) for r in due}
    rest = [
        r
        for r in forecast_mod.list_forecasts(root)
        if r.get("type") == "Forecast"
        and str(r.get("status", "open")) == "open"
        and str(r.get("id")) not in due_ids
    ]
    rest.sort(key=lambda r: str(r.get("resolves_by", "")))
    cal = forecast_mod.calibration(root)
    if as_data:
        return {"due": due, "open": rest, "calibration": cal}
    lines: list[str] = []
    if due:
        lines.append("DUE FORECASTS")
        for r in due:
            days = r.get("days_left")
            when = f"overdue {-days}d" if isinstance(days, int) and days < 0 else f"in {days}d"
            lines.append(
                f"  {r.get('id', '?')} · resolves {r.get('resolves_by', '?')} ({when}) · "
                f"p={r.get('probability', '?')} c={r.get('confidence', '?')} · "
                f"{_trunc(r.get('description', ''))}"
            )
        lines.append("")
    if rest:
        lines.append("OPEN FORECASTS")
        for r in rest:
            lines.append(
                f"  {r.get('id', '?')} · resolves {r.get('resolves_by', '?')} · "
                f"p={r.get('probability', '?')} c={r.get('confidence', '?')} · "
                f"{_trunc(r.get('description', ''))}"
            )
        lines.append("")
    if not due and not rest:
        lines += ["no open forecasts (forecasts/ is absent or empty)", ""]
    lines.append("RECORD")
    lines.append(
        f"  resolved: {cal['resolved_yes']} yes · {cal['resolved_no']} no · "
        f"{cal['void']} void ({cal['n_scored']} scored)"
    )
    sharp = "n/a" if cal["sharpness"] is None else f"{cal['sharpness']:.2f}"
    lines.append(f"  sharpness (resolved-yes share): {sharp}")
    brier = "n/a" if cal["brier"] is None else f"{cal['brier']:.3f}"
    lines.append(
        f"  Brier (needs ≥{forecast_mod.BRIER_MIN_RESOLUTIONS} resolutions): {brier}"
    )
    return "\n".join(lines)


# --- workspace roster (SPEC §18) ---------------------------------------------


def _idle_suffix(idle: int | None) -> str:
    """" · idle 41d" when the notebook has aged, "" when fresh or undated."""
    return f" · idle {idle}d" if idle else ""


def _current_question_text(page: pages.Page) -> str:
    """The current formulation of a question: the body's lead prose up to the
    first '## ' section (a dated Re-posed block or ## Answer), else the
    description. A re-posed question shows its current wording, not its whole
    journey — the journey stays on the page (mirrors ledgers._question_text)."""
    body = page.body
    if body.lstrip().startswith("## "):
        return str(page.fm.get("description", ""))
    head = body.split("\n## ", 1)[0].strip()
    return head or str(page.fm.get("description", ""))


def _open_questions_roster(root: Path) -> list[dict]:
    """Open questions with their re-pose count (len of the formulations
    history), id order — the roster view's per-notebook question list.
    Same roster rule as `flip show`: open always, dormant only once its
    review date arrives, answered/closed never, unknown statuses visible."""
    out = []
    for page in _pages(root, "questions"):
        if str(page.fm.get("type", "")) != "Question":
            continue
        status = str(page.fm.get("status", "open"))
        if status in ("answered", "closed"):
            continue
        if status == "dormant" and _review_pending(str(page.fm.get("review_by", ""))):
            continue
        out.append(
            {
                "id": page.id,
                "text": _current_question_text(page),
                "repose_count": len(pages.as_list(page.fm.get("formulations"))),
            }
        )
    out.sort(key=lambda q: _id_num(q["id"]))
    return out


def _load_bearing_needing_work(root: Path) -> list[dict]:
    """Load-bearing claims whose verification bar is unmet AND that carry no
    gating (adversarial/recomputation) verification — the same condition that
    would block `flip claim status … verified` (SPEC §7, A2). Terminal
    statuses (retracted/superseded/false-positive) are out; this is the
    roster's "still needs work" list. Recomputed, never trusting the stored
    corroboration count.

    A claim citing only what it is ABOUT (SPEC §7) is measured against the bar
    that applies to it — a severe, surviving attribution test — because the
    corroboration bar is one it could never meet, and a roster that lists a
    claim forever under work nobody can do is a roster people stop reading.
    """
    m = load_manifest(root)
    profile = _profile_or_default(m, root)
    source_fms = _source_rows(root)  # dicts carrying id/grade/independence
    out = []
    for c in _claim_rows(root):
        if not c.get("load_bearing"):
            continue
        status = str(c.get("status", "asserted"))
        if status in ("retracted", "superseded", "false-positive"):
            continue
        corroboration = claims.claim_corroboration(source_fms, c)
        if corroboration is None:
            if not claims.unaudited_subjects(c) or claims.has_gating_verification(c):
                continue
        else:
            linked = claims._linked_fms(source_fms, claims.evidence_ids(c))
            has_grade_a = any(sources_mod.derive_grade(fm) == "A" for fm in linked)
            bar_met = corroboration >= profile.claim_min_independent or (
                profile.claim_grade_a_suffices and has_grade_a
            )
            if bar_met or claims.has_gating_verification(c):
                continue
        out.append(
            {
                "id": c.get("id"),
                "description": str(c.get("description", "")),
                "status": status,
                "corroboration": corroboration,
            }
        )
    out.sort(key=lambda c: _id_num(str(c["id"])))
    return out


def ws_show(
    ws_root: Path,
    open_only: bool = False,
    claims_only: bool = False,
    as_data: bool = False,
) -> str | dict:
    """The merged workspace roster (SPEC §18): across every bound notebook,
    its kind/status/updated-age plus its open questions (with re-pose counts)
    and load-bearing claims still needing work. A view over existing data — no
    new ledger. `--open`/`--claims` narrow to one lane; broken bindings
    (missing / not-a-notebook) are listed but carry no roster.
    """
    from . import workspace

    rows = workspace.ws_rows(ws_root)
    notebooks: list[dict] = []
    for row in rows:
        nb: dict = {
            "handle": row["handle"],
            "path": row["path"],
            "slug": row.get("slug", ""),
            "title": row.get("title", ""),
            "binding": row.get("status", "ok"),
        }
        if row.get("status") == "ok":
            m = load_manifest(ws_root / row["path"])
            nb_root = ws_root / row["path"]
            nb.update(
                kind=m.kind,
                status=m.status,
                updated=m.updated,
                idle_days=idle_days(m.updated),
                open_questions=_open_questions_roster(nb_root),
                claims_needing_work=_load_bearing_needing_work(nb_root),
            )
        else:
            nb.update(
                kind="", status="", updated="", idle_days=None,
                open_questions=[], claims_needing_work=[],
            )
        notebooks.append(nb)
    data = {"workspace_root": str(ws_root), "notebooks": notebooks}
    if as_data:
        return data
    return _render_ws_show(data, open_only=open_only, claims_only=claims_only)


def _ws_header(nb: dict) -> str:
    if nb["binding"] != "ok":
        return f"{nb['handle']} · [{nb['binding']}] · {nb['path']}"
    return " · ".join(
        [nb["handle"], nb["kind"], nb["status"] + _idle_suffix(nb["idle_days"])]
    )


def _render_ws_show(data: dict, open_only: bool, claims_only: bool) -> str:
    show_q = not claims_only
    show_c = not open_only
    nbs = data["notebooks"]
    lines = [data["workspace_root"], f"{len(nbs)} notebook(s) bound"]
    for nb in nbs:
        lines += ["", _ws_header(nb)]
        if nb["binding"] != "ok":
            continue
        shown = False
        if show_q and nb["open_questions"]:
            lines.append(f"  OPEN QUESTIONS ({len(nb['open_questions'])})")
            for q in nb["open_questions"]:
                rep = f" (re-posed {q['repose_count']}×)" if q["repose_count"] else ""
                lines.append(f"    {q['id']} · {_trunc(q['text'])}{rep}")
            shown = True
        if show_c and nb["claims_needing_work"]:
            lines.append(f"  CLAIMS NEEDING WORK ({len(nb['claims_needing_work'])})")
            for c in nb["claims_needing_work"]:
                # None is the roster's way of saying the corroboration axis
                # does not apply to this claim, and it must not print as 0 or
                # as "None" — what it owes is an attribution test (SPEC §7).
                count = c["corroboration"]
                lines.append(
                    f"    {c['id']} · {c['status']} · corroboration "
                    f"{'n/a (subject)' if count is None else count} · "
                    f"{_trunc(c['description'])}"
                )
            shown = True
        if not shown:
            what = (
                "open questions"
                if claims_only
                else "load-bearing claims needing work"
                if open_only
                else "open questions or load-bearing claims needing work"
            )
            lines.append(f"  (no {what})")
    return "\n".join(lines)


# --- generated at-rest views (SPEC §10) --------------------------------------


def regenerate(root: Path, changed: Iterable[str] | None = None) -> None:
    """Rewrite the generated projections after a mutation (SPEC §6.5, §10).

    Writes, in order: log.md at the root (skipped while there are no log
    events, so a fresh notebook stays two files), an index.md listing inside
    each entity directory that exists, and the root index.md *body* — through
    save_manifest, so the manifest frontmatter (including keys flip doesn't
    know) is preserved byte-for-key. Hand-edits to any of these don't survive;
    canonical records (entity pages, JSONL ledgers) are never touched.

    `changed` names the entity directories this mutation touched. None (the
    default) means "assume everything" — the full rebuild, and the only mode
    before 0.19. A caller that knows better passes the touched set — `flip
    log` passes `()` because a log event touches no entity page — and the
    unchanged directories keep their listings, their counts served from the
    derived viewcache. Measured motivation: the full rebuild re-parses every
    page on every mutation, so one log line cost 1.06 s at 301 sources and
    19.8 s at 10,300. Byte-for-byte identical output to the full rebuild as
    long as the caller's `changed` set is honest; when the cache is absent or
    stale for a directory, that directory is recounted from its pages.
    """
    m = load_manifest(root)  # validates the root before writing anything
    try:
        events = read_jsonl(root / LOG_JSONL)
    except ValueError:
        events = []  # corrupt ledger: leave log.md as-is; doctor pinpoints the line
    if events:
        write_log_md(root, events)
    cache = _load_viewcache(root) if changed is not None else {}
    dirty = (
        set(pages.ENTITY_DIRS)
        if changed is None
        else {d for d in changed if d in pages.ENTITY_DIRS}
    )
    counts: dict[str, dict] = {}
    for dirname in pages.ENTITY_DIRS:
        if dirname in dirty or dirname not in cache:
            entries = _pages(root, dirname)
            _write_dir_index(root, dirname, entries)
            info: dict = {"count": len(entries)}
            if dirname == "questions":
                info["open"] = len(_open_questions(root, loaded=entries))
            counts[dirname] = info
        else:
            counts[dirname] = cache[dirname]
    _save_viewcache(root, counts, create=changed is not None)
    save_manifest(root, m, body=_root_body(root, m, events, counts))


def _load_viewcache(root: Path) -> dict:
    """The derived per-directory counts, or {} when absent/corrupt/unreadable
    (every miss is answered by recounting the real pages — the cache can only
    ever save work, never change output)."""
    try:
        data = json.loads((root / VIEWCACHE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(value.get("count"), int):
            out[key] = value
    return out


def _save_viewcache(root: Path, counts: dict[str, dict], create: bool) -> None:
    """Best-effort write; a notebook on read-only media still gets its views.

    Only an incremental caller (`create=True`) may bring the cache into
    existence; a full rebuild refreshes one that is already there — so it can
    never go stale — but creates nothing. That keeps full `regenerate(root)`
    free of side files, which `flip export`'s never-mutates invariant (and
    its test) depends on. Unchanged content is not rewritten.
    """
    path = root / VIEWCACHE
    if not create and not path.is_file():
        return
    text = json.dumps(counts, sort_keys=True) + "\n"
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass


def write_log_md(root: Path, events: list[dict]) -> None:
    """log.md: the OKF-reserved, newest-first view of log/log.jsonl (SPEC §8).

    Shared with the beat layer (beat.regenerate) so beat and notebook logs
    render identically."""
    by_day: dict[str, list[dict]] = {}
    for ev in events:
        day = str(ev.get("ts", ""))[:10] or "undated"
        by_day.setdefault(day, []).append(ev)
    lines = ["# Update Log"]
    for day in sorted(by_day, reverse=True):
        lines += ["", f"## {day}", ""]
        for ev in reversed(by_day[day]):  # newest first within the day
            actor = _one_line(ev.get("actor", ""))
            suffix = f" _({actor})_" if actor else ""
            lines.append(f"* **Update**: {_one_line(ev.get('text', ''))}{suffix}")
    (root / LOG_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_dir_index(root: Path, dirname: str, entries: list[pages.Page]) -> None:
    """<dirname>/index.md: one listing line per entity page, filename order —
    up to INDEX_LIST_CAP. Past the cap the listing shows the newest entries
    (id order, newest first) and counts the rest, naming the list command that
    serves the full roster: a generated listing is a directory sign, and a
    73 KB sign (measured, 301 sources) costs any reader ~18 K tokens.

    Empty structure is worse than absent structure (SPEC §1.10): when the
    directory holds no entity pages, a previously generated listing (its
    frontmatter-free shape marks it as flip's) is deleted rather than left
    stale — authored files, even misplaced ones, are never deleted.
    """
    directory = root / dirname
    if not directory.is_dir():
        return
    index = directory / "index.md"
    if not entries:
        if index.is_file() and is_generated_index(index):
            index.unlink()
        return
    if len(entries) > INDEX_LIST_CAP:
        shown = sorted(entries, key=lambda p: _id_num(p.id or ""), reverse=True)
        shown = shown[:INDEX_LIST_CAP]
    else:
        shown = entries
    lines = [f"# {_DIR_TITLES.get(dirname, dirname.title())}", ""]
    for page in shown:
        label = _one_line(page.fm.get("title") or page.id or page.slug)
        line = f"* [{label}]({page.slug}.md)"
        desc = _one_line(page.fm.get("description", ""))
        if desc:
            line += f" - {desc}"
        lines.append(line)
    if len(entries) > len(shown):
        cmd = _LIST_COMMANDS.get(dirname)
        hint = f" — `{cmd}` lists all" if cmd else ""
        lines += [
            "",
            f"*…and {len(entries) - len(shown)} more "
            f"(newest {len(shown)} listed{hint}).*",
        ]
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_generated_index(index: Path) -> bool:
    """A frontmatter-free index.md is flip's generated listing; anything
    carrying frontmatter (or unreadable) is treated as authored and kept.
    Shared with the beat layer (threads/index.md follows the same rule)."""
    try:
        fm, _body = pages.parse(index.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return not fm


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _root_body(root: Path, m: Manifest, events: list[dict],
               dir_counts: dict[str, dict]) -> str:
    """The root index.md body: title heading + OKF directory listing (SPEC §4).

    Sections appear once they have content — an empty entity directory gets
    no bullet, matching _write_dir_index dropping its listing. Counts arrive
    from regenerate (freshly counted or viewcache-served) so this body never
    forces a parse of every page in the notebook.
    """
    lines = [f"# {m.title or m.slug}"]
    bullets: list[str] = []
    counts = {d: n for d in pages.ENTITY_DIRS
              if (n := dir_counts.get(d, {}).get("count", 0))}
    if "references" in counts:
        bullets.append(
            f"* [References](references/) - {_count(counts['references'], 'captured source')} "
            "with custody and grading"
        )
    if "claims" in counts:
        bullets.append(
            f"* [Claims](claims/) - {_count(counts['claims'], 'claim')} with status and citations"
        )
    if "decisions" in counts:
        bullets.append(
            f"* [Decisions](decisions/) - {_count(counts['decisions'], 'recorded decision')}"
        )
    if "questions" in counts:
        open_n = dir_counts.get("questions", {}).get("open", 0)
        bullets.append(
            f"* [Questions](questions/) - {_count(counts['questions'], 'question')}, {open_n} open"
        )
    if "forecasts" in counts:
        bullets.append(
            f"* [Forecasts](forecasts/) - {_count(counts['forecasts'], 'forecast page')} "
            "with dates and scoring"
        )
    if "commissions" in counts:
        bullets.append(
            f"* [Commissions](commissions/) - "
            f"{_count(counts['commissions'], 'contract')} with lifecycle"
        )
    if "sessions" in counts:
        bullets.append(f"* [Sessions](sessions/) - {_count(counts['sessions'], 'work session')}")
    if (root / LOG_MD).is_file():
        detail = f"{_count(len(events), 'logged event')}, newest first" if events else "work log"
        bullets.append(f"* [Update Log]({LOG_MD}) - {detail}")
    if bullets:
        lines.append("")
        lines += bullets
    return "\n".join(lines) + "\n"
