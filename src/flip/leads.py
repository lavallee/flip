"""The leads ledger: candidate sources seen but not yet dealt with (SPEC §8).

`flip find` used to print its candidates and forget them, so the same search
had to be re-run to see what was left to triage, and a second reader of the
notebook never saw the candidates at all. Every candidate now lands as one row
in log/leads.jsonl, and `flip lead add` records one found any other way.

The ledger is append-only and holds two row shapes:

    {ts, query?, url, title?, snippet?, note?, actor}       a lead
    {ts, event: "dismiss", url, reason?, actor}             a dismissal

A lead's state is derived on every read and never stored, so it cannot drift
from the records that decide it:

    captured    a source page holds that URL (the row carries `source_id`)
    passed      log/passed.jsonl names that URL
    dismissed   a dismiss row exists for it
    open        none of the above — still to triage

One URL is one lead: a URL already in the ledger is not added again, however
many searches surface it.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import events, manifest, pages, util

LEADS = Path("log") / "leads.jsonl"
PASSED = Path("log") / "passed.jsonl"
PROVENANCE = Path("sources") / "_provenance.jsonl"

STATES = ("open", "captured", "passed", "dismissed")


def url_key(url: object) -> str:
    """The form two spellings of one address share: scheme and host
    lowercased, fragment and trailing slash dropped. Used only to compare —
    the ledger keeps every URL exactly as it was given."""
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc:
        return text.rstrip("/")
    return urlunsplit((
        parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "",
    ))


def _rows(root: Path) -> list[dict]:
    try:
        return util.read_jsonl(root / LEADS)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line (flip doctor pinpoints it)") from None


def _is_dismissal(row: dict) -> bool:
    return str(row.get("event") or "") == "dismiss"


def _append_lead(root: Path, known: set[str], url: str, **fields) -> dict | None:
    key = url_key(url)
    if not key or key in known:
        return None
    known.add(key)
    row: dict = {"ts": util.utc_now()}
    for name in ("query", "url", "title", "snippet", "note"):
        value = url if name == "url" else fields.get(name)
        if value:
            row[name] = str(value)
    row["actor"] = util.detect_actor()
    util.append_jsonl(root / LEADS, row)
    events.emit(root, "lead.add", url=row["url"], title=row.get("title"),
                query=row.get("query"), note=row.get("note"))
    return row


def record_candidates(root: Path, query: str, candidates: list[dict]) -> list[dict]:
    """Keep the candidates one search returned; returns the rows added.

    A URL already in the ledger is skipped, in any state: a lead that was
    dismissed or captured is not reopened by turning up in another search.
    """
    if not candidates:
        return []
    known = {url_key(r.get("url")) for r in _rows(root) if not _is_dismissal(r)}
    added = []
    for candidate in candidates:
        row = _append_lead(
            root, known, str(candidate.get("url") or ""), query=query,
            title=candidate.get("title"), snippet=candidate.get("snippet"),
        )
        if row is not None:
            added.append(row)
    if added:
        manifest.touch_updated(root)
    return added


def add_lead(root: Path, url: str, title: str | None = None, note: str | None = None) -> dict:
    """Record one lead by hand. Refuses a URL the ledger already holds."""
    root = util.require_notebook_root(root)
    url = (url or "").strip()
    if not url:
        raise SystemExit("empty URL; pass the address of the candidate source")
    known = {url_key(r.get("url")) for r in _rows(root) if not _is_dismissal(r)}
    row = _append_lead(root, known, url, title=(title or "").strip(),
                       note=(note or "").strip())
    if row is None:
        state = next(
            (lead["state"] for lead in list_leads(root, include_all=True)
             if url_key(lead["url"]) == url_key(url)), "open",
        )
        raise SystemExit(
            f"{url} is already a lead ({state}); `flip lead list --all` shows it"
        )
    manifest.touch_updated(root)
    return row


def dismiss_lead(root: Path, url: str, reason: str | None = None) -> dict:
    """Dismiss a lead: not worth capturing, and not worth a `flip pass` row.

    Appends a dismiss row; the lead row itself is never rewritten. Refuses a
    URL that is not a lead, and one already dismissed. Only the ledger is
    consulted, so a dismissal costs the same in a notebook of ten sources or
    ten thousand; dismissing a lead that was since captured or passed is
    harmless, because those states take precedence when state is derived.
    """
    root = util.require_notebook_root(root)
    url = (url or "").strip()
    key = url_key(url)
    rows = _rows(root)
    lead = next(
        (r for r in rows if not _is_dismissal(r) and url_key(r.get("url")) == key), None
    )
    if lead is None:
        raise SystemExit(
            f"{url} is not a lead in this notebook; `flip lead list --all` shows what is"
        )
    if any(_is_dismissal(r) and url_key(r.get("url")) == key for r in rows):
        raise SystemExit(f"{lead['url']} is already dismissed; nothing to do")
    row: dict = {"ts": util.utc_now(), "event": "dismiss", "url": lead["url"]}
    reason = (reason or "").strip()
    if reason:
        row["reason"] = reason
    row["actor"] = util.detect_actor()
    util.append_jsonl(root / LEADS, row)
    manifest.touch_updated(root)
    events.emit(root, "lead.dismiss", url=lead["url"], reason=reason)
    return row


def _source_urls(root: Path) -> dict[str, str]:
    """url key → source id, over every address a captured source is known by:
    the page's own coordinate and each URL its capture rows recorded."""
    out: dict[str, str] = {}
    page_ids = set()
    source_pages, _errors = pages.iter_pages_tolerant(root, "references")
    for page in source_pages:
        if not page.id:
            continue
        page_ids.add(page.id)
        for field in ("resource", "url"):
            key = url_key(page.fm.get(field))
            if key:
                out.setdefault(key, page.id)
    try:
        provenance = util.read_jsonl(root / PROVENANCE)
    except ValueError:
        provenance = []  # doctor reports the bad line; the pages still answer
    for event in provenance:
        sid = str(event.get("source_id") or "")
        if sid not in page_ids or not event.get("sha256"):
            continue
        for field in ("url", "canonical_url"):
            key = url_key(event.get(field))
            if key:
                out.setdefault(key, sid)
    return out


def list_leads(root: Path, include_all: bool = False) -> list[dict]:
    """Leads with their derived state, oldest first.

    Each row: {url, title, snippet, query, note, ts, actor, state, source_id,
    reason} — `source_id` set when captured, `reason` when passed or
    dismissed and one was given. Open leads only unless `include_all`.
    """
    rows = _rows(root)
    if not rows:
        return []
    dismissed: dict[str, dict] = {}
    for row in rows:
        if _is_dismissal(row):
            dismissed[url_key(row.get("url"))] = row
    captured = _source_urls(root)
    try:
        passed_rows = util.read_jsonl(root / PASSED)
    except ValueError:
        passed_rows = []
    passed = {url_key(r.get("url")): r for r in passed_rows if r.get("url")}
    out = []
    for row in rows:
        if _is_dismissal(row):
            continue
        key = url_key(row.get("url"))
        state, source_id, reason = "open", None, None
        if key in captured:
            state, source_id = "captured", captured[key]
        elif key in passed:
            state, reason = "passed", passed[key].get("reason")
        elif key in dismissed:
            state, reason = "dismissed", dismissed[key].get("reason")
        if state != "open" and not include_all:
            continue
        out.append({
            "url": str(row.get("url") or ""),
            "title": row.get("title"),
            "snippet": row.get("snippet"),
            "query": row.get("query"),
            "note": row.get("note"),
            "ts": row.get("ts"),
            "actor": row.get("actor"),
            "state": state,
            "source_id": source_id,
            "reason": reason,
        })
    return out


__all__ = [
    "LEADS", "STATES", "add_lead", "dismiss_lead", "list_leads", "record_candidates",
    "url_key",
]
