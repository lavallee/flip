"""Tests for flip.resolve: the one primitive behind `flip open`/`flip resolve`.

Bare ids must keep resolving exactly as `flip open` always has inside a
notebook; qualified `handle:id` refs resolve through the nearest workspace
table from anywhere under the workspace root; every miss is a loud,
actionable diagnostic — never a guess (SPEC §9). The deprecated '#'
separator still reads, with a stderr note, until 0.10.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import pages
from flip.cli import main
from flip.resolve import known_ids_hint, resolve_ref
from flip.workspace import ws_init


# --- fixtures ---------------------------------------------------------------------


def make_notebook(d: Path, slug: str, uid: str = "") -> Path:
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
        "---\n"
        f"# Title of {slug}\n",
        encoding="utf-8",
    )
    return d


def add_page(nb: Path, entity_id: str, slug: str = "", dirname: str = "references",
             extra_fm: dict | None = None) -> Path:
    fm = {"type": "Source", "id": entity_id, "aliases": [entity_id]}
    fm.update(extra_fm or {})
    slug = slug or f"page-{entity_id.lower()}"
    return pages.write_page(nb / dirname / f"{slug}.md", fm, "notes\n")


def make_ws(tmp_path: Path, *slugs: str) -> Path:
    """A workspace root with one notebook per slug (dir name == slug), initialized."""
    ws_root = tmp_path / "vault"
    ws_root.mkdir(exist_ok=True)
    for slug in slugs:
        make_notebook(ws_root / slug, slug)
    ws_init(ws_root)
    return ws_root


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


# --- bare ids inside a notebook ---------------------------------------------------


def test_bare_id_resolves_in_notebook(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes", uid="nb-r3c1p3s0")
    page_path = add_page(nb, "A3", extra_fm={"title": "Sourdough starter log"})
    r = resolve_ref("A3", start=nb)
    assert r.path == page_path
    assert r.ref == "A3" and r.entity_id == "A3" and r.handle is None
    assert r.notebook_root == nb and r.notebook_slug == "recipes"
    assert r.uid == "nb-r3c1p3s0" and r.title == "Sourdough starter log"


def test_bare_id_matches_flip_open_behavior(tmp_path, monkeypatch):
    """`flip open A3` inside a notebook prints the absolute page path — the
    pre-workspace contract, byte-identical."""
    nb = make_notebook(tmp_path / "recipes", "recipes")
    page_path = add_page(nb, "A3")
    monkeypatch.chdir(nb)
    result = invoke(["open", "A3"])
    assert result.exit_code == 0, result.output
    assert result.output == f"{page_path.resolve()}\n"


def test_bare_id_prefers_containing_notebook_over_workspace(tmp_path):
    """Rule 1 (SPEC §9): inside a notebook, a bare id never consults the
    workspace — even when a sibling notebook carries the same id."""
    ws = make_ws(tmp_path, "recipes", "gardening")
    add_page(ws / "recipes", "A3", extra_fm={"title": "recipes A3"})
    add_page(ws / "gardening", "A3", extra_fm={"title": "gardening A3"})
    r = resolve_ref("A3", start=ws / "recipes")
    assert r.notebook_root == ws / "recipes" and r.title == "recipes A3"


def test_unknown_bare_id_lists_known_ids(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    add_page(nb, "A3")
    add_page(nb, "C1", dirname="claims", extra_fm={"type": "Claim"})
    with pytest.raises(SystemExit) as exc:
        resolve_ref("Z9", start=nb)
    msg = str(exc.value)
    assert "no page with id 'Z9'" in msg
    assert "known ids: A3, C1" in msg


def test_unknown_id_in_empty_notebook_hint(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    assert known_ids_hint(nb) == "no entity pages yet"
    with pytest.raises(SystemExit, match="no entity pages yet"):
        resolve_ref("A3", start=nb)


# --- qualified refs ---------------------------------------------------------------


def test_qualified_resolves_from_workspace_root(tmp_path):
    ws = make_ws(tmp_path, "recipes", "gardening")
    page_path = add_page(ws / "recipes", "A3")
    r = resolve_ref("recipes:A3", start=ws)
    assert r.path == page_path
    assert r.handle == "recipes" and r.notebook_root == ws / "recipes"


def test_qualified_resolves_from_any_dir_under_ws_root(tmp_path):
    ws = make_ws(tmp_path, "recipes")
    page_path = add_page(ws / "recipes", "A3")
    attic = ws / "attic" / "boxes"
    attic.mkdir(parents=True)
    assert resolve_ref("recipes:A3", start=attic).path == page_path


def test_qualified_resolves_from_inside_another_notebook(tmp_path):
    ws = make_ws(tmp_path, "recipes", "gardening")
    page_path = add_page(ws / "recipes", "A3")
    add_page(ws / "gardening", "A3")  # same bare id locally — must not win
    r = resolve_ref("recipes:A3", start=ws / "gardening" / "references")
    assert r.path == page_path and r.handle == "recipes"


def test_qualified_unknown_id_names_notebook_and_hints(tmp_path):
    ws = make_ws(tmp_path, "recipes")
    add_page(ws / "recipes", "A3")
    with pytest.raises(SystemExit) as exc:
        resolve_ref("recipes:Z9", start=ws)
    msg = str(exc.value)
    assert "no page with id 'Z9' in notebook 'recipes'" in msg
    assert "known ids: A3" in msg


def test_unknown_handle_lists_known_handles(tmp_path):
    ws = make_ws(tmp_path, "recipes", "gardening")
    with pytest.raises(SystemExit) as exc:
        resolve_ref("orchard-survey:A3", start=ws)
    msg = str(exc.value)
    assert "unknown handle 'orchard-survey'" in msg
    assert "gardening, recipes" in msg  # sorted
    assert "flip ws list" in msg


def test_unknown_handle_in_empty_workspace_says_none_bound(tmp_path):
    ws = make_ws(tmp_path)  # a table with no notebooks
    with pytest.raises(SystemExit, match="none bound"):
        resolve_ref("recipes:A3", start=ws)


# --- '#' deprecation window -------------------------------------------------------


def test_hash_synonym_resolves_with_stderr_note(tmp_path, capsys):
    ws = make_ws(tmp_path, "recipes")
    page_path = add_page(ws / "recipes", "A3")
    r = resolve_ref("recipes#A3", start=ws)
    assert r.path == page_path and r.handle == "recipes"
    err = capsys.readouterr().err
    assert "deprecated '#'" in err
    assert "recipes:A3" in err  # names the form to use instead
    assert "0.10" in err  # and when '#' reads go away


def test_colon_ref_prints_no_note(tmp_path, capsys):
    ws = make_ws(tmp_path, "recipes")
    add_page(ws / "recipes", "A3")
    resolve_ref("recipes:A3", start=ws)
    assert capsys.readouterr().err == ""


# --- bare ids under a workspace root (outside any notebook) ------------------------


def test_bare_id_at_ws_root_unique_resolves(tmp_path):
    ws = make_ws(tmp_path, "recipes", "gardening")
    page_path = add_page(ws / "gardening", "A3")
    r = resolve_ref("A3", start=ws)
    assert r.path == page_path
    assert r.handle is None  # the ref was bare; provenance still names the notebook
    assert r.notebook_root == ws / "gardening" and r.notebook_slug == "gardening"


def test_bare_id_at_ws_root_ambiguous_lists_qualified_forms(tmp_path):
    ws = make_ws(tmp_path, "recipes", "gardening")
    add_page(ws / "recipes", "A3")
    add_page(ws / "gardening", "A3")
    with pytest.raises(SystemExit) as exc:
        resolve_ref("A3", start=ws)
    msg = str(exc.value)
    assert "'A3' is ambiguous" in msg
    assert "gardening:A3 or recipes:A3" in msg  # both qualified forms, sorted


def test_bare_id_at_ws_root_absent_errors(tmp_path):
    ws = make_ws(tmp_path, "recipes")
    add_page(ws / "recipes", "A3")
    with pytest.raises(SystemExit) as exc:
        resolve_ref("Z9", start=ws)
    assert "no page with id 'Z9' in any notebook bound in" in str(exc.value)


def test_no_notebook_no_workspace_is_canonical_error(tmp_path):
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        resolve_ref("A3", start=tmp_path)


def test_nearest_workspace_beats_outer(tmp_path):
    """A workspace nested under another consults only its own table — the
    nearest .flip/workspace.toml wins, same walk-up rule as notebooks."""
    outer = make_ws(tmp_path, "field-notes")
    add_page(outer / "field-notes", "A3")
    inner = outer / "team"
    inner.mkdir()
    make_notebook(inner / "orchard-survey", "orchard-survey")
    ws_init(inner)
    inner_page = add_page(inner / "orchard-survey", "A3")
    # bare id: only the inner table is scanned, so A3 is unique here
    assert resolve_ref("A3", start=inner).path == inner_page
    # outer handles are invisible from the inner workspace
    with pytest.raises(SystemExit) as exc:
        resolve_ref("field-notes:A3", start=inner)
    msg = str(exc.value)
    assert "unknown handle 'field-notes'" in msg
    assert "orchard-survey" in msg


# --- CLI: flip resolve ------------------------------------------------------------


def test_resolve_cli_plain_prints_path(tmp_path, monkeypatch):
    ws = make_ws(tmp_path, "recipes")
    page_path = add_page(ws / "recipes", "A3")
    monkeypatch.chdir(ws)
    result = invoke(["resolve", "recipes:A3"])
    assert result.exit_code == 0, result.output
    assert result.output == f"{page_path.resolve()}\n"


def test_resolve_cli_json_shape_qualified(tmp_path, monkeypatch):
    ws = make_ws(tmp_path, "recipes")
    make_notebook(ws / "recipes", "recipes", uid="nb-r3c1p3s0")  # stamp a uid
    page_path = add_page(ws / "recipes", "A3",
                         extra_fm={"title": "Sourdough starter log"})
    monkeypatch.chdir(ws)
    result = invoke(["resolve", "recipes:A3", "--json"])
    assert result.exit_code == 0, result.output
    root = ws.resolve()
    assert json.loads(result.output) == {
        "ref": "recipes:A3",
        "id": "A3",
        "handle": "recipes",
        "path": str(root / "recipes" / "references" / "page-a3.md"),
        "notebook_root": str(root / "recipes"),
        "notebook_slug": "recipes",
        "uid": "nb-r3c1p3s0",
        "title": "Sourdough starter log",
    }
    assert Path(json.loads(result.output)["path"]) == page_path.resolve()


def test_resolve_cli_json_bare_ref_has_null_handle(tmp_path, monkeypatch):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    add_page(nb, "A3")
    monkeypatch.chdir(nb)
    result = invoke(["resolve", "A3", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["handle"] is None and data["id"] == "A3" and data["ref"] == "A3"


def test_title_falls_back_to_description(tmp_path):
    nb = make_notebook(tmp_path / "recipes", "recipes")
    add_page(nb, "A3", extra_fm={"description": "a starter, described"})
    assert resolve_ref("A3", start=nb).title == "a starter, described"
