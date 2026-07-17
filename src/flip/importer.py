"""`flip import` — bring a shared notebook into a workspace (SPEC §17-§18).

Sources: a notebook directory, an okf export, or a BagIt bag (payload =
data/). The copy lands under the workspace, gets bound to an importer-chosen
handle, and records provenance (`origin:`, and a `uid:` minted only when the
source predates uids). Entity ids are never rekeyed — identity lives in
metadata and the handle is the disambiguator, so citations inside the bundle
stay valid and round-trips are lossless.

`--update` is replace-if-uid-matches: same lineage refreshes in place
(keeping local `.flip/` reservations); anything else refuses. Three-way merge
of diverged copies is out of scope for 0.9.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import registry, workspace
from .doctor import run_doctor
from .manifest import load_manifest, save_manifest
from .okf import STATE_FILE
from .util import is_notebook_root, new_uid, today

__all__ = ["import_bundle", "update_bundle"]

# Local-only directory names: never copied out of a source bundle, and never
# deleted from the bound copy on --update. `.flip/` holds the id reservation
# file (ids are never reused — SPEC §9 — so reservations must survive a
# refresh); the rest is tooling state the import never created and does not
# own.
_LOCAL_DIRS = {".flip", ".obsidian", ".git"}


def import_bundle(
    ws_root: Path,
    src: Path,
    handle: str | None = None,
    into: Path | None = None,
) -> dict:
    """Copy a bundle into the workspace and bind it. Returns a summary dict
    (slug, handle, path, uid, doctor finding counts) for the CLI."""
    ws_root = Path(ws_root).resolve()
    src = Path(src).resolve()
    _kind, payload = _classify_src(src)
    slug = load_manifest(payload).slug
    ws = workspace.load_workspace(ws_root)
    if handle is None:
        handle = workspace.default_handle(slug, set())
    else:
        workspace.require_valid_handle(handle)
    if handle in ws.notebooks:
        raise SystemExit(workspace._handle_taken(handle, set(ws.notebooks)))
    dest = Path(into).resolve() if into is not None else ws_root / handle
    try:
        rel = dest.relative_to(ws_root).as_posix()
    except ValueError:
        raise SystemExit(
            f"{dest} is outside the workspace root {ws_root}; imports land "
            "beneath the workspace so their handle can resolve"
        ) from None
    if dest.exists():
        raise SystemExit(f"{dest} already exists; pick a fresh --into or remove it first")
    for ancestor in dest.parents:
        if ancestor == ws_root:
            break
        if is_notebook_root(ancestor):
            raise SystemExit(
                f"{dest} is inside the notebook at {ancestor}; a notebook never "
                "nests inside another — pick an --into directly under the workspace"
            )

    _copy_payload(payload, dest)
    m = load_manifest(dest)
    if not m.uid:
        m.uid = new_uid()  # the source predates uids; mint the lineage id here
    m.origin = f"{src} (imported {today()})"
    save_manifest(dest, m)

    ws.notebooks[handle] = rel
    workspace.save_workspace(ws)
    workspace.ensure_qualified_aliases(dest, handle)
    return _summary(dest, m.slug, handle, rel, m.uid)


def update_bundle(ws_root: Path, handle: str, src: Path) -> dict:
    """Refresh an imported bundle from a newer copy of the same lineage
    (uids must match). Returns a summary dict for the CLI."""
    ws_root = Path(ws_root).resolve()
    src = Path(src).resolve()
    ws = workspace.load_workspace(ws_root)
    rel = workspace._require_bound(ws, handle)
    dest = ws_root / rel
    if not is_notebook_root(dest):
        raise SystemExit(
            f"{dest} (bound as '{handle}') is not a flip notebook on disk; fix the "
            "binding with `flip ws rm` / `flip ws add` before --update"
        )
    _kind, payload = _classify_src(src)
    # Refuse before anything is deleted: the refresh wipes dest and then
    # copies the payload in, so src and dest must be disjoint trees — a src
    # that IS the bound copy (or lives inside it, or contains it) would be
    # destroyed by its own wipe. A plausible arg mixup, not a real refresh.
    dest_res, src_res = dest.resolve(), src.resolve()
    if dest_res == src_res or dest_res.is_relative_to(src_res) or src_res.is_relative_to(dest_res):
        raise SystemExit(
            f"--update source {src} overlaps the bound copy at {dest}; --update "
            "replaces the bound copy from a separate directory — nothing was changed"
        )
    local_uid = load_manifest(dest).uid
    src_uid = load_manifest(payload).uid
    if local_uid and src_uid and local_uid == src_uid:
        uid = local_uid
    elif not local_uid and not src_uid:
        uid = new_uid()  # both copies predate uids; mint the shared lineage id locally
    else:
        raise SystemExit(
            f"uid mismatch: '{handle}' has uid {local_uid or '(none)'} but {src} has "
            f"{src_uid or '(none)'} — not the same notebook lineage; import it under "
            "its own handle with `flip import` instead"
        )

    for entry in sorted(dest.iterdir()):
        if entry.name in _LOCAL_DIRS:
            continue  # local reservations (and local tooling state) survive
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    _copy_payload(payload, dest)
    m = load_manifest(dest)
    m.uid = uid
    m.origin = f"{src} (imported {today()})"
    save_manifest(dest, m)
    workspace.ensure_qualified_aliases(dest, handle)
    return _summary(dest, m.slug, handle, rel, uid)


def _classify_src(src: Path) -> tuple[str, Path]:
    """("bag" | "okf-export" | "notebook", payload_root) — SystemExit when
    src is none of them. Bag fixity is not re-verified here (out of scope;
    `bagit.py --validate` or similar does that before import)."""
    src = Path(src)
    if (src / "bagit.txt").is_file():
        payload = src / "data"
        if not is_notebook_root(payload):
            raise SystemExit(
                f"{src} is a BagIt bag but data/ is not a flip notebook (no index.md "
                "with flip manifest frontmatter); only flip bags import"
            )
        return "bag", payload
    if not is_notebook_root(src):
        raise SystemExit(
            f"{src} is not an importable bundle: expected a flip notebook directory, "
            "an OKF export, or a BagIt bag (bagit.txt + data/)"
        )
    if (src / STATE_FILE).is_file():
        return "okf-export", src
    return "notebook", src


def _copy_payload(payload: Path, dest: Path) -> None:
    """Copy the bundle tree, skipping local-only dirs (_LOCAL_DIRS), the okf
    export marker, and any nested export copy (a bag or OKF bundle riding
    inside the source is a copy of custody bytes, never notebook payload —
    same rule as registry/export)."""
    for dirpath, dirnames, filenames in os.walk(payload):
        directory = Path(dirpath)
        if directory != payload and any(
            marker in filenames for marker in registry.COPY_MARKERS
        ):
            dirnames[:] = []  # a nested export copy — never payload
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in _LOCAL_DIRS)
        for name in sorted(filenames):
            if name == STATE_FILE:
                continue  # labels the source as an okf export; not content
            target = dest / (directory / name).relative_to(payload)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(directory / name, target)


def _summary(dest: Path, slug: str, handle: str, rel: str, uid: str) -> dict:
    """Post-copy doctor pass folded into the CLI summary. Findings never fail
    the import — the copy is already bound; doctor says what to clean up."""
    findings = run_doctor(dest)
    return {
        "slug": slug,
        "handle": handle,
        "path": rel,
        "uid": uid,
        "doctor_errors": sum(1 for f in findings if f.level == "ERROR"),
        "doctor_warns": sum(1 for f in findings if f.level == "WARN"),
    }
