"""Tests for flip.workspace: the workspace table (SPEC §18), notebook
discovery, handle lifecycle (init/add/rename/rm), qualified-alias
maintenance, and the rename ref rewrite with its adversarial edges."""

from __future__ import annotations

from pathlib import Path

import pytest

from flip import pages
from flip.manifest import load_manifest
from flip.util import WORKSPACE_FILE, find_workspace_root
from flip.workspace import (
    Workspace,
    discover_notebooks,
    default_handle,
    ensure_qualified_aliases,
    load_workspace,
    require_valid_handle,
    require_workspace_root,
    save_workspace,
    ws_add,
    ws_init,
    ws_rename,
    ws_rm,
    ws_rows,
    _rewrite_qualified_refs,
)


# --- fixtures ---------------------------------------------------------------------


def make_notebook(d: Path, slug: str, uid: str = "", links: str = "") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    uid_line = f"uid: {uid}\n" if uid else ""
    (d / "index.md").write_text(
        "---\n"
        'okf_version: "0.1"\n'
        'flip: "0.5"\n'
        f"slug: {slug}\n"
        f"{uid_line}"
        f"title: Title of {slug}\n"
        "kind: scout\n"
        "status: active\n"
        "created: 2026-07-01\n"
        "updated: 2026-07-02\n"
        f"{links}"
        "---\n"
        f"# Title of {slug}\n",
        encoding="utf-8",
    )
    return d


def make_beat(d: Path, slug: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(
        '---\nokf_version: "0.1"\nflip_beat: "0.1"\n'
        f"slug: {slug}\nmission: keep watch\n---\n# beat\n",
        encoding="utf-8",
    )
    return d


def add_page(nb: Path, entity_id: str, slug: str = "", dirname: str = "references",
             aliases=None, extra_fm: dict | None = None, body: str = "notes\n") -> Path:
    fm = {"type": "Source", "id": entity_id,
          "aliases": [entity_id] if aliases is None else aliases}
    fm.update(extra_fm or {})
    slug = slug or f"page-{entity_id.lower()}"
    return pages.write_page(nb / dirname / f"{slug}.md", fm, body)


def make_ws(tmp_path: Path, *slugs: str) -> Path:
    """A workspace root with one notebook per slug (dir name == slug), initialized."""
    ws_root = tmp_path / "vault"
    ws_root.mkdir(exist_ok=True)
    for slug in slugs:
        make_notebook(ws_root / slug, slug)
    ws_init(ws_root)
    return ws_root


def aliases_of(path: Path) -> list:
    return pages.as_list(pages.read_page(path).fm.get("aliases"))


# --- table round-trip -------------------------------------------------------------


def test_save_load_round_trip_awkward_paths(tmp_path):
    ws = Workspace(root=tmp_path)
    ws.notebooks = {
        "recipes": "kitchen notes/recipes",  # space
        "gardening": 'plots/"the" garden',  # double quotes
        "orchard": "vergers/récolte-2026",  # unicode
    }
    save_workspace(ws)
    loaded = load_workspace(tmp_path)
    assert loaded.notebooks == ws.notebooks
    assert loaded.version == ws.version
    assert loaded.root == tmp_path


def test_save_workspace_sorted_and_deterministic(tmp_path):
    ws = Workspace(root=tmp_path)
    ws.notebooks = {"recipes": "recipes", "field-notes": "notes", "apiary": "bees"}
    save_workspace(ws)
    first = (tmp_path / WORKSPACE_FILE).read_text(encoding="utf-8")
    ws.notebooks = {"apiary": "bees", "field-notes": "notes", "recipes": "recipes"}
    save_workspace(ws)
    assert (tmp_path / WORKSPACE_FILE).read_text(encoding="utf-8") == first
    body = first[first.index("[notebooks]"):]
    assert body.index("apiary") < body.index("field-notes") < body.index("recipes")


def test_load_workspace_reads_hand_edits_with_comments(tmp_path):
    path = tmp_path / WORKSPACE_FILE
    path.parent.mkdir(parents=True)
    path.write_text(
        "# my own note\n[workspace]\nversion = \"0.1\"\n\n"
        "[notebooks]\nrecipes = \"recipes\"  # inline comment\n",
        encoding="utf-8",
    )
    assert load_workspace(tmp_path).notebooks == {"recipes": "recipes"}


def test_load_workspace_bad_toml_is_one_liner(tmp_path):
    path = tmp_path / WORKSPACE_FILE
    path.parent.mkdir(parents=True)
    # duplicate keys are a TOMLDecodeError — the design's duplicate-handle case
    path.write_text(
        '[workspace]\nversion = "0.1"\n[notebooks]\na = "x"\na = "y"\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="invalid TOML"):
        load_workspace(tmp_path)


def test_load_workspace_missing_version_and_newer_major(tmp_path):
    path = tmp_path / WORKSPACE_FILE
    path.parent.mkdir(parents=True)
    path.write_text("[notebooks]\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"missing \[workspace\] version"):
        load_workspace(tmp_path)
    path.write_text('[workspace]\nversion = "1.0"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="upgrade flip"):
        load_workspace(tmp_path)


def test_load_workspace_non_string_path_rejected(tmp_path):
    path = tmp_path / WORKSPACE_FILE
    path.parent.mkdir(parents=True)
    path.write_text(
        '[workspace]\nversion = "0.1"\n[notebooks]\nrecipes = 3\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="must be a string path"):
        load_workspace(tmp_path)


# --- handles ----------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "Recipes", "2cool", "_x", "a_b", "a.b", "-a", "a b"])
def test_require_valid_handle_rejects(bad):
    with pytest.raises(SystemExit, match="invalid handle"):
        require_valid_handle(bad)


def test_default_handle_narrows_slug_charset():
    assert default_handle("field.notes_2026", set()) == "field-notes-2026"
    assert default_handle("2026-orchard", set()) == "n2026-orchard"
    assert default_handle("recipes", set()) == "recipes"


def test_default_handle_suffixes_past_collisions():
    assert default_handle("recipes", {"recipes"}) == "recipes-2"
    assert default_handle("recipes", {"recipes", "recipes-2"}) == "recipes-3"


# --- root discovery (find_workspace_root) ------------------------------------------


def test_find_workspace_root_nested_inner_wins(tmp_path):
    outer, inner = tmp_path / "outer", tmp_path / "outer" / "inner"
    for d in (outer, inner):
        (d / ".flip").mkdir(parents=True)
        save_workspace(Workspace(root=d))
    sub = inner / "deep" / "down"
    sub.mkdir(parents=True)
    assert find_workspace_root(sub) == inner
    assert find_workspace_root(outer / "elsewhere-missing") == outer


def test_require_workspace_root_exits_outside(tmp_path):
    with pytest.raises(SystemExit, match="flip ws init"):
        require_workspace_root(tmp_path)


# --- discover_notebooks -------------------------------------------------------------


def test_discover_finds_nested_notebooks_in_order(tmp_path):
    make_notebook(tmp_path / "recipes", "recipes")
    make_notebook(tmp_path / "plots" / "gardening", "gardening")
    found = discover_notebooks(tmp_path)
    assert found == [tmp_path / "plots" / "gardening", tmp_path / "recipes"]


def test_discover_skips_dot_dirs_and_prune_dirs(tmp_path):
    make_notebook(tmp_path / "kept", "kept")
    for junk in (".obsidian", ".git", "node_modules", "renders", "__pycache__", ".venv"):
        make_notebook(tmp_path / junk / "hidden", "hidden")
    assert discover_notebooks(tmp_path) == [tmp_path / "kept"]


def test_discover_skips_export_copies(tmp_path):
    make_notebook(tmp_path / "recipes", "recipes")
    bag = tmp_path / "recipes-bag"
    make_notebook(bag / "data", "recipes")
    (bag / "bagit.txt").write_text("BagIt-Version: 1.0\n", encoding="utf-8")
    okf = make_notebook(tmp_path / "recipes-okf", "recipes")
    (okf / ".last-export.json").write_text("{}\n", encoding="utf-8")
    assert discover_notebooks(tmp_path) == [tmp_path / "recipes"]


def test_discover_notebook_inside_notebook_counted_once(tmp_path):
    outer = make_notebook(tmp_path / "outer", "outer")
    make_notebook(outer / "embedded", "embedded")  # never descended into
    assert discover_notebooks(tmp_path) == [outer]


def test_discover_descends_beat_roots(tmp_path):
    beat = make_beat(tmp_path / "orchard-survey", "orchard-survey")
    child = make_notebook(beat / "notebooks" / "field-notes", "field-notes")
    found = discover_notebooks(tmp_path)
    assert found == [child]  # the beat root itself is not a notebook


# --- ws_init ------------------------------------------------------------------------


def test_ws_init_binds_discovered_notebooks(tmp_path):
    ws_root = tmp_path / "vault"
    make_notebook(ws_root / "recipes", "recipes")
    make_notebook(ws_root / "plots" / "gardening", "gardening")
    ws = ws_init(ws_root)
    assert ws.notebooks == {"recipes": "recipes", "gardening": "plots/gardening"}
    assert load_workspace(ws_root).notebooks == ws.notebooks


def test_ws_init_refuses_existing_workspace_file(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    with pytest.raises(SystemExit, match="already exists"):
        ws_init(ws_root)


def test_ws_init_refuses_notebook_root(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    with pytest.raises(SystemExit, match="one level up"):
        ws_init(nb)
    assert not (nb / WORKSPACE_FILE).exists()


def test_ws_init_auto_suffixes_slug_collisions(tmp_path, capsys):
    ws_root = tmp_path / "vault"
    make_notebook(ws_root / "a" / "recipes", "recipes")
    make_notebook(ws_root / "b" / "recipes", "recipes")
    ws = ws_init(ws_root)
    assert ws.notebooks == {"recipes": "a/recipes", "recipes-2": "b/recipes"}
    assert "recipes-2" in capsys.readouterr().err  # the note is loud


def test_ws_init_adds_qualified_aliases(tmp_path):
    ws_root = tmp_path / "vault"
    nb = make_notebook(ws_root / "recipes", "recipes")
    page = add_page(nb, "A3")
    ws_init(ws_root)
    assert aliases_of(page) == ["A3", "recipes:A3"]


def test_ws_init_empty_dir_makes_empty_table(tmp_path):
    ws = ws_init(tmp_path)
    assert ws.notebooks == {}
    assert ws_rows(tmp_path) == []


# --- ws_add -------------------------------------------------------------------------


def test_ws_add_binds_default_handle_and_aliases(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    nb = make_notebook(ws_root / "plots" / "gardening", "gardening")
    page = add_page(nb, "C7", dirname="claims")
    handle, rel = ws_add(ws_root, nb)
    assert (handle, rel) == ("gardening", "plots/gardening")
    assert load_workspace(ws_root).notebooks["gardening"] == "plots/gardening"
    assert aliases_of(page) == ["C7", "gardening:C7"]


def test_ws_add_requires_notebook_root(tmp_path):
    ws_root = make_ws(tmp_path)
    plain = ws_root / "just-files"
    plain.mkdir()
    with pytest.raises(SystemExit, match="not a flip notebook root"):
        ws_add(ws_root, plain)


def test_ws_add_outside_workspace_refused(tmp_path):
    ws_root = make_ws(tmp_path)
    stray = make_notebook(tmp_path / "elsewhere", "stray")
    with pytest.raises(SystemExit, match="outside the workspace root"):
        ws_add(ws_root, stray)


def test_ws_add_collision_lists_taken_and_suggests(tmp_path):
    ws_root = make_ws(tmp_path, "recipes", "gardening")
    make_notebook(ws_root / "more" / "recipes", "recipes")
    with pytest.raises(SystemExit) as exc:
        ws_add(ws_root, ws_root / "more" / "recipes")
    msg = str(exc.value)
    assert "handle 'recipes' is taken" in msg
    assert "gardening, recipes" in msg
    assert "--as recipes-2" in msg


def test_ws_add_explicit_handle_collision_and_validation(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    nb = make_notebook(ws_root / "second", "second")
    with pytest.raises(SystemExit, match="handle 'recipes' is taken"):
        ws_add(ws_root, nb, "recipes")
    with pytest.raises(SystemExit, match="invalid handle"):
        ws_add(ws_root, nb, "Second")
    handle, _rel = ws_add(ws_root, nb, "backup-recipes")
    assert handle == "backup-recipes"


def test_ws_add_already_bound_path_refused(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    with pytest.raises(SystemExit, match="already bound as 'recipes'"):
        ws_add(ws_root, ws_root / "recipes", "other")


# --- ws_rows ------------------------------------------------------------------------


def test_ws_rows_statuses(tmp_path):
    ws_root = make_ws(tmp_path)
    make_notebook(ws_root / "recipes", "recipes", uid="nb-0123456b")
    ws_add(ws_root, ws_root / "recipes")
    ws = load_workspace(ws_root)
    ws.notebooks["ghost"] = "gone"
    ws.notebooks["shed"] = "shed"
    save_workspace(ws)
    (ws_root / "shed").mkdir()  # a dir with no flip index.md
    rows = ws_rows(ws_root)
    assert [r["handle"] for r in rows] == ["ghost", "recipes", "shed"]  # sorted
    by_handle = {r["handle"]: r for r in rows}
    ok = by_handle["recipes"]
    assert (ok["status"], ok["slug"], ok["uid"], ok["path"], ok["title"]) == (
        "ok", "recipes", "nb-0123456b", "recipes", "Title of recipes"
    )
    assert by_handle["ghost"]["status"] == "missing"
    assert by_handle["shed"]["status"] == "not-a-notebook"


# --- ensure_qualified_aliases -------------------------------------------------------


def test_ensure_inserts_qualified_right_after_bare_id(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page = add_page(nb, "A3", aliases=["Fancy Name", "A3", "old brine notes"])
    assert ensure_qualified_aliases(nb, "recipes") == 1
    assert aliases_of(page) == ["Fancy Name", "A3", "recipes:A3", "old brine notes"]


def test_ensure_appends_missing_bare_id_first(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page = add_page(nb, "A3", aliases=["Fancy Name"])
    ensure_qualified_aliases(nb, "recipes")
    assert aliases_of(page) == ["Fancy Name", "A3", "recipes:A3"]


def test_ensure_untouched_page_is_byte_identical(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page = add_page(nb, "A3", aliases=["A3", "recipes:A3"])
    before = page.read_bytes()
    assert ensure_qualified_aliases(nb, "recipes") == 0
    assert page.read_bytes() == before


def test_ensure_idempotent_second_run_changes_nothing(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    add_page(nb, "A3", aliases=["Fancy"])
    add_page(nb, "C7", dirname="claims")
    assert ensure_qualified_aliases(nb, "recipes") == 2
    assert ensure_qualified_aliases(nb, "recipes") == 0


def test_ensure_preserves_foreign_frontmatter_and_body(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page = add_page(
        nb, "A3", aliases=["A3"],
        extra_fm={"beekeeper": {"hive": 4}, "tags": ["brine", "pickles"]},
        body="Some notes citing [C7].\n",
    )
    ensure_qualified_aliases(nb, "recipes")
    got = pages.read_page(page)
    assert got.fm["beekeeper"] == {"hive": 4}
    assert got.fm["tags"] == ["brine", "pickles"]
    assert list(got.fm) == ["type", "id", "aliases", "beekeeper", "tags"]  # order kept
    assert got.body == "Some notes citing [C7].\n"


def test_ensure_removes_only_old_handle_alias(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page = add_page(nb, "A3", aliases=["A3", "old:A3", "pantry:A3"])
    ensure_qualified_aliases(nb, "new", old_handle="old")
    assert aliases_of(page) == ["A3", "new:A3", "pantry:A3"]


def test_ensure_handle_none_still_ensures_bare_id(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page = add_page(nb, "A3", aliases=["Fancy"])
    ensure_qualified_aliases(nb, None)
    assert aliases_of(page) == ["Fancy", "A3"]


def test_ensure_scalar_alias_treated_as_one_item(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page = pages.write_page(
        nb / "references" / "brine.md",
        {"type": "Source", "id": "A3", "aliases": "A3"}, "notes\n",
    )
    ensure_qualified_aliases(nb, "recipes")
    assert aliases_of(page) == ["A3", "recipes:A3"]


def test_ensure_skips_pages_without_id_and_broken_pages(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    pages.write_page(nb / "analysis" / "overview.md", {"type": "Analysis"}, "no id\n")
    (nb / "claims").mkdir()
    (nb / "claims" / "broken.md").write_text("---\n: bad: [yaml\n---\n", encoding="utf-8")
    assert ensure_qualified_aliases(nb, "recipes") == 0


# --- ws_rm --------------------------------------------------------------------------


def test_ws_rm_unbinds_strips_own_aliases_keeps_files(tmp_path):
    ws_root = make_ws(tmp_path, "recipes", "gardening")
    page = add_page(ws_root / "recipes", "A3",
                    aliases=["A3", "recipes:A3", "gardening:A3", "Fancy"])
    ws_rm(ws_root, "recipes")
    assert "recipes" not in load_workspace(ws_root).notebooks
    assert (ws_root / "recipes" / "index.md").exists()  # never deletes files
    assert aliases_of(page) == ["A3", "gardening:A3", "Fancy"]  # only its own alias


def test_ws_rm_unknown_handle_lists_known(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    with pytest.raises(SystemExit, match=r"unknown handle 'nope' \(known handles: recipes\)"):
        ws_rm(ws_root, "nope")


def test_ws_rm_tolerates_missing_directory(tmp_path):
    ws_root = make_ws(tmp_path)
    ws = load_workspace(ws_root)
    ws.notebooks["ghost"] = "gone"
    save_workspace(ws)
    ws_rm(ws_root, "ghost")
    assert load_workspace(ws_root).notebooks == {}


# --- ws_rename ----------------------------------------------------------------------


def test_ws_rename_rebinds_and_updates_aliases(tmp_path):
    ws_root = make_ws(tmp_path, "recipes", "gardening")
    page = add_page(ws_root / "recipes", "A3", aliases=["A3", "recipes:A3"])
    ws_rename(ws_root, "recipes", "pantry")
    assert load_workspace(ws_root).notebooks == {
        "pantry": "recipes", "gardening": "gardening"
    }
    assert aliases_of(page) == ["A3", "pantry:A3"]


def test_ws_rename_rewrites_prose_wikilinks_labels_frontmatter(tmp_path):
    ws_root = make_ws(tmp_path, "recipes", "gardening")
    add_page(ws_root / "recipes", "A3")
    note = add_page(
        ws_root / "gardening", "C1", dirname="claims",
        extra_fm={"supports": ["recipes:A3"]},
        body=(
            "Prose cite [recipes:A3] and wikilink [[recipes:A3]].\n"
            "Labeled [[references/brine.md|recipes:A3]] too.\n"
        ),
    )
    loose = ws_root / "notes.md"
    loose.write_text("Vault-level pointer to recipes:A3.\n", encoding="utf-8")
    changed, alias_pages = ws_rename(ws_root, "recipes", "pantry")
    assert changed == 2  # the claim page and the loose note
    assert alias_pages == 1  # recipes' A3 page: recipes:A3 → pantry:A3
    got = pages.read_page(note)
    assert got.fm["supports"] == ["pantry:A3"]
    assert "[pantry:A3]" in got.body and "[[pantry:A3]]" in got.body
    assert "|pantry:A3]]" in got.body
    assert "recipes:A3" not in got.body
    assert loose.read_text(encoding="utf-8") == "Vault-level pointer to pantry:A3.\n"


def test_ws_rename_other_handle_substring_untouched(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    note = ws_root / "notes.md"
    note.write_text(
        "Mine: recipes:A3. Not mine: field-recipes:A3, myrecipes:A3, "
        "old_recipes:A3.\n",
        encoding="utf-8",
    )
    ws_rename(ws_root, "recipes", "pantry")
    assert note.read_text(encoding="utf-8") == (
        "Mine: pantry:A3. Not mine: field-recipes:A3, myrecipes:A3, "
        "old_recipes:A3.\n"
    )


def test_ws_rename_requires_compact_id_after_colon(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    note = ws_root / "notes.md"
    note.write_text(
        "Not refs: recipes:notafile.md recipes:a3 recipes:A recipes:A3x recipes:.\n"
        "Refs: recipes:A3 recipes:TH12, and recipes:A3.\n",
        encoding="utf-8",
    )
    ws_rename(ws_root, "recipes", "pantry")
    text = note.read_text(encoding="utf-8")
    assert text.splitlines()[0] == (
        "Not refs: recipes:notafile.md recipes:a3 recipes:A recipes:A3x recipes:."
    )
    assert text.splitlines()[1] == "Refs: pantry:A3 pantry:TH12, and pantry:A3."


def test_ws_rename_fenced_code_untouched(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    note = ws_root / "notes.md"
    note.write_text(
        "Outside recipes:A3.\n```\nfenced recipes:A3 stays\n```\nAfter recipes:A3.\n",
        encoding="utf-8",
    )
    ws_rename(ws_root, "recipes", "pantry")
    assert note.read_text(encoding="utf-8") == (
        "Outside pantry:A3.\n```\nfenced recipes:A3 stays\n```\nAfter pantry:A3.\n"
    )


def test_ws_rename_never_edits_sources_derived_renders_or_copies(tmp_path):
    ws_root = make_ws(tmp_path, "recipes", "gardening")
    keep = "Captured cite recipes:A3.\n"
    victims = []
    for sub in ("sources/raw", "derived", "renders"):
        p = ws_root / "gardening" / sub / "capture.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(keep, encoding="utf-8")
        victims.append(p)
    bag = ws_root / "gardening-bag"
    bag.mkdir()
    (bag / "bagit.txt").write_text("BagIt-Version: 1.0\n", encoding="utf-8")
    (bag / "copy.md").write_text(keep, encoding="utf-8")
    victims.append(bag / "copy.md")
    changed, _aliases = ws_rename(ws_root, "recipes", "pantry")
    assert changed == 0
    for p in victims:
        assert p.read_text(encoding="utf-8") == keep


def test_ws_rename_links_beat_survives_slug_collision(tmp_path):
    # A notebook graduated from a beat whose slug equals the renamed handle:
    # links.beat is a beat ref, not a workspace ref, and must not be rewritten.
    ws_root = tmp_path / "vault"
    make_notebook(ws_root / "recipes", "recipes")
    make_notebook(
        ws_root / "gardening", "gardening",
        links='links:\n  beat: "recipes:TH1"\n  upstream: "recipes:A3"\n',
    )
    ws_init(ws_root)
    changed, _aliases = ws_rename(ws_root, "recipes", "pantry")
    assert changed == 1  # gardening's index.md, rewritten structurally
    links = load_manifest(ws_root / "gardening").links
    assert links["beat"] == "recipes:TH1"
    assert links["upstream"] == "pantry:A3"


def test_ws_rename_rewrites_bound_root_index_body(tmp_path):
    # The root index.md frontmatter is handled structurally (links.beat must
    # survive) but its *body* is prose like any other page: qualified refs
    # there are rewritten too, and the file counts once even when both body
    # and frontmatter change.
    ws_root = tmp_path / "vault"
    make_notebook(ws_root / "recipes", "recipes")
    make_notebook(
        ws_root / "gardening", "gardening",
        links='links:\n  beat: "recipes:TH1"\n  upstream: "recipes:A3"\n',
    )
    index = ws_root / "gardening" / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8") + "\nSee recipes:A3 for the soil survey.\n",
        encoding="utf-8",
    )
    ws_init(ws_root)
    changed, _aliases = ws_rename(ws_root, "recipes", "pantry")
    assert changed == 1  # gardening's index.md: body + frontmatter, one file
    assert "See pantry:A3 for the soil survey." in index.read_text(encoding="utf-8")
    links = load_manifest(ws_root / "gardening").links
    assert links["beat"] == "recipes:TH1"
    assert links["upstream"] == "pantry:A3"


def test_ws_rename_protects_unbound_notebook_beat_link(tmp_path):
    # An unregistered notebook (doctor WARNs, a supported state) whose beat
    # slug collides with the renamed handle: its links.beat must survive just
    # like a bound notebook's, while its other qualified refs are rewritten.
    ws_root = tmp_path / "vault"
    make_notebook(ws_root / "recipes", "recipes")
    ws_init(ws_root)  # binds recipes only
    unbound = make_notebook(
        ws_root / "field-notes", "field-notes",
        links='links:\n  beat: "recipes:TH1"\n  upstream: "recipes:A3"\n',
    )
    ws_rename(ws_root, "recipes", "pantry")
    assert "field-notes" not in load_workspace(ws_root).notebooks  # still unbound
    links = load_manifest(unbound).links
    assert links["beat"] == "recipes:TH1"  # beat lineage intact
    assert links["upstream"] == "pantry:A3"


def test_ws_rename_refusals(tmp_path):
    ws_root = make_ws(tmp_path, "recipes", "gardening")
    with pytest.raises(SystemExit, match="unknown handle 'nope'"):
        ws_rename(ws_root, "nope", "pantry")
    with pytest.raises(SystemExit, match="already bound"):
        ws_rename(ws_root, "recipes", "gardening")
    with pytest.raises(SystemExit, match="invalid handle"):
        ws_rename(ws_root, "recipes", "Pantry")
    with pytest.raises(SystemExit, match="nothing to do"):
        ws_rename(ws_root, "recipes", "recipes")


def test_rewrite_qualified_refs_counts_files_once(tmp_path):
    ws_root = make_ws(tmp_path, "recipes")
    note = ws_root / "notes.md"
    note.write_text("recipes:A3 twice recipes:C7.\n", encoding="utf-8")
    assert _rewrite_qualified_refs(ws_root, "recipes", "pantry") == 1
    assert note.read_text(encoding="utf-8") == "pantry:A3 twice pantry:C7.\n"
