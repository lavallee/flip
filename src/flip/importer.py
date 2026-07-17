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

from pathlib import Path

__all__ = ["import_bundle", "update_bundle"]


def import_bundle(
    ws_root: Path,
    src: Path,
    handle: str | None = None,
    into: Path | None = None,
) -> dict:
    """Copy a bundle into the workspace and bind it. Returns a summary dict
    (slug, handle, path, uid, doctor finding counts) for the CLI."""
    raise NotImplementedError("WP2")


def update_bundle(ws_root: Path, handle: str, src: Path) -> dict:
    """Refresh an imported bundle from a newer copy of the same lineage
    (uids must match). Returns a summary dict for the CLI."""
    raise NotImplementedError("WP2")


def _classify_src(src: Path) -> tuple[str, Path]:
    """("bag" | "okf-export" | "notebook", payload_root) — SystemExit when
    src is none of them."""
    raise NotImplementedError("WP2")
