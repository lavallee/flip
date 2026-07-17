"""Workspaces — many notebooks sharing one vault or repo (SPEC §18).

A workspace root carries `.flip/workspace.toml`, the local table binding
short handles to notebook paths. Handles are importer-owned petnames — the
same model as git remote names: the notebook's manifest slug is only a
*suggestion*, the binding that resolves `recipes:A3` lives here, and it
never ships inside a bundle (`.flip/` is excluded from every export).

Read with stdlib tomllib; written by a deliberately minimal writer (the
schema is two tables of scalars). Hand edits are read fine, but comments
are not preserved across `flip ws` rewrites — the emitted header says so.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .util import (
    HANDLE_RE,
    WORKSPACE_FILE,
    find_workspace_root,
    is_workspace_root,
)

__all__ = [
    "WORKSPACE_FILE", "WORKSPACE_VERSION", "Workspace",
    "is_workspace_root", "find_workspace_root", "require_workspace_root",
    "require_valid_handle", "load_workspace", "save_workspace",
    "discover_notebooks", "default_handle", "ws_init", "ws_add",
    "ws_rename", "ws_rm", "ws_rows", "ensure_qualified_aliases",
]

WORKSPACE_VERSION = "0.1"

_HEADER = (
    "# flip workspace table — maintained by `flip ws`; hand edits are read but\n"
    "# comments are not preserved on rewrite.\n"
)


@dataclass
class Workspace:
    root: Path
    version: str = WORKSPACE_VERSION
    notebooks: dict[str, str] = field(default_factory=dict)  # handle -> rel posix path


def require_workspace_root(start: Path | None = None) -> Path:
    root = find_workspace_root(start)
    if root is None:
        raise SystemExit(
            "not inside a flip workspace (no .flip/workspace.toml found here or "
            "above); run `flip ws init` at the vault or repo root"
        )
    return root


def require_valid_handle(handle: str) -> str:
    if not HANDLE_RE.match(handle or ""):
        raise SystemExit(
            f"invalid handle {handle!r}: lowercase letters, digits, and hyphens, "
            "starting with a letter — e.g. recipes"
        )
    return handle


def load_workspace(ws_root: Path) -> Workspace:
    """Parse the workspace table. A broken file is a one-line SystemExit here;
    doctor catches that and reports it as bad-workspace-file instead."""
    path = ws_root / WORKSPACE_FILE
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise SystemExit(f"{path}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{path}: invalid TOML — {e}") from e
    meta = data.get("workspace")
    if not isinstance(meta, dict) or "version" not in meta:
        raise SystemExit(f"{path}: missing [workspace] version key")
    version = str(meta["version"])
    if version.split(".", 1)[0] != WORKSPACE_VERSION.split(".", 1)[0]:
        raise SystemExit(
            f"{path}: workspace version {version!r} is newer than this flip "
            f"understands ({WORKSPACE_VERSION}); upgrade flip"
        )
    notebooks: dict[str, str] = {}
    table = data.get("notebooks", {})
    if not isinstance(table, dict):
        raise SystemExit(f"{path}: [notebooks] must be a table of handle = \"path\"")
    for handle, rel in table.items():
        if not isinstance(rel, str):
            raise SystemExit(f"{path}: [notebooks] {handle} must be a string path")
        notebooks[str(handle)] = Path(rel).as_posix()
    return Workspace(root=ws_root, version=version, notebooks=notebooks)


def save_workspace(ws: Workspace) -> None:
    """Deterministic writer: fixed header, sorted handles, JSON-escaped paths
    (JSON string escaping is valid TOML basic-string escaping for all
    reachable inputs)."""
    path = ws.root / WORKSPACE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_HEADER, "\n[workspace]\n", f'version = "{ws.version}"\n', "\n[notebooks]\n"]
    for handle in sorted(ws.notebooks):
        require_valid_handle(handle)
        lines.append(f"{handle} = {json.dumps(ws.notebooks[handle])}\n")
    path.write_text("".join(lines), encoding="utf-8")


def default_handle(slug: str, taken: set[str]) -> str:
    """Derive a free handle from a manifest slug: narrow the charset to
    HANDLE_RE, then suffix -2, -3, … past collisions."""
    base = slug.replace(".", "-").replace("_", "-").strip("-") or "notebook"
    if not base[0].isalpha():
        base = "n" + base
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


# ---------------------------------------------------------------------------
# WP1 implements everything below; signatures are frozen by the foundation.
# ---------------------------------------------------------------------------


def discover_notebooks(ws_root: Path) -> list[Path]:
    """Find notebook roots under a workspace root: bounded walk that prunes
    registry.PRUNE_DIRS, dot-dirs, and export copies (registry.COPY_MARKERS);
    a matched notebook root is not descended into, beat roots are."""
    raise NotImplementedError("WP1")


def ws_init(ws_root: Path) -> Workspace:
    """Create the workspace table at ws_root: scan, propose handles (auto
    -2 suffix on slug collisions), write, and qualify aliases."""
    raise NotImplementedError("WP1")


def ws_add(ws_root: Path, nb_path: Path, handle: str | None = None) -> tuple[str, str]:
    """Bind one notebook. Returns (handle, relpath). Collision without an
    explicit handle is a SystemExit listing taken handles."""
    raise NotImplementedError("WP1")


def ws_rename(ws_root: Path, old: str, new: str) -> int:
    """Rebind a handle and rewrite qualified refs workspace-wide. Returns
    the number of files rewritten."""
    raise NotImplementedError("WP1")


def ws_rm(ws_root: Path, handle: str) -> None:
    """Unbind a handle and strip its qualified aliases. Never deletes files."""
    raise NotImplementedError("WP1")


def ws_rows(ws_root: Path) -> list[dict]:
    """Rows for `flip ws list`: handle, path, slug, uid, title, status
    ("ok" | "missing" | "not-a-notebook")."""
    raise NotImplementedError("WP1")


def ensure_qualified_aliases(
    nb_root: Path, handle: str | None, old_handle: str | None = None
) -> int:
    """Maintain id aliases on every entity page: bare id always present,
    `handle:id` when bound, `old_handle:id` removed. Foreign aliases and all
    other frontmatter preserved verbatim; pages rewritten only when the
    alias list actually changed. Returns pages changed."""
    raise NotImplementedError("WP1")


def _rewrite_qualified_refs(ws_root: Path, old: str, new: str) -> int:
    """Textual `old:ID` -> `new:ID` across workspace markdown (prose, wikilinks,
    labels, frontmatter), skipping sources/derived/renders/dot-dirs/export
    copies and fenced code blocks; notebook root index.md files are handled
    structurally to protect links.beat. Returns files changed."""
    raise NotImplementedError("WP1")
