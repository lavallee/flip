"""The per-user registry (SPEC §15): scan roots for notebooks, rebuild index.jsonl.

`flip index` walks configured roots looking for flip notebook roots — an
index.md whose frontmatter declares a `flip:` profile version (util.
is_notebook_root; plain OKF bundles without the flip key don't count) — and
rewrites `<flip_home>/index.jsonl` in full, one line per notebook plus one
per workspace root (.flip/workspace.toml, SPEC §18). A plain file, built by
scanning, no service: anything richer (dashboards, concept registries)
consumes this file; flip has no reverse dependency on them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .manifest import load_manifest
from .util import ROOT_FILE, is_notebook_root, is_workspace_root, read_jsonl, write_jsonl

INDEX = "index.jsonl"

# Directory names never descended into while scanning.
PRUNE_DIRS = {".git", ".venv", "node_modules", "__pycache__", "renders"}

# Marker files whose directory holds a COPY of a notebook, not a second
# notebook: BagIt bags (`flip export bag`) and OKF exports (`flip export okf`,
# which since v0.4 copies the bundle wholesale, flip frontmatter included).
COPY_MARKERS = ("bagit.txt", ".last-export.json")


def flip_home() -> Path:
    """Per-user flip home: $FLIP_HOME when set, else ~/.flip."""
    override = os.environ.get("FLIP_HOME")
    return Path(override) if override else Path.home() / ".flip"


def _index_row(nb_dir: Path) -> dict:
    m = load_manifest(nb_dir)
    return {
        "path": str(nb_dir),
        "slug": m.slug,
        "uid": m.uid,  # "" for pre-0.5 notebooks that haven't run `flip migrate`
        "kind": m.kind,
        "status": m.status,
        # tolerate foreign-authored non-string values (YAML dates arrive as
        # ISO strings via pages, but belt-and-suspenders for hand edits)
        "updated": m.updated if isinstance(m.updated, str) else str(m.updated),
        "title": m.title if isinstance(m.title, str) else str(m.title),
    }


def _workspace_row(ws_dir: Path) -> dict:
    # Lazy import: workspace.py imports registry (PRUNE_DIRS/COPY_MARKERS),
    # so a module-level import here would be circular.
    from .workspace import load_workspace

    ws = load_workspace(ws_dir)
    return {"path": str(ws_dir), "workspace": True, "notebooks": dict(ws.notebooks)}


def build_index(roots: list[Path]) -> list[dict]:
    """Scan `roots` for notebooks and workspaces, rewrite <flip_home>/index.jsonl.

    One row per notebook: path (absolute str), slug, uid, kind, status,
    updated, title. A directory carrying .flip/workspace.toml adds one
    workspace row — {"path", "workspace": true, "notebooks": {handle: rel}} —
    and is still descended into, so its bound notebooks index as themselves.
    Unparseable manifests (or workspace tables) are skipped with a WARN row of
    shape {"path": ..., "error": ...} so the scan never dies on one bad entry.
    Returns the rows written.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    seen_ws: set[str] = set()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            if any(marker in filenames for marker in COPY_MARKERS):
                # An export (bag or OKF bundle): it holds a COPY of a
                # notebook, not a second notebook — never descend or index.
                dirnames[:] = []
                continue
            dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_DIRS)
            directory = Path(dirpath)
            if is_workspace_root(directory):
                ws_dir = directory.resolve()
                if str(ws_dir) not in seen_ws:
                    seen_ws.add(str(ws_dir))
                    try:
                        rows.append(_workspace_row(ws_dir))
                    except (SystemExit, Exception) as e:  # tolerate one broken table
                        err = str(e)
                        print(f"WARN: skipped {ws_dir}: {err}", file=sys.stderr)
                        rows.append({"path": str(ws_dir), "error": err})
                # no continue: the walk descends so bound notebooks get rows too
            if ROOT_FILE not in filenames or not is_notebook_root(directory):
                continue  # no index.md, or an OKF/plain index without flip frontmatter
            nb_dir = directory.resolve()
            if str(nb_dir) in seen:
                continue
            seen.add(str(nb_dir))
            try:
                rows.append(_index_row(nb_dir))
            except (SystemExit, Exception) as e:  # tolerate one broken manifest
                err = str(e)
                print(f"WARN: skipped {nb_dir}: {err}", file=sys.stderr)
                rows.append({"path": str(nb_dir), "error": err})
    write_jsonl(flip_home() / INDEX, rows)
    return rows


def read_index() -> list[dict]:
    """Read the registry; empty list when no index has been built yet."""
    return read_jsonl(flip_home() / INDEX)
