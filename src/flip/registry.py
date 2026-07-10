"""The per-user registry (SPEC §14): scan roots for notebooks, rebuild index.jsonl.

`flip index` walks configured roots looking for directories that hold
notebook.toml and rewrites `<flip_home>/index.jsonl` in full — one line per
notebook. A plain file, built by scanning, no service: anything richer
(dashboards, concept registries) consumes this file; flip has no reverse
dependency on them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .manifest import load_manifest
from .util import MANIFEST, read_jsonl, write_jsonl

INDEX = "index.jsonl"

# Directory names never descended into while scanning.
PRUNE_DIRS = {".git", ".venv", "node_modules", "__pycache__", "renders"}


def flip_home() -> Path:
    """Per-user flip home: $FLIP_HOME when set, else ~/.flip."""
    override = os.environ.get("FLIP_HOME")
    return Path(override) if override else Path.home() / ".flip"


def _index_row(nb_dir: Path) -> dict:
    m = load_manifest(nb_dir)
    return {
        "path": str(nb_dir),
        "slug": m.slug,
        "kind": m.kind,
        "status": m.status,
        # tolerate hand-written unquoted TOML dates (tomllib yields date objects)
        "updated": m.updated if isinstance(m.updated, str) else str(m.updated),
        "title": m.title if isinstance(m.title, str) else str(m.title),
    }


def build_index(roots: list[Path]) -> list[dict]:
    """Scan `roots` for notebooks and rewrite <flip_home>/index.jsonl.

    One row per notebook: path (absolute str), slug, kind, status, updated,
    title. Unparseable manifests are skipped with a WARN row of shape
    {"path": ..., "error": ...} so the scan never dies on one bad notebook.
    Returns the rows written.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            if "bagit.txt" in filenames:
                # An export bag (`flip export bag`): its data/ holds a COPY of
                # a notebook, not a second notebook — never descend or index.
                dirnames[:] = []
                continue
            dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_DIRS)
            if MANIFEST not in filenames:
                continue
            nb_dir = Path(dirpath).resolve()
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
