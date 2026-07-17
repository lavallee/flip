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
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import pages, registry
from .manifest import load_manifest, save_manifest
from .util import (
    HANDLE_RE,
    ROOT_FILE,
    WORKSPACE_FILE,
    find_workspace_root,
    is_notebook_root,
    is_workspace_root,
)

__all__ = [
    "WORKSPACE_FILE", "WORKSPACE_VERSION", "Workspace",
    "is_workspace_root", "find_workspace_root", "require_workspace_root",
    "require_valid_handle", "load_workspace", "save_workspace",
    "discover_notebooks", "default_handle", "ws_init", "ws_add",
    "ws_rename", "ws_rm", "ws_rows", "ensure_qualified_aliases",
    "other_workspace_handles",
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


def discover_notebooks(ws_root: Path) -> list[Path]:
    """Find notebook roots under a workspace root: bounded walk that prunes
    registry.PRUNE_DIRS, dot-dirs, and export copies (registry.COPY_MARKERS);
    a matched notebook root is not descended into, beat roots are.

    Beat roots descend for free: their index.md declares `flip_beat:`, which
    never matches the `flip:` sniff (beat.is_beat_root is deliberately
    disjoint from util.is_notebook_root), so the walk keeps going down to the
    real notebooks under notebooks/. Sorted dirnames make the result order
    deterministic (top-down, lexicographic).
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ws_root):
        if any(marker in filenames for marker in registry.COPY_MARKERS):
            dirnames[:] = []  # an export copy of a notebook, never a second one
            continue
        dirnames[:] = sorted(
            d for d in dirnames if d not in registry.PRUNE_DIRS and not d.startswith(".")
        )
        directory = Path(dirpath)
        if ROOT_FILE in filenames and is_notebook_root(directory):
            found.append(directory)
            dirnames[:] = []  # a notebook inside a notebook never double-counts
    return found


def ws_init(ws_root: Path) -> Workspace:
    """Create the workspace table at ws_root: scan, propose handles (auto
    -2 suffix on slug collisions, noted loudly on stderr), write, and
    qualify aliases."""
    if (ws_root / WORKSPACE_FILE).exists():
        raise SystemExit(
            f"{ws_root / WORKSPACE_FILE} already exists; `flip ws add <path>` binds "
            "more notebooks, `flip ws list` shows what's bound"
        )
    if is_notebook_root(ws_root):
        raise SystemExit(
            f"{ws_root} is a notebook root; a workspace wraps notebooks — run "
            "`flip ws init` one level up, at the vault or repo root"
        )
    ws = Workspace(root=ws_root)
    bindings: list[tuple[str, Path]] = []
    for nb_root in discover_notebooks(ws_root):
        slug = load_manifest(nb_root).slug
        handle = default_handle(slug, set(ws.notebooks))
        rel = nb_root.relative_to(ws_root).as_posix()
        if handle != slug:
            print(
                f"note: bound {rel} as '{handle}' — slug '{slug}' was taken or is "
                "not a valid handle; rename with `flip ws rename`",
                file=sys.stderr,
            )
        ws.notebooks[handle] = rel
        bindings.append((handle, nb_root))
    save_workspace(ws)
    for handle, nb_root in bindings:
        ensure_qualified_aliases(nb_root, handle)
    return ws


def _handle_taken(handle: str, taken: set[str]) -> str:
    suggestion = default_handle(handle, taken)
    return (
        f"handle '{handle}' is taken (taken: {', '.join(sorted(taken))}); "
        f"re-run with --as, e.g. --as {suggestion}"
    )


def _require_bound(ws: Workspace, handle: str) -> str:
    """The relpath bound to `handle`, or a SystemExit listing what is bound."""
    if handle not in ws.notebooks:
        known = ", ".join(sorted(ws.notebooks)) or "none bound"
        raise SystemExit(
            f"unknown handle '{handle}' (known handles: {known}) — see `flip ws list`"
        )
    return ws.notebooks[handle]


def ws_add(ws_root: Path, nb_path: Path, handle: str | None = None) -> tuple[str, str]:
    """Bind one notebook. Returns (handle, relpath). Collision without an
    explicit handle is a SystemExit listing taken handles."""
    nb_path = nb_path.resolve()
    try:
        rel = nb_path.relative_to(ws_root.resolve()).as_posix()
    except ValueError:
        raise SystemExit(
            f"{nb_path} is outside the workspace root {ws_root}; a workspace "
            "binds only notebooks beneath it"
        ) from None
    if rel == ".":
        raise SystemExit("the workspace root itself can't be bound as a notebook")
    if not is_notebook_root(nb_path):
        raise SystemExit(
            f"{nb_path} is not a flip notebook root (no index.md with flip "
            "manifest frontmatter); `flip new <slug>` creates one"
        )
    ws = load_workspace(ws_root)
    for bound, existing in ws.notebooks.items():
        if existing == rel:
            raise SystemExit(f"{rel} is already bound as '{bound}' (rename with `flip ws rename`)")
    taken = set(ws.notebooks)
    if handle is None:
        handle = default_handle(load_manifest(nb_path).slug, set())
    else:
        require_valid_handle(handle)
    if handle in taken:
        raise SystemExit(_handle_taken(handle, taken))
    ws.notebooks[handle] = rel
    save_workspace(ws)
    ensure_qualified_aliases(nb_path, handle)
    return handle, rel


def ws_rename(ws_root: Path, old: str, new: str) -> tuple[int, int]:
    """Rebind a handle and rewrite qualified refs workspace-wide. Returns
    (files with refs rewritten, pages whose aliases were regenerated)."""
    require_valid_handle(new)
    ws = load_workspace(ws_root)
    rel = _require_bound(ws, old)
    if new == old:
        raise SystemExit(f"'{old}' is already the handle; nothing to do")
    if new in ws.notebooks:
        raise SystemExit(
            f"handle '{new}' is already bound to {ws.notebooks[new]}; pick "
            f"another, or `flip ws rm {new}` first"
        )
    del ws.notebooks[old]
    ws.notebooks[new] = rel
    save_workspace(ws)
    nb_root = ws_root / rel
    alias_pages = 0
    if is_notebook_root(nb_root):
        alias_pages = ensure_qualified_aliases(nb_root, new, old_handle=old)
    return _rewrite_qualified_refs(ws_root, old, new), alias_pages


def ws_rm(ws_root: Path, handle: str) -> None:
    """Unbind a handle and strip its qualified aliases. Never deletes files."""
    ws = load_workspace(ws_root)
    rel = _require_bound(ws, handle)
    del ws.notebooks[handle]
    save_workspace(ws)
    nb_root = ws_root / rel
    if is_notebook_root(nb_root):  # a missing dir has no aliases to strip
        ensure_qualified_aliases(nb_root, None, old_handle=handle)


def ws_rows(ws_root: Path) -> list[dict]:
    """Rows for `flip ws list`: handle, path, slug, uid, title, status
    ("ok" | "missing" | "not-a-notebook")."""
    ws = load_workspace(ws_root)
    rows: list[dict] = []
    for handle in sorted(ws.notebooks):
        rel = ws.notebooks[handle]
        row = {"handle": handle, "path": rel, "slug": "", "uid": "", "title": "",
               "status": "ok"}
        nb_root = ws_root / rel
        if not nb_root.is_dir():
            row["status"] = "missing"
        elif not is_notebook_root(nb_root):
            row["status"] = "not-a-notebook"
        else:
            try:
                m = load_manifest(nb_root)
            except SystemExit:  # flip frontmatter present but manifest broken
                row["status"] = "not-a-notebook"
            else:
                row.update(slug=m.slug, uid=m.uid, title=m.title)
        rows.append(row)
    return rows


def other_workspace_handles(ws_root: Path, nb_root: Path) -> set[str]:
    """Handles binding nb_root in *other* workspace tables that enclose it —
    every workspace root among nb_root's ancestors except ws_root itself
    (an enclosing vault above, or a nested workspace between ws_root and the
    notebook). Nested workspaces are supported (resolution is nearest-wins),
    and each table maintains its own qualified aliases on the same pages —
    so those handles are legitimate, not stale."""
    ws_root = ws_root.resolve()
    nb_resolved = nb_root.resolve()
    handles: set[str] = set()
    for ancestor in nb_resolved.parents:
        if ancestor == ws_root or not is_workspace_root(ancestor):
            continue
        try:
            other = load_workspace(ancestor)
        except SystemExit:
            continue  # a broken table is that workspace's own doctor finding
        for handle, rel in other.notebooks.items():
            if (ancestor / rel).resolve() == nb_resolved:
                handles.add(handle)
    return handles


def ensure_qualified_aliases(
    nb_root: Path, handle: str | None, old_handle: str | None = None
) -> int:
    """Maintain id aliases on every entity page: bare id always present,
    `handle:id` when bound (inserted right after the bare id), `old_handle:id`
    removed. Foreign aliases and all other frontmatter preserved verbatim;
    pages rewritten only when the alias list actually changed. Returns pages
    changed. Unparseable pages are skipped — doctor reports those."""
    changed = 0
    for dirname in pages.SCAN_DIRS:
        found, _errors = pages.iter_pages_tolerant(nb_root, dirname)
        for page in found:
            entity_id = page.id
            if not entity_id:
                continue
            aliases = pages.as_list(page.fm.get("aliases"))
            wanted = list(aliases)
            if old_handle:
                wanted = [a for a in wanted if a != f"{old_handle}:{entity_id}"]
            if entity_id not in wanted:
                wanted.append(entity_id)
            if handle:
                qualified = f"{handle}:{entity_id}"
                if qualified not in wanted:
                    wanted.insert(wanted.index(entity_id) + 1, qualified)
            if wanted != aliases:
                fm = dict(page.fm)  # key order preserved; aliases keeps its slot
                fm["aliases"] = wanted
                pages.write_page(page.path, fm, page.body)
                changed += 1
    return changed


# Directory components the ref rewrite never edits: custody bytes and
# derivations are verbatim (SPEC §5.1), renders are disposable, the rest is
# tooling noise. Mirrors rename._PRUNE.
_REWRITE_PRUNE = {"sources", "derived", "renders", "node_modules", "__pycache__"}


def _workspace_md_files(ws_root: Path) -> list[Path]:
    """Every markdown file the rename rewrite may touch: pruned like
    rename._md_files, plus export-copy dirs (registry.COPY_MARKERS) skipped."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ws_root):
        if any(marker in filenames for marker in registry.COPY_MARKERS):
            dirnames[:] = []  # export copies are never edited
            continue
        dirnames[:] = sorted(
            d for d in dirnames if d not in _REWRITE_PRUNE and not d.startswith(".")
        )
        out.extend(Path(dirpath) / name for name in sorted(filenames) if name.endswith(".md"))
    return out


def _sub_outside_fences(token: re.Pattern, replacement: str, text: str) -> str:
    """Apply a substitution line-by-line, skipping ``` fenced blocks. Inline
    code spans are an accepted limitation (documented in the CHANGELOG)."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append(line if in_fence else token.sub(replacement, line))
    return "".join(out)


def _split_frontmatter_block(text: str) -> tuple[str, str]:
    """(frontmatter block, body) split byte-preservingly: the block includes
    both delimiter lines; a file with no leading block is ("", text). Mirrors
    pages.parse's delimiter handling without touching the YAML."""
    if not text.startswith(pages.FM_DELIM + "\n"):
        return "", text
    end = text.find("\n" + pages.FM_DELIM, len(pages.FM_DELIM))
    if end == -1:
        return "", text  # unterminated block: pages.parse treats it all as body
    close = end + 1 + len(pages.FM_DELIM)
    if text[close : close + 1] == "\n":
        close += 1
    return text[:close], text[close:]


def _rewrite_qualified_refs(ws_root: Path, old: str, new: str) -> int:
    """Textual `old:ID` -> `new:ID` across workspace markdown (prose, wikilinks,
    labels, frontmatter), skipping sources/derived/renders/dot-dirs/export
    copies and fenced code blocks; notebook root index.md frontmatter is
    handled structurally to protect links.beat (their prose bodies are
    rewritten like any other page). Every notebook root under the workspace is
    protected this way, bound or not — an unregistered notebook's beat lineage
    must survive a rename too. Returns files changed.

    The token regex is anchored both ways: the lookbehind keeps
    `other-old:A3` from matching as a substring, the lookahead demands a
    compact id right after the colon so `old:notafile.md` stays untouched.
    """
    token = re.compile(
        r"(?<![A-Za-z0-9_-])" + re.escape(old) + r":(?=[A-Z]+\d+(?![A-Za-z0-9]))"
    )
    replacement = f"{new}:"
    ws = load_workspace(ws_root)
    nb_roots = {
        (ws_root / rel).resolve()
        for rel in ws.notebooks.values()
        if is_notebook_root(ws_root / rel)
    }
    nb_roots.update(r.resolve() for r in discover_notebooks(ws_root))
    root_indexes = {nb_root / ROOT_FILE for nb_root in nb_roots}
    changed_files: set[Path] = set()
    for md_file in _workspace_md_files(ws_root):
        resolved = md_file.resolve()
        text = md_file.read_text(encoding="utf-8")
        if resolved in root_indexes:
            # frontmatter handled structurally below — links.beat must survive
            fm_block, body = _split_frontmatter_block(text)
            new_text = fm_block + _sub_outside_fences(token, replacement, body)
        else:
            new_text = _sub_outside_fences(token, replacement, text)
        if new_text != text:
            md_file.write_text(new_text, encoding="utf-8")
            changed_files.add(resolved)
    for nb_root in sorted(nb_roots):
        try:
            m = load_manifest(nb_root)
        except SystemExit:
            continue  # unreadable manifest: doctor's finding, not rename's crash
        dirty = False
        for key, value in m.links.items():
            if key == "beat":
                continue  # a beat slug is not a workspace handle (SPEC §14)
            if isinstance(value, str):
                rewritten = token.sub(replacement, value)
            elif isinstance(value, list):
                rewritten = [token.sub(replacement, v) if isinstance(v, str) else v
                             for v in value]
            else:
                continue
            if rewritten != value:
                m.links[key] = rewritten
                dirty = True
        if dirty:
            save_manifest(nb_root, m)
            changed_files.add(nb_root / ROOT_FILE)
    return len(changed_files)
