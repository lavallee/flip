"""Computed hot/cold views for `flip show` (SPEC §10).

Views are computed, never stored: each function reads whatever ledgers exist
under the notebook root and assembles a windowed projection. Every ledger is
optional — a missing file simply contributes nothing. Each view returns a
rendered plain-text string, or a plain dict when `as_data=True` (for `--json`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .manifest import Manifest, load_manifest
from .profiles import Profile, load_profile
from .util import age_months, read_jsonl

# Claim status enum (SPEC §7.2), in display order.
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


def _trunc(text: object, width: int = TRUNCATE_WIDTH) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= width:
        return s
    return s[: width - 1].rstrip() + "…"


def _read(root: Path, rel: str) -> list[dict]:
    """Read an optional ledger; a corrupt line becomes an actionable exit."""
    try:
        return read_jsonl(root / rel)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line (flip doctor pinpoints it)") from None


def _manifest(root: Path) -> Manifest:
    try:
        return load_manifest(root)
    except SystemExit:
        raise
    except Exception as e:  # e.g. notebook.toml missing required fields
        raise SystemExit(
            f"{root / 'notebook.toml'} is not a valid manifest ({e}); run `flip doctor`"
        ) from None


def _profile_or_default(m: Manifest, root: Path) -> Profile:
    """Views tolerate an unresolvable kind; doctor is where that gets flagged."""
    try:
        return load_profile(m.kind, root)
    except SystemExit:
        return Profile(id=m.kind)


def _open_questions(root: Path) -> list[dict]:
    """Last-event-wins per id: a question is open unless its latest event in
    log/questions.jsonl carries status "answered" (ledgers.py convention)."""
    latest: dict[str, dict] = {}
    texts: dict[str, str] = {}
    order: list[str] = []
    for ev in _read(root, "log/questions.jsonl"):
        qid = ev.get("id")
        if not qid:
            continue
        if qid not in latest:
            order.append(qid)
        latest[qid] = ev
        if ev.get("text"):
            texts[qid] = ev["text"]
    return [
        {"id": qid, "text": texts.get(qid, ""), "ts": latest[qid].get("ts", "")}
        for qid in order
        if latest[qid].get("status") != "answered"
    ]


def _claims_needing_work(root: Path) -> list[dict]:
    claims = [
        c for c in _read(root, "analysis/claims.jsonl") if c.get("status") in NEEDS_WORK_STATUSES
    ]
    claims.sort(key=lambda c: not c.get("load_bearing", False))  # load-bearing first, stable
    return claims


def _latest_session(root: Path) -> str | None:
    sessions = root / "log" / "sessions"
    if not sessions.is_dir():
        return None
    files = [p for p in sessions.iterdir() if p.is_file() and not p.name.startswith(".")]
    if not files:
        return None
    newest = max(files, key=lambda p: p.name)  # names are UTC-stamped (SPEC §3)
    return newest.relative_to(root).as_posix()


def _stale_sources(rows: list[dict], freshness_months: int) -> list[dict]:
    """Sources judged dated, or whose ledger date is at/past the profile threshold."""
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
    parts.append(_trunc(c.get("text", "")))
    sources = c.get("sources") or []
    parts.append("sources: " + (", ".join(str(s) for s in sources) if sources else "none"))
    parts.append(f"corroboration: {c.get('independent_corroboration', 0)}")
    return " · ".join(parts)


def hot_view(root: Path, as_data: bool = False) -> str | dict:
    """Current focus: open questions, claims needing work, recent activity."""
    m = _manifest(root)
    profile = _profile_or_default(m, root)
    questions = _open_questions(root)
    claims = _claims_needing_work(root)
    recent = _read(root, "log/log.jsonl")[-RECENT_LOG_COUNT:]
    session = _latest_session(root)
    dated = _stale_sources(_read(root, "sources/ledger.jsonl"), profile.freshness_months)
    if as_data:
        return {
            "slug": m.slug,
            "kind": m.kind,
            "status": m.status,
            "updated": m.updated,
            "open_questions": questions,
            "claims_needing_work": claims,
            "recent_log": recent,
            "latest_session": session,
            "dated_sources": len(dated),
        }
    lines = [" · ".join([m.slug, m.kind, m.status, m.updated])]
    if questions:
        lines += ["", "OPEN QUESTIONS"]
        lines += [f"  {q['id']} · {_trunc(q['text'])}" for q in questions]
    if claims:
        lines += ["", "CLAIMS NEEDING WORK"]
        lines += [f"  {_claim_line(c, with_status=True)}" for c in claims]
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
    _manifest(root)  # fail early with an actionable error if this isn't a notebook
    claims = _read(root, "analysis/claims.jsonl")
    groups: dict[str, list[dict]] = {}
    for c in claims:
        groups.setdefault(str(c.get("status", "unknown")), []).append(c)
    order = [s for s in CLAIM_STATUS_ORDER if s in groups]
    order += [s for s in groups if s not in CLAIM_STATUS_ORDER]
    if as_data:
        return {"total": len(claims), "by_status": {s: groups[s] for s in order}}
    if not claims:
        return "no claims recorded (analysis/claims.jsonl is absent or empty)"
    lines: list[str] = []
    for status in order:
        lines.append(status.upper())
        lines += [f"  {_claim_line(c)}" for c in groups[status]]
        lines.append("")
    return "\n".join(lines).rstrip()


def stale_view(root: Path, as_data: bool = False) -> str | dict:
    """What has gone cold: dated sources, open questions, stuck claims."""
    m = _manifest(root)
    profile = _profile_or_default(m, root)
    dated = _stale_sources(_read(root, "sources/ledger.jsonl"), profile.freshness_months)
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
        lines += [f"  {q['id']} · {_trunc(q['text'])}" for q in questions]
        lines.append("")
    if stuck:
        lines.append("STUCK CLAIMS")
        lines += [f"  {_claim_line(c, with_status=True)}" for c in stuck]
        lines.append("")
    if not lines:
        return "nothing stale"
    return "\n".join(lines).rstrip()
