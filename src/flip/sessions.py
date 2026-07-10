"""Session records — log/sessions/ (SPEC §8).

One markdown file per working episode, named `<UTC stamp>-<slug>.md`
(util.stamp_slug has minute precision, so filenames sort chronologically).
The frontmatter is YAML-ish — plain `key: value` lines between `---` fences —
written for humans and agents to read; flip never parses it back.

`end_session` never edits the frontmatter: it appends a closing block at the
end of the file — `---`, `ended: <ts>`, then `## Summary` — so session files
stay append-friendly like the ledgers.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import manifest, util

SESSIONS = Path("log") / "sessions"

_SECTION_STUBS = "\n## Goal\n\n## Prompt\n\n## Key outputs\n\n## Transcript\n"


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
    """Create log/sessions/<stamp>-<slug>.md with frontmatter and section stubs.

    Frontmatter carries actor, model (if given), tools (if given), started.
    Returns the path written.
    """
    root = util.require_notebook_root(root)
    slug = _clean_slug(slug)
    path = root / SESSIONS / f"{util.stamp_slug()}-{slug}.md"
    if path.exists():
        raise SystemExit(
            f"session file already exists: {path}; "
            "pick a different slug (one session per slug per minute)"
        )
    lines = ["---", f"actor: {util.detect_actor()}"]
    if model:
        lines.append(f"model: {model}")
    if tools:
        if isinstance(tools, (list, tuple)):
            lines.append("tools: [" + ", ".join(str(t) for t in tools) + "]")
        else:
            lines.append(f"tools: {tools}")
    lines.append(f"started: {util.utc_now()}")
    lines.append("---")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n" + _SECTION_STUBS, encoding="utf-8")
    manifest.touch_updated(root)
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
    """Close a session: append `---` / `ended: <ts>` / `## Summary` to its file.

    `path_or_slug` may be the session file path (absolute, root-relative, or
    bare filename) or the exact slug it was started with — among sessions
    whose slug matches exactly, the newest wins. Returns the path appended to.
    """
    root = util.require_notebook_root(root)
    summary = (summary or "").strip()
    if not summary:
        raise SystemExit("empty session summary; say what the session accomplished")
    path = _find_session(root, path_or_slug)
    content = path.read_text(encoding="utf-8")
    if re.search(r"^ended: ", content, flags=re.MULTILINE):
        raise SystemExit(f"session already ended: {path}; start a new session instead")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n---\nended: {util.utc_now()}\n\n## Summary\n{summary}\n")
    manifest.touch_updated(root)
    return path
