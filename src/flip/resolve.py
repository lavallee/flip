"""Reference resolution — the one primitive behind `flip resolve`/`flip open`.

Normative semantics (SPEC §9): a bare id resolves within the containing
notebook; `handle:id` resolves through the nearest workspace table; unknown
handles and ids are loud diagnostics, never guesses. The single sanctioned
extension: a bare id used under a workspace root (outside any notebook)
resolves iff exactly one bound notebook carries it — ambiguity lists the
qualified forms to use instead. The pre-0.5 '#' separator no longer reads
(removed in flip 0.10).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import pages
from .manifest import load_manifest
from .util import (
    find_notebook_root,
    find_notebook_root_pinned,
    find_workspace_root,
    format_ref,
    parse_ref,
    require_notebook_root,
)
from .workspace import load_workspace, require_workspace_root

__all__ = ["Resolved", "resolve_ref", "known_ids_hint"]


@dataclass
class Resolved:
    ref: str
    entity_id: str
    handle: str | None
    path: Path
    notebook_root: Path
    notebook_slug: str
    uid: str
    title: str


def known_ids_hint(root: Path) -> str:
    """"known ids: A1, C2, …" for unknown-id diagnostics (shared with the CLI)."""
    known = sorted(
        {p.id for d in pages.SCAN_DIRS for p in pages.iter_pages(root, d) if p.id},
        key=lambda s: (s.rstrip("0123456789"), len(s), s),
    )
    return f"known ids: {', '.join(known)}" if known else "no entity pages yet"


def _resolved(ref: str, entity_id: str, handle: str | None,
              page: pages.Page, nb_root: Path) -> Resolved:
    m = load_manifest(nb_root)
    title = str(page.fm.get("title") or page.fm.get("description") or "")
    return Resolved(ref=ref, entity_id=entity_id, handle=handle, path=page.path,
                    notebook_root=nb_root, notebook_slug=m.slug, uid=m.uid, title=title)


def _find_in_notebook(ref: str, entity_id: str, handle: str | None, nb_root: Path) -> Resolved:
    page = pages.find_by_id(nb_root, entity_id)
    if page is None:
        where = f" in notebook '{handle}'" if handle else ""
        raise SystemExit(f"no page with id '{entity_id}'{where} ({known_ids_hint(nb_root)})")
    return _resolved(ref, entity_id, handle, page, nb_root)


def resolve_ref(ref: str, start: Path | None = None) -> Resolved:
    """Resolve "A3" / "recipes:A3" from `start` (default cwd) to the entity
    page. The pre-0.5 "recipes#A3" form no longer reads (removed in flip
    0.10) — parse_ref rejects it with the current grammar."""
    handle, entity_id = parse_ref(ref)

    # A CLI entry point (start is None) honors the --notebook/FLIP_NOTEBOOK
    # pin: resolution anchors on the pinned root, not the CWD, so `flip
    # --notebook <path> resolve A3` works from anywhere (SPEC §15).
    if start is None:
        start = find_notebook_root_pinned()

    if handle is not None:
        ws_root = require_workspace_root(start)
        ws = load_workspace(ws_root)
        if handle not in ws.notebooks:
            known = ", ".join(sorted(ws.notebooks)) or "none bound"
            raise SystemExit(
                f"unknown handle '{handle}' in workspace {ws_root} "
                f"(known handles: {known}) — see `flip ws list`"
            )
        return _find_in_notebook(ref, entity_id, handle, ws_root / ws.notebooks[handle])

    nb_root = find_notebook_root(start)
    if nb_root is not None:
        return _find_in_notebook(ref, entity_id, None, nb_root)

    ws_root = find_workspace_root(start)
    if ws_root is None:
        require_notebook_root(start)  # raises the canonical "not inside…" message
    ws = load_workspace(ws_root)
    matches: list[tuple[str, Resolved]] = []
    for h in sorted(ws.notebooks):
        page = pages.find_by_id(ws_root / ws.notebooks[h], entity_id)
        if page is not None:
            matches.append((h, _resolved(ref, entity_id, None, page, ws_root / ws.notebooks[h])))
    if len(matches) == 1:
        return matches[0][1]
    if matches:
        forms = " or ".join(format_ref(h, entity_id) for h, _ in matches)
        raise SystemExit(
            f"'{entity_id}' is ambiguous in this workspace — qualify it: {forms}"
        )
    raise SystemExit(f"no page with id '{entity_id}' in any notebook bound in {ws_root}")
