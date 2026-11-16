"""Session entity pages — sessions/ at the notebook top level (SPEC §3, §8).

One markdown page per working episode, named `<UTC stamp>-<slug>.md`
(util.stamp_slug has minute precision, so filenames sort chronologically).
Sessions are entity pages like any other: YAML frontmatter (`type: Work
Session`, `generated: {by, at}`, `model`, `tools`, `started`, `ended`, plus
optional workflow/phase/item coordinates) written and read through the pages
layer, body owned by whoever ran the session.

`end_session` sets `ended` and a conservative activity receipt in the
FRONTMATTER (current-state metadata any OKF consumer can read) and appends the
summary to the body; foreign frontmatter keys and the existing body survive
(round-trip rule, SPEC §6.6).
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path

from . import events, manifest, pages, util, views

SESSIONS = Path("sessions")

_SECTION_STUBS = "## Goal\n\n## Prompt\n\n## Key outputs\n\n## Transcript\n"


def _clean_slug(slug: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", (slug or "").lower()).strip("-.")
    if not cleaned:
        raise SystemExit(
            "empty or unusable session slug; use letters/digits/dashes, e.g. 'corpus-sweep'"
        )
    return cleaned


def start_session(
    root: Path,
    slug: str,
    model: str | None = None,
    tools: list[str] | str | None = None,
    workflow: str | None = None,
    phase: str | None = None,
    item: str | None = None,
) -> Path:
    """Create sessions/<stamp>-<slug>.md with frontmatter and section stubs.

    Frontmatter carries type, actor, model (if given), tools (if given),
    started. Returns the path written.
    """
    root = util.require_notebook_root(root)  # before any write: no stray sessions/ dirs
    slug = _clean_slug(slug)
    path = root / SESSIONS / f"{util.stamp_slug()}-{slug}.md"
    if path.exists():
        raise SystemExit(
            f"session file already exists: {path}; "
            "pick a different slug (one session per slug per minute)"
        )
    fm: dict = {"type": "Work Session", "generated": util.generated_now()}
    if model:
        fm["model"] = str(model)
    if tools:
        fm["tools"] = [str(t) for t in tools] if isinstance(tools, (list, tuple)) else str(tools)
    if workflow or phase:
        from . import workflows

        selected = workflow or manifest.load_manifest(root).workflow
        if not selected:
            raise SystemExit("--phase needs --workflow or a workflow pin in index.md")
        definition = workflows.load_workflow(selected, root)
        known_phases = {entry.id for entry in definition.phases}
        if phase is None:
            suggestion = workflows.next_phase(root, definition.pin)
            if suggestion.get("complete"):
                raise SystemExit(
                    f"workflow {definition.pin} completed its terminal phase; choose a phase "
                    "explicitly or start a different workflow"
                )
            phase = str(suggestion["phase"])
        if phase not in known_phases:
            raise SystemExit(
                f"unknown phase '{phase}' for {definition.pin}; known: "
                f"{', '.join(sorted(known_phases))}"
            )
        fm["workflow"] = definition.pin
        fm["phase"] = phase
    if item:
        fm["item"] = str(item)
    from . import extensions
    enabled = [plugin.pin for plugin in extensions.enabled_plugins(root)]
    if enabled:
        fm["extensions"] = enabled
    # Nanosecond local baseline avoids falsely counting a page created earlier
    # in the same UTC second. It moves into the close receipt when the session
    # ends; old open sessions without it fall back to their ISO started time.
    fm["receipt_opened_ns"] = time.time_ns()
    fm["started"] = util.utc_now()
    pages.write_page(path, fm, _SECTION_STUBS)
    manifest.touch_updated(root)
    views.regenerate(root, changed=("sessions",))
    events.emit(root, "session.start", path=path.relative_to(root).as_posix(),
                model=fm.get("model"), workflow=fm.get("workflow"),
                phase=fm.get("phase"), item=fm.get("item"))
    return path


# Session filenames are <stamp>-<slug>.md where the stamp is exactly the 15
# characters of util.stamp_slug() ("%Y-%m-%dT%H%M", e.g. 2026-07-10T1431).
_STAMP_LEN = 15
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{4}$")


def _slug_of(filename: str) -> str | None:
    """The exact slug of a session filename, or None if it isn't one."""
    if not filename.endswith(".md"):
        return None
    stem = filename[: -len(".md")]
    stamp, sep, slug = stem[:_STAMP_LEN], stem[_STAMP_LEN : _STAMP_LEN + 1], stem[_STAMP_LEN + 1 :]
    if sep != "-" or not slug or not _STAMP_RE.match(stamp):
        return None
    return slug


def _find_session(root: Path, path_or_slug: Path | str) -> Path:
    p = Path(str(path_or_slug))
    for candidate in (p, root / p, root / SESSIONS / p.name):
        if candidate.is_file():
            return candidate
    sessions_dir = root / SESSIONS
    slug = re.sub(r"[^a-z0-9._-]+", "-", str(path_or_slug).lower()).strip("-.")
    if slug and sessions_dir.is_dir():
        # Exact slug equality — "sweep" must not match "...-corpus-sweep.md".
        # Stamped names sort chronologically, so the lexical max is the newest.
        matches = [p for p in sessions_dir.iterdir() if p.is_file() and _slug_of(p.name) == slug]
        if matches:
            return max(matches, key=lambda p: p.name)
    raise SystemExit(
        f"no session file matching '{path_or_slug}' under {SESSIONS}/; "
        "pass the path returned by `flip session start`, or the slug it was started with"
    )


def attach_transcript(
    root: Path, path_or_slug: Path | str, source_id: str, local: str, slug: str
) -> Path:
    """Point a session page at the transcript captured for it (SPEC §8).

    Sets `transcript: {id, local}` in the frontmatter — current-state metadata
    any OKF consumer can read — and fills the `## Transcript` stub with a link
    to the source page. The session keeps the summary; the transcript keeps
    the conversation; the id is what lets a claim cite the second while the
    first stays a working record.

    The prose link goes to the references/ page rather than to the raw bytes:
    that page is where the pinned passages are readable, and the raw path is
    one line below it for anyone who wants the file itself.
    """
    root = util.require_notebook_root(root)
    path = _find_session(root, path_or_slug)
    page = pages.read_page(path)
    page.fm["transcript"] = {"id": source_id, "local": local}
    pointer = (
        f"Captured verbatim as [{source_id}](../references/{slug}.md) — "
        f"cite passages as `{source_id}§<label>`.\n\nRaw bytes: `{local}`"
    )
    body = page.body.strip("\n")
    if "## Transcript" in body:
        head, _, tail = body.partition("## Transcript")
        rest = tail.split("\n## ", 1)
        following = f"\n## {rest[1]}" if len(rest) > 1 else ""
        body = f"{head}## Transcript\n\n{pointer}\n{following}"
    else:
        body = (body + "\n\n" if body else "") + f"## Transcript\n\n{pointer}\n"
    pages.write_page(path, page.fm, body)
    manifest.touch_updated(root)
    views.regenerate(root, changed=("sessions",))
    events.emit(root, "session.transcript", path=path.relative_to(root).as_posix(),
                source=source_id, local=local)
    return path


_RECEIPT_LEDGERS = (
    Path("log/log.jsonl"), Path("log/passed.jsonl"),
    Path("log/resolutions.jsonl"), Path("log/declined-forecasts.jsonl"),
    Path("sources/_provenance.jsonl"), Path("derived/_derivations.jsonl"),
)
_RECEIPT_DIRS = (
    "references", "claims", "questions", "decisions", "forecasts", "commissions",
)


def _parse_time(value: object) -> datetime | None:
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _receipt(root: Path, session_path: Path, started: object, opened_ns: object,
             outputs: list[str] | None, checks: list[str] | None) -> dict:
    since = _parse_time(started)
    by_ledger: dict[str, int] = {}
    if since is not None:
        for rel in _RECEIPT_LEDGERS:
            count = 0
            try:
                rows = util.read_jsonl(root / rel)
            except (OSError, ValueError):
                continue  # doctor owns malformed-ledger reporting
            for row in rows:
                event_time = next(
                    (_parse_time(row.get(key)) for key in ("ts", "at", "captured_at", "created")
                     if row.get(key)),
                    None,
                )
                if event_time is not None and event_time >= since:
                    count += 1
            if count:
                by_ledger[rel.as_posix()] = count
    artifacts: list[str] = []
    try:
        threshold_ns = int(opened_ns)
    except (TypeError, ValueError):
        threshold_ns = int(since.timestamp() * 1_000_000_000) if since is not None else None
    if threshold_ns is not None:
        for dirname in _RECEIPT_DIRS:
            directory = root / dirname
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.md")):
                if path.name == "index.md":  # generated view, never a canonical artifact
                    continue
                try:
                    changed = path.stat().st_mtime_ns >= threshold_ns
                except OSError:
                    changed = False
                if changed and path != session_path:
                    artifacts.append(path.relative_to(root).as_posix())
    event_count = sum(by_ledger.values())
    if event_count or artifacts:
        floor = (
            f"observed {event_count} append-only event(s) and "
            f"{len(artifacts)} changed canonical entity page(s) during this session"
        )
    else:
        floor = "no append-only events or changed canonical entity pages were observed"
    return {
        "protocol": "flip-session-receipt/1",
        "observed_since": str(started or ""),
        "observed_since_ns": threshold_ns,
        "events": {"count": event_count, "by_ledger": by_ledger},
        "artifacts": artifacts,
        "outputs": [str(value) for value in (outputs or [])],
        "checks": [str(value) for value in (checks or [])],
        "materiality_floor": floor,
        "does_not_establish": "reader relevance, research quality, demand, or external outcome",
    }


def end_session(root: Path, path_or_slug: Path | str, summary: str,
                outputs: list[str] | None = None,
                checks: list[str] | None = None) -> Path:
    """Close a session: set `ended` in the frontmatter, append `## Summary`.

    `path_or_slug` may be the session file path (absolute, root-relative, or
    bare filename) or the exact slug it was started with — among sessions
    whose slug matches exactly, the newest wins. Only the `ended` key changes;
    everything else round-trips (SPEC §6.6). Returns the path written.
    """
    root = util.require_notebook_root(root)
    summary = (summary or "").strip()
    if not summary:
        raise SystemExit("empty session summary; say what the session accomplished")
    path = _find_session(root, path_or_slug)
    page = pages.read_page(path)
    if page.fm.get("ended"):
        raise SystemExit(f"session already ended: {path}; start a new session instead")
    page.fm["ended"] = util.utc_now()
    opened_ns = page.fm.pop("receipt_opened_ns", None)
    draft = _receipt(root, path, page.fm.get("started"), opened_ns, outputs, checks)
    from . import extensions
    enriched, extension_trace = extensions.filter_receipt(root, draft)
    # Filters may add namespaced receipt data, but the measured core floor is
    # not theirs to erase or rewrite.
    enriched.update(draft)
    if extension_trace:
        enriched["extension_trace"] = extension_trace
    page.fm["receipt"] = enriched
    # read_page keeps the blank separator line write_page emits as a leading
    # newline on the body; normalize so rewrites don't accrete blank lines.
    base = page.body.strip("\n")
    body = (base + "\n\n" if base else "") + f"## Summary\n{summary}\n"
    pages.write_page(path, page.fm, body)
    manifest.touch_updated(root)
    views.regenerate(root, changed=("sessions",))
    events.emit(root, "session.end", path=path.relative_to(root).as_posix(), text=summary)
    return path
