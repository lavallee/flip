"""Session entity pages — sessions/ at the notebook top level (SPEC §3, §8).

One markdown page per working episode, named `<UTC stamp>-<slug>.md`
(util.stamp_slug has minute precision, so filenames sort chronologically).
Sessions are entity pages like any other: YAML frontmatter (`type: Work
Session`, `actor`, `model`, `tools`, `started`, `ended`) written and read
through the pages layer, body owned by whoever ran the session.

`end_session` sets `ended` in the FRONTMATTER (current-state metadata any
OKF consumer can read) and appends the summary to the body; foreign
frontmatter keys and the existing body survive (round-trip rule, SPEC §6.6).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import manifest, pages, util, views

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
    fm: dict = {"type": "Work Session", "actor": util.detect_actor()}
    if model:
        fm["model"] = str(model)
    if tools:
        fm["tools"] = [str(t) for t in tools] if isinstance(tools, (list, tuple)) else str(tools)
    fm["started"] = util.utc_now()
    pages.write_page(path, fm, _SECTION_STUBS)
    manifest.touch_updated(root)
    views.regenerate(root)
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


def end_session(root: Path, path_or_slug: Path | str, summary: str) -> Path:
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
    # read_page keeps the blank separator line write_page emits as a leading
    # newline on the body; normalize so rewrites don't accrete blank lines.
    base = page.body.strip("\n")
    body = (base + "\n\n" if base else "") + f"## Summary\n{summary}\n"
    pages.write_page(path, page.fm, body)
    manifest.touch_updated(root)
    views.regenerate(root)
    return path
