"""Interop exports (SPEC §17): BagIt bags and CSL JSON.

Exports are projections — the canonical artifact stays the plain-file
notebook, and exporters never mutate it. `export_bag` writes a BagIt 1.0 bag
for cold archival; `export_csl` maps the source ledger to CSL-JSON items for
citation managers.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .util import MANIFEST, read_jsonl, sha256_file, today

# Directory names excluded from bag payloads: repo/tooling internals and
# derived renders are not evidentiary content (SPEC §11, §16).
EXCLUDE_DIRS = {".git", ".venv", ".flip", "renders", "__pycache__"}

_CSL_TYPES = {
    "paper": "article-journal",
    "web": "webpage",
    "article": "webpage",  # ledger "article" rows are captured web articles
    "dataset": "dataset",
    "file": "dataset",
    "talk": "speech",
}


def _require_notebook(root: Path) -> Path:
    root = Path(root)
    if not (root / MANIFEST).is_file():
        raise SystemExit(
            f"{root} is not a flip notebook (no {MANIFEST}); "
            "pass a notebook root or run `flip new <slug>` first"
        )
    return root


def _payload_files(root: Path) -> list[Path]:
    """Notebook files relative to root, excluded dirs pruned, sorted.

    Symlinks are followed: a valid link — file or directory — contributes its
    resolved CONTENT under the link's own name (so `drafts/current -> v1`
    yields `drafts/current/...` paths whose bytes duplicate `drafts/v1/...`).
    A dangling link is skipped with a warning on stderr. Self-referential
    directory loops are cut by tracking each branch's resolved ancestors.
    """
    out: list[Path] = []

    def walk(dir_path: Path, seen_reals: frozenset[Path]) -> None:
        real = dir_path.resolve()
        if real in seen_reals:  # symlink loop back into an ancestor
            return
        seen_reals = seen_reals | {real}
        for entry in sorted(dir_path.iterdir()):
            if entry.is_symlink() and not entry.exists():
                rel = entry.relative_to(root).as_posix()
                print(
                    f"warning: skipping dangling symlink {rel} -> {entry.readlink()}",
                    file=sys.stderr,
                )
                continue
            if entry.is_dir():
                if entry.name not in EXCLUDE_DIRS:
                    walk(entry, seen_reals)
            elif entry.is_file():
                out.append(entry.relative_to(root))

    walk(root, frozenset())
    return sorted(out)


def export_bag(root: Path, dest: Path) -> Path:
    """Write a BagIt 1.0 bag of the notebook at `dest` for cold archival.

    Payload (`data/`) is the full notebook tree minus EXCLUDE_DIRS;
    `manifest-sha256.txt` carries per-file fixity; `bag-info.txt` carries
    Bagging-Date and Payload-Oxum (<octets>.<files>).

    Symlinks are materialized: a valid link's content is copied under the
    link's name, so `drafts/current/` appears in the bag as a full copy of
    the current draft (deliberate duplication — a bag is for cold storage,
    where the pointer matters more than the bytes saved). Dangling links are
    skipped with a warning. If anything fails mid-export, the partial bag at
    `dest` is removed before exiting, so a retry starts clean.
    """
    root = _require_notebook(root)
    dest = Path(dest)
    if dest.exists():
        raise SystemExit(f"{dest} already exists; export to a fresh path or remove it first")
    data = dest / "data"
    total_bytes = 0
    manifest_lines: list[str] = []
    try:
        for rel in _payload_files(root):
            target = data / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, target)
            total_bytes += target.stat().st_size
            manifest_lines.append(f"{sha256_file(target)}  data/{rel.as_posix()}")
        (dest / "bagit.txt").write_text(
            "BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n", encoding="utf-8"
        )
        (dest / "manifest-sha256.txt").write_text(
            "\n".join(manifest_lines) + "\n", encoding="utf-8"
        )
        (dest / "bag-info.txt").write_text(
            f"Bagging-Date: {today()}\nPayload-Oxum: {total_bytes}.{len(manifest_lines)}\n",
            encoding="utf-8",
        )
    except SystemExit:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise SystemExit(
            f"export bag failed ({e}); removed the partial bag at {dest} — "
            "fix the cause and re-run"
        ) from None
    return dest


def _issued(date: object) -> dict | None:
    """Parse a ledger date ("2025-11-23", "2025-11", "2025") to CSL issued."""
    parts: list[int] = []
    for piece in str(date).split("T")[0].split("-")[:3]:
        if not piece.isdigit():
            break
        parts.append(int(piece))
    if not parts:
        return None
    return {"date-parts": [parts]}


def _note(row: dict) -> str:
    bits = [f"{key}: {row[key]}" for key in ("grade", "independence", "freshness") if row.get(key)]
    return "; ".join(bits)


def export_csl(root: Path) -> list[dict]:
    """Map sources/ledger.jsonl rows to CSL-JSON items (one per source)."""
    root = _require_notebook(root)
    ledger = root / "sources" / "ledger.jsonl"
    try:
        rows = read_jsonl(ledger)
    except ValueError as e:
        raise SystemExit(f"{e}; fix that line in the source ledger, then re-export") from None
    items: list[dict] = []
    for row in rows:
        item: dict = {
            "id": row.get("id"),
            "type": _CSL_TYPES.get(row.get("kind", ""), "document"),
        }
        if row.get("title"):
            item["title"] = row["title"]
        if row.get("authors"):
            item["author"] = [{"literal": a} for a in row["authors"]]
        issued = _issued(row["date"]) if row.get("date") else None
        if issued:
            item["issued"] = issued
        if row.get("url"):
            item["URL"] = row["url"]
        if row.get("publisher"):
            item["publisher"] = row["publisher"]
        note = _note(row)
        if note:
            item["note"] = note
        items.append(item)
    return items


def export_okf(
    root: Path, dest: Path, include_private: bool = False, announce: Path | None = None
) -> Path:
    """OKF v0.1 knowledge-bundle export; see okf.py and docs/wiki-alignment.md."""
    from .okf import export_okf as _export_okf

    return _export_okf(root, dest, include_private=include_private, announce=announce)
