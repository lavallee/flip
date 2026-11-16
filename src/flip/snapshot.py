"""`flip snapshot`: one whole, unfiltered read of a notebook (SPEC §10).

The list commands each answer one question; a tool that draws a notebook —
a live interface, a report builder, a second agent orienting — needs all of
them at once and from the same instant. This is that read: every page and
ledger loaded once in one process, emitted as one document.

Two properties the callers rely on:

- **Local.** A snapshot is for the machine that holds the notebook. It
  ignores visibility policy and withholds nothing, so it is not a publication
  surface; `flip export json` is the one that applies policy.
- **Read-only and derived.** Nothing is written, and everything flip derives
  elsewhere is derived here the same way (the letter grade, a claim's
  exposure, a lead's state) rather than read from a stored copy.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import (
    claims,
    commissions,
    directives,
    events,
    forecast,
    leads,
    ledgers,
    pages,
    sources,
    stance,
    util,
)
from .manifest import load_manifest

SCHEMA = "flip-snapshot/1"
DEFAULT_LOG_LIMIT = 200

_CUSTODY_KEYS = ("ts", "sha256", "bytes", "tool", "strategy", "status", "mime")
_FOOTNOTE_MARKER_RE = re.compile(r"\[\^[^\]\s]+\]")
_BOLD_FIELD_RE = re.compile(r"^\*\*(Question|Decision|Why|Rejected)\.\*\*\s*(.*)$", re.S)


def _ledger(root: Path, rel: Path | str) -> list[dict]:
    try:
        return util.read_jsonl(root / rel)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line (flip doctor pinpoints it)") from None


def _pages(root: Path, dirname: str, page_type: str | None = None) -> list[pages.Page]:
    found, _errors = pages.iter_pages_tolerant(root, dirname)
    if page_type is not None:
        found = [p for p in found if str(p.fm.get("type", "")) == page_type]
    return found


def _id_key(entity_id: object) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(entity_id or ""))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(entity_id or ""), 0)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _strs(value: object) -> list[str]:
    return [str(v) for v in pages.as_list(value)]


def _dicts(value: object) -> list[dict]:
    return [v for v in pages.as_list(value) if isinstance(v, dict)]


def claim_text(page: pages.Page) -> str:
    """A claim's whole sentence: the lead paragraph of its page with the
    footnote markers removed. The frontmatter `description` is a clipped
    summary of this, and is the fallback only when the page has no prose."""
    lead = page.body.strip("\n").partition("\n\n")[0]
    text = " ".join(_FOOTNOTE_MARKER_RE.sub("", lead).split())
    if not text or text.startswith(("[^", "## ")):
        return str(page.fm.get("description") or "")
    return text


def _custody_by_source(root: Path) -> dict[str, dict]:
    """source id → its primary capture row, by `sources.latest_capture_event`'s
    rule, over one read of the ledger instead of one read per source."""
    best: dict[str, dict] = {}
    for event in _ledger(root, Path("sources") / "_provenance.jsonl"):
        sid = str(event.get("source_id") or "")
        if not sid or not event.get("sha256"):
            continue
        if str(event.get("status") or "") in sources.NON_CAPTURE_STATUSES:
            continue
        if Path(str(event.get("local_path") or "")).name == sources.ENVELOPE_FILENAME:
            continue
        held = best.get(sid)
        if held is None or str(event.get("ts") or "") > str(held.get("ts") or ""):
            best[sid] = event
        elif event.get("ts") == held.get("ts") and (event.get("bytes") or 0) > (
            held.get("bytes") or 0
        ):
            best[sid] = event
    return best


def _sources(root: Path, claim_pages: list[pages.Page], event_rows: list[dict]) -> list[dict]:
    custody = _custody_by_source(root)
    cited_by: dict[str, list[str]] = {}
    for page in claim_pages:
        for sid in claims.source_ids(page.fm):
            if page.id and page.id not in cited_by.setdefault(sid, []):
                cited_by[sid].append(page.id)
    read_by: dict[str, list[dict]] = {}
    kinds: dict[str, str] = {}
    for row in event_rows:
        sid = str(row.get("id") or "")
        if row.get("op") == "source.read" and sid:
            read_by.setdefault(sid, []).append(
                {"actor": row.get("actor"), "ts": row.get("ts")}
            )
        elif row.get("op") == "source.add" and sid and row.get("kind"):
            kinds[sid] = str(row["kind"])
    out = []
    for page in _pages(root, "references", "Source"):
        fm, sid = page.fm, page.id
        event = custody.get(sid)
        text_path = root / "sources" / "text" / f"{sid}.txt"
        support = fm.get("support")
        out.append({
            "id": sid,
            "title": fm.get("title"),
            "description": fm.get("description"),
            # The page does not store the capture kind; the event that
            # recorded the capture does. Null for sources older than the ledger.
            "kind": fm.get("kind") or kinds.get(sid),
            "url": fm.get("resource") or fm.get("url") or (event or {}).get("url"),
            "local": fm.get("local"),
            "status": fm.get("status"),
            "grade": sources.derive_grade(fm),
            "independence": fm.get("independence"),
            "freshness": fm.get("freshness"),
            "support": support if isinstance(support, dict) else None,
            "notes": fm.get("notes"),
            "path": _rel(root, page.path),
            "by": pages.generated_by(fm) or None,
            "at": pages.generated_at(fm) or None,
            "custody": {k: event.get(k) for k in _CUSTODY_KEYS} if event else None,
            "text": _rel(root, text_path) if text_path.is_file() else None,
            "cited_by": sorted(cited_by.get(sid, []), key=_id_key),
            "read_by": read_by.get(sid, []),
        })
    out.sort(key=lambda r: _id_key(r["id"]))
    return out


def _claims(root: Path, claim_pages: list[pages.Page]) -> list[dict]:
    out = []
    for page in claim_pages:
        fm = page.fm
        out.append({
            "id": page.id,
            "text": claim_text(page),
            "summary": fm.get("description"),
            "status": fm.get("status"),
            "load_bearing": bool(fm.get("load_bearing", False)),
            "sources": claims.evidence_ids(fm),
            "about": claims.subject_ids(fm),
            "corroboration": fm.get("independent_corroboration"),
            "exposure": stance.derive_exposure(fm),
            "value": fm.get("value"),
            "unit": fm.get("unit"),
            "notes": fm.get("notes"),
            "stances": stance.stance_records(fm),
            "rivals": stance.rival_records(fm),
            "tests": stance.test_records(fm),
            "verified": _dicts(fm.get("verified")),
            "derives_from": claims.derivation_ids(fm),
            "path": _rel(root, page.path),
            "by": pages.generated_by(fm) or None,
            "at": pages.generated_at(fm) or None,
        })
    out.sort(key=lambda r: _id_key(r["id"]))
    return out


def _questions(root: Path) -> list[dict]:
    out = []
    for page in _pages(root, "questions", "Question"):
        fm = page.fm
        out.append({
            "id": page.id,
            "text": ledgers._question_text(page),
            "status": str(fm.get("status", "open")),
            "path": _rel(root, page.path),
            "by": pages.generated_by(fm) or None,
            "at": pages.generated_at(fm) or None,
            "review_by": fm.get("review_by"),
            "reopen_when": _strs(fm.get("reopen_when")),
            "resolves_via": _strs(fm.get("resolves_via")),
            "formulations": _dicts(fm.get("formulations")),
        })
    out.sort(key=lambda r: _id_key(r["id"]))
    return out


def _decision_fields(body: str) -> dict[str, str]:
    """The **Question.** / **Decision.** / **Why.** paragraphs flip writes on a
    decision page, read back whole (frontmatter keeps only a clipped summary)."""
    found: dict[str, str] = {}
    for paragraph in body.split("\n\n"):
        m = _BOLD_FIELD_RE.match(paragraph.strip())
        if m and m.group(1).lower() not in found:
            found[m.group(1).lower()] = m.group(2).strip()
    return found


def _decisions(root: Path) -> list[dict]:
    out = []
    for page in _pages(root, "decisions", "Decision"):
        fm = page.fm
        fields = _decision_fields(page.body)
        out.append({
            "id": page.id,
            "question": fm.get("question") or fields.get("question"),
            "decision": fields.get("decision") or fm.get("description"),
            "why": fields.get("why"),
            "rejected": _strs(fm.get("alternatives_rejected")),
            "path": _rel(root, page.path),
            "by": pages.generated_by(fm) or None,
            "at": pages.generated_at(fm) or None,
        })
    out.sort(key=lambda r: _id_key(r["id"]))
    return out


def _session_goal(body: str) -> str | None:
    if "## Goal" not in body:
        return None
    section = body.split("## Goal", 1)[1].split("\n## ", 1)[0].strip()
    return section or None


def _sessions(root: Path) -> list[dict]:
    out = []
    for page in _pages(root, "sessions"):  # filename order is start order
        fm = page.fm
        out.append({
            "path": _rel(root, page.path),
            "actor": pages.generated_by(fm) or fm.get("actor"),
            "model": fm.get("model"),
            "started": fm.get("started"),
            "ended": fm.get("ended"),
            "goal": _session_goal(page.body),
            "workflow": fm.get("workflow"),
            "phase": fm.get("phase"),
            "item": fm.get("item"),
        })
    return out


def snapshot(root: Path, log_limit: int = DEFAULT_LOG_LIMIT) -> dict:
    """The whole notebook as one `flip-snapshot/1` document."""
    root = util.require_notebook_root(root)
    if log_limit < 0:
        raise SystemExit("--log-limit takes zero or a positive number of rows")
    m = load_manifest(root)
    claim_pages = _pages(root, "claims", "Claim")
    event_rows = _ledger(root, events.EVENTS)
    log_rows = _ledger(root, ledgers.LOG)
    return {
        "schema": SCHEMA,
        "generated": util.utc_now(),
        "root": str(root),
        "notebook": {
            "slug": m.slug,
            "uid": m.uid or None,
            "title": m.title or None,
            "kind": m.kind,
            "status": m.status,
            "created": m.created or None,
            "updated": m.updated or None,
            "visibility": m.visibility,
            "workflow": m.workflow or None,
            "idle_days": util.idle_days(m.updated),
        },
        "sources": _sources(root, claim_pages, event_rows),
        "claims": _claims(root, claim_pages),
        "questions": _questions(root),
        "decisions": _decisions(root),
        "sessions": _sessions(root),
        "forecasts": forecast.list_forecasts(root),
        "commissions": commissions.list_commissions(root),
        "passed": [
            {key: row.get(key) for key in ("ts", "text", "reason", "url", "actor")}
            for row in _ledger(root, ledgers.PASSED)
        ],
        "leads": leads.list_leads(root, include_all=True),
        "directives": directives.list_directives(root, include_all=True),
        "log": log_rows[-log_limit:] if log_limit else [],
    }


__all__ = ["DEFAULT_LOG_LIMIT", "SCHEMA", "claim_text", "snapshot"]
