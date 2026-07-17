"""Tests for flip.importer: source classification (notebook dir / OKF export /
BagIt bag), copy hygiene (local dirs and export markers never travel),
uid/origin provenance rules, handle binding with ws_add's collision
semantics, id stability across import, and --update's replace-if-uid-matches
contract. Fixtures are built with flip's own scaffold/export helpers so the
importer is exercised against real bundles, not hand-rolled approximations."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from flip import pages, scaffold, workspace
from flip.export import export_bag
from flip.importer import _classify_src, import_bundle, update_bundle
from flip.manifest import load_manifest, save_manifest
from flip.okf import STATE_FILE, export_okf
from flip.util import UID_RE, WORKSPACE_FILE, today


# --- fixtures ---------------------------------------------------------------------


def make_ws(tmp_path: Path, name: str = "vault") -> Path:
    ws_root = tmp_path / name
    ws_root.mkdir()
    workspace.ws_init(ws_root)
    return ws_root


def make_src(tmp_path: Path, slug: str = "recipes", uid: bool = True) -> Path:
    """A real notebook (flip new) with one source page and one claim citing it."""
    nb = scaffold.create_notebook(
        tmp_path / "bundles" / slug, slug, "scout", title=f"Title of {slug}"
    )
    pages.write_page(
        nb / "references" / "garden-soil.md",
        {"type": "Source", "id": "A3", "aliases": ["A3"], "grade": "B"},
        "# Garden soil survey\n",
    )
    pages.reserve_id(nb, "A3")
    pages.write_page(
        nb / "claims" / "loam-drains-well.md",
        {"type": "Claim", "id": "C1", "aliases": ["C1"], "sources": ["A3"]},
        "Loam drains well; see [A3](../references/garden-soil.md).\n",
    )
    pages.reserve_id(nb, "C1")
    if not uid:
        m = load_manifest(nb)
        m.uid = ""
        save_manifest(nb, m)
    return nb


def bound_paths(ws_root: Path) -> dict[str, str]:
    return workspace.load_workspace(ws_root).notebooks


# --- _classify_src ----------------------------------------------------------------


def test_classify_notebook_dir(tmp_path):
    nb = make_src(tmp_path)
    assert _classify_src(nb) == ("notebook", nb)


def test_classify_okf_export(tmp_path):
    nb = make_src(tmp_path)
    dest = export_okf(nb, tmp_path / "exports" / "recipes-okf", include_private=True)
    assert _classify_src(dest) == ("okf-export", dest)


def test_classify_bag(tmp_path):
    nb = make_src(tmp_path)
    bag = export_bag(nb, tmp_path / "exports" / "recipes-bag")
    assert _classify_src(bag) == ("bag", bag / "data")


def test_classify_rejects_plain_dir(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "notes.md").write_text("# not a bundle\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not an importable bundle"):
        _classify_src(plain)


def test_classify_rejects_bag_without_notebook_payload(tmp_path):
    bag = tmp_path / "junk-bag"
    (bag / "data").mkdir(parents=True)
    (bag / "bagit.txt").write_text("BagIt-Version: 1.0\n", encoding="utf-8")
    (bag / "data" / "index.md").write_text("# no frontmatter\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="data/ is not a flip notebook"):
        _classify_src(bag)


# --- import: sources and copy hygiene -----------------------------------------------


def test_import_notebook_dir_copies_and_binds(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    summary = import_bundle(ws_root, src)
    assert summary["slug"] == "recipes"
    assert summary["handle"] == "recipes"  # default handle is the bundle slug
    assert summary["path"] == "recipes"
    assert UID_RE.match(summary["uid"])
    assert (ws_root / "recipes" / "references" / "garden-soil.md").is_file()
    assert bound_paths(ws_root) == {"recipes": "recipes"}
    assert isinstance(summary["doctor_errors"], int)
    assert isinstance(summary["doctor_warns"], int)


def test_import_okf_export_drops_state_file(tmp_path):
    ws_root = make_ws(tmp_path)
    nb = make_src(tmp_path)
    src = export_okf(nb, tmp_path / "exports" / "recipes-okf", include_private=True)
    summary = import_bundle(ws_root, src)
    dest = ws_root / summary["path"]
    assert (dest / "references" / "garden-soil.md").is_file()
    assert not (dest / STATE_FILE).exists()


def test_import_bag_uses_payload(tmp_path):
    ws_root = make_ws(tmp_path)
    nb = make_src(tmp_path)
    bag = export_bag(nb, tmp_path / "exports" / "recipes-bag")
    summary = import_bundle(ws_root, bag)
    dest = ws_root / summary["path"]
    assert (dest / "index.md").is_file()
    assert not (dest / "bagit.txt").exists()  # bag tag files stay outside the payload
    assert not (dest / "manifest-sha256.txt").exists()
    assert load_manifest(dest).uid == load_manifest(nb).uid  # uid travels through a bag


def test_import_never_copies_local_dirs(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)  # reserve_id already created src/.flip/ids
    (src / ".obsidian").mkdir()
    (src / ".obsidian" / "app.json").write_text("{}\n", encoding="utf-8")
    (src / ".git").mkdir()
    (src / ".git" / "config").write_text("", encoding="utf-8")
    dest = ws_root / import_bundle(ws_root, src)["path"]
    assert not (dest / ".flip").exists()
    assert not (dest / ".obsidian").exists()
    assert not (dest / ".git").exists()


def test_import_skips_nested_export_copy(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    nested = src / "old-export"
    nested.mkdir()
    (nested / "bagit.txt").write_text("BagIt-Version: 1.0\n", encoding="utf-8")
    (nested / "stale.md").write_text("# stale copy\n", encoding="utf-8")
    dest = ws_root / import_bundle(ws_root, src)["path"]
    assert not (dest / "old-export").exists()


# --- import: uid / origin ------------------------------------------------------------


def test_import_pre_uid_source_gets_uid(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path, uid=False)
    summary = import_bundle(ws_root, src)
    assert UID_RE.match(summary["uid"])
    assert load_manifest(ws_root / summary["path"]).uid == summary["uid"]
    assert load_manifest(src).uid == ""  # the source is never touched


def test_import_preserves_existing_uid(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    src_uid = load_manifest(src).uid
    summary = import_bundle(ws_root, src)
    assert summary["uid"] == src_uid
    assert load_manifest(ws_root / summary["path"]).uid == src_uid


def test_import_origin_is_dated(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    dest = ws_root / import_bundle(ws_root, src)["path"]
    assert load_manifest(dest).origin == f"{src.resolve()} (imported {today()})"


# --- import: handles -----------------------------------------------------------------


def test_import_default_handle_normalizes_slug(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path, slug="field.notes")  # dots are slug-legal, handle-illegal
    summary = import_bundle(ws_root, src)
    assert summary["handle"] == "field-notes"
    assert bound_paths(ws_root) == {"field-notes": "field-notes"}


def test_import_handle_collision_error(tmp_path):
    ws_root = make_ws(tmp_path)
    import_bundle(ws_root, make_src(tmp_path))
    rival = make_src(tmp_path / "elsewhere", slug="recipes")
    with pytest.raises(SystemExit) as e:
        import_bundle(ws_root, rival)
    assert "handle 'recipes' is taken" in str(e.value)
    assert "--as recipes-2" in str(e.value)
    assert bound_paths(ws_root) == {"recipes": "recipes"}  # nothing half-bound


def test_import_explicit_handle_avoids_collision(tmp_path):
    ws_root = make_ws(tmp_path)
    import_bundle(ws_root, make_src(tmp_path))
    rival = make_src(tmp_path / "elsewhere", slug="recipes")
    summary = import_bundle(ws_root, rival, handle="orchard-survey")
    assert summary["handle"] == "orchard-survey"
    assert (ws_root / "orchard-survey" / "index.md").is_file()
    assert sorted(bound_paths(ws_root)) == ["orchard-survey", "recipes"]


# --- import: id stability and aliases ------------------------------------------------


def test_import_ids_never_rekeyed(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    dest = ws_root / import_bundle(ws_root, src)["path"]
    page = pages.find_by_id(dest, "A3")
    assert page is not None and page.id == "A3"
    claim = pages.read_page(dest / "claims" / "loam-drains-well.md")
    assert "[A3]" in claim.body  # the citation inside the bundle still reads
    assert page.fm["aliases"] == ["A3", "recipes:A3"]  # qualified alias added after bare
    assert claim.fm["aliases"] == ["C1", "recipes:C1"]


# --- import: destination refusals ----------------------------------------------------


def test_import_dest_exists_refuses(tmp_path):
    ws_root = make_ws(tmp_path)
    (ws_root / "recipes").mkdir()
    with pytest.raises(SystemExit, match="already exists"):
        import_bundle(ws_root, make_src(tmp_path))


def test_import_into_outside_workspace_refuses(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    with pytest.raises(SystemExit, match="outside the workspace root"):
        import_bundle(ws_root, src, into=tmp_path / "elsewhere" / "recipes")
    assert bound_paths(ws_root) == {}


def test_import_into_inside_notebook_refuses(tmp_path):
    ws_root = make_ws(tmp_path)
    import_bundle(ws_root, make_src(tmp_path))
    rival = make_src(tmp_path / "elsewhere", slug="gardening")
    with pytest.raises(SystemExit, match="inside the notebook"):
        import_bundle(ws_root, rival, into=ws_root / "recipes" / "gardening")
    assert not (ws_root / "recipes" / "gardening").exists()


def test_import_outside_workspace_refuses(tmp_path):
    no_ws = tmp_path / "no-workspace"
    no_ws.mkdir()
    with pytest.raises(SystemExit):
        import_bundle(no_ws, make_src(tmp_path))
    assert not (no_ws / WORKSPACE_FILE).exists()


# --- update ---------------------------------------------------------------------------


def test_update_replaces_pages_keeps_local_reservations(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    dest = ws_root / import_bundle(ws_root, src)["path"]
    local_id = pages.allocate_id(dest, "Q")  # a local-only reservation
    # the source moves on: one page gains text, one page disappears, one is new
    (src / "claims" / "loam-drains-well.md").unlink()
    pages.write_page(
        src / "references" / "orchard-map.md",
        {"type": "Source", "id": "A4", "aliases": ["A4"], "grade": "C"},
        "# Orchard map\n",
    )
    update_bundle(ws_root, "recipes", src)
    assert (dest / "references" / "orchard-map.md").is_file()
    assert not (dest / "claims" / "loam-drains-well.md").exists()
    assert local_id in pages.reserved_ids(dest)  # .flip/ids survived the refresh
    assert load_manifest(dest).uid == load_manifest(src).uid


def test_update_uid_mismatch_refuses(tmp_path):
    ws_root = make_ws(tmp_path)
    import_bundle(ws_root, make_src(tmp_path))
    stranger = make_src(tmp_path / "elsewhere", slug="recipes")  # fresh uid, same slug
    with pytest.raises(SystemExit, match="uid mismatch"):
        update_bundle(ws_root, "recipes", stranger)
    assert (ws_root / "recipes" / "claims" / "loam-drains-well.md").is_file()


def test_update_one_sided_uid_refuses(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    import_bundle(ws_root, src)  # bound copy has a uid
    m = load_manifest(src)
    m.uid = ""
    save_manifest(src, m)  # the offered copy lost its uid
    with pytest.raises(SystemExit, match="uid mismatch"):
        update_bundle(ws_root, "recipes", src)


def test_update_both_pre_uid_mints_shared_uid(tmp_path):
    ws_root = make_ws(tmp_path)
    local = make_src(ws_root, slug="gardening", uid=False)  # a pre-uid copy already in place
    workspace.ws_add(ws_root, local, "gardening")
    src = make_src(tmp_path / "elsewhere", slug="gardening", uid=False)
    summary = update_bundle(ws_root, "gardening", src)
    assert UID_RE.match(summary["uid"])
    assert load_manifest(local).uid == summary["uid"]  # written locally…
    assert load_manifest(src).uid == ""  # …never to the source


def test_update_src_is_bound_copy_refuses_before_deleting(tmp_path):
    # `flip import --update recipes <ws>/recipes` — a plausible arg mixup that
    # must never wipe the notebook (the refresh deletes dest before copying).
    ws_root = make_ws(tmp_path)
    dest = ws_root / import_bundle(ws_root, make_src(tmp_path))["path"]
    with pytest.raises(SystemExit, match="overlaps the bound copy"):
        update_bundle(ws_root, "recipes", dest)
    assert (dest / "claims" / "loam-drains-well.md").is_file()  # nothing deleted


def test_update_src_inside_bound_copy_refuses_before_deleting(tmp_path):
    # A backup copy stored inside the bound dir would be destroyed by the wipe.
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    dest = ws_root / import_bundle(ws_root, src)["path"]
    backup = dest / "backup"
    shutil.copytree(src, backup)
    with pytest.raises(SystemExit, match="overlaps the bound copy"):
        update_bundle(ws_root, "recipes", backup)
    assert (backup / "index.md").is_file()
    assert (dest / "claims" / "loam-drains-well.md").is_file()


def test_update_src_containing_bound_copy_refuses(tmp_path):
    # dest nested inside src: a bag whose data/ payload was bound in place —
    # "updating" from the bag would wipe the very payload being copied.
    ws_root = make_ws(tmp_path)
    nb = make_src(tmp_path)
    bag = ws_root / "recipes-bag"
    bag.mkdir()
    (bag / "bagit.txt").write_text("BagIt-Version: 1.0\n", encoding="utf-8")
    shutil.copytree(nb, bag / "data")
    workspace.ws_add(ws_root, bag / "data", "recipes")
    with pytest.raises(SystemExit, match="overlaps the bound copy"):
        update_bundle(ws_root, "recipes", bag)
    assert (bag / "data" / "claims" / "loam-drains-well.md").is_file()


def test_update_unknown_handle_refuses(tmp_path):
    ws_root = make_ws(tmp_path)
    import_bundle(ws_root, make_src(tmp_path))
    with pytest.raises(SystemExit, match="unknown handle 'gardening'"):
        update_bundle(ws_root, "gardening", make_src(tmp_path / "elsewhere"))


def test_update_refreshes_origin_and_requalifies_aliases(tmp_path):
    ws_root = make_ws(tmp_path)
    first = make_src(tmp_path)
    dest = ws_root / import_bundle(ws_root, first)["path"]
    moved = tmp_path / "handed-over" / "recipes"
    moved.parent.mkdir()
    first.rename(moved)  # the same lineage now arrives from a new path
    pages.write_page(
        moved / "references" / "orchard-map.md",
        {"type": "Source", "id": "A4", "aliases": ["A4"], "grade": "C"},
        "# Orchard map\n",
    )
    update_bundle(ws_root, "recipes", moved)
    assert load_manifest(dest).origin == f"{moved.resolve()} (imported {today()})"
    new_page = pages.read_page(dest / "references" / "orchard-map.md")
    assert new_page.fm["aliases"] == ["A4", "recipes:A4"]


def test_update_from_okf_export_roundtrip(tmp_path):
    ws_root = make_ws(tmp_path)
    src = make_src(tmp_path)
    dest = ws_root / import_bundle(ws_root, src)["path"]
    pages.write_page(
        src / "references" / "orchard-map.md",
        {"type": "Source", "id": "A4", "aliases": ["A4"], "grade": "C"},
        "# Orchard map\n",
    )
    bundle = export_okf(src, tmp_path / "exports" / "recipes-okf", include_private=True)
    update_bundle(ws_root, "recipes", bundle)  # uid travelled through the export
    assert (dest / "references" / "orchard-map.md").is_file()
    assert not (dest / STATE_FILE).exists()
    assert load_manifest(dest).uid == load_manifest(src).uid
