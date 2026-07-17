"""Obsidian vault prep tests — `flip obsidian` / obsidian.prepare_vault.

The contract (SPEC §12): merge-write, never clobber — an existing
.obsidian/ config keeps every key flip doesn't own; the packaged plugin
lands intact; a second run is a no-op; and `.obsidian/` never ships in
exports (it is editor-local state).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from flip.beat import create_beat
from flip.cli import main
from flip.obsidian import PLUGIN_FILES, PLUGIN_ID, prepare_vault
from flip.okf import export_okf
from flip.scaffold import create_notebook


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def make_notebook(dest: Path, visibility: str | None = None) -> Path:
    return create_notebook(dest, "demo", "scout", visibility=visibility)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- app.json


def test_prepare_creates_app_json_and_plugin(tmp_path):
    root = make_notebook(tmp_path / "demo")
    actions = prepare_vault(root)
    assert len(actions) == 3  # app.json, plugin files, community-plugins.json
    app = read_json(root / ".obsidian" / "app.json")
    assert app == {"useMarkdownLinks": True, "newLinkFormat": "relative"}
    enabled = read_json(root / ".obsidian" / "community-plugins.json")
    assert enabled == [PLUGIN_ID]
    plugin_dir = root / ".obsidian" / "plugins" / PLUGIN_ID
    assert sorted(p.name for p in plugin_dir.iterdir()) == sorted(PLUGIN_FILES)
    manifest = read_json(plugin_dir / "manifest.json")
    assert manifest["id"] == PLUGIN_ID
    assert manifest["isDesktopOnly"] is True


def test_app_json_merge_preserves_foreign_keys(tmp_path):
    root = make_notebook(tmp_path / "demo")
    obsidian = root / ".obsidian"
    obsidian.mkdir()
    (obsidian / "app.json").write_text(
        json.dumps({"readableLineLength": False, "newLinkFormat": "shortest"}),
        encoding="utf-8",
    )
    prepare_vault(root)
    app = read_json(obsidian / "app.json")
    assert app["readableLineLength"] is False  # foreign key survives
    assert app["useMarkdownLinks"] is True
    assert app["newLinkFormat"] == "relative"  # flip's setting wins


def test_corrupt_app_json_is_refused_actionably(tmp_path):
    root = make_notebook(tmp_path / "demo")
    obsidian = root / ".obsidian"
    obsidian.mkdir()
    (obsidian / "app.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="app.json"):
        prepare_vault(root)


# ---------------------------------------------------------------- community-plugins


def test_community_plugins_merge_keeps_existing_and_never_duplicates(tmp_path):
    root = make_notebook(tmp_path / "demo")
    obsidian = root / ".obsidian"
    obsidian.mkdir()
    (obsidian / "community-plugins.json").write_text(
        json.dumps(["dataview"]), encoding="utf-8"
    )
    prepare_vault(root)
    assert read_json(obsidian / "community-plugins.json") == ["dataview", PLUGIN_ID]
    prepare_vault(root)  # again: no duplicate
    assert read_json(obsidian / "community-plugins.json") == ["dataview", PLUGIN_ID]


def test_no_plugin_skips_plugin_install(tmp_path):
    root = make_notebook(tmp_path / "demo")
    actions = prepare_vault(root, with_plugin=False)
    assert len(actions) == 1
    assert (root / ".obsidian" / "app.json").exists()
    assert not (root / ".obsidian" / "plugins").exists()
    assert not (root / ".obsidian" / "community-plugins.json").exists()


# ---------------------------------------------------------------- idempotency / roots


def test_second_run_changes_nothing(tmp_path):
    root = make_notebook(tmp_path / "demo")
    assert prepare_vault(root)  # first run acts
    tree = root / ".obsidian"
    before = {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}
    assert prepare_vault(root) == []  # second run: no actions
    after = {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}
    assert before == after


def test_beat_root_is_accepted(tmp_path):
    root = create_beat(tmp_path / "mybeat", "mybeat", mission="test the vault prep")
    actions = prepare_vault(root)
    assert len(actions) == 3
    assert (root / ".obsidian" / "plugins" / PLUGIN_ID / "main.js").exists()


def test_non_root_is_refused(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(SystemExit, match="not a flip notebook, beat, or workspace root"):
        prepare_vault(plain)
    assert not (plain / ".obsidian").exists()  # refused before writing anything


# ---------------------------------------------------------------- workspace roots
#
# The plugin side (main.js) has no JS test harness — no build step, no deps
# is the point — so its workspace behavior is covered by the marker test
# below plus this manual checklist, run in Obsidian against a prepared
# workspace vault (two notebooks bound, e.g. recipes + gardening):
#
#   1. Panel shows the "workspace" badge and `flip doctor --workspace --json`
#      findings; hot view says per-notebook.
#   2. Open-by-id lists ids from every bound notebook as handle:id
#      (recipes:A3), labels suffixed with the handle, and opens them.
#   3. Free-typing recipes:a3 (and the deprecated recipes#a3) offers
#      "open this id" as recipes:A3 — id uppercased, "#" normalized to ":".
#   4. Typing [[A3 in the editor autocompletes via the qualified aliases;
#      confirm an alias containing ":" doesn't confuse the suggester
#      (plan §12 risk 2 — bare-id alias stays first as the fallback).


def make_workspace(dest: Path) -> Path:
    """A workspace root binding one real notebook, table written the way
    `flip ws` serializes it (sorted handles, json-quoted paths)."""
    create_notebook(dest / "recipes", "recipes", "scout")
    (dest / ".flip").mkdir(parents=True)
    (dest / ".flip" / "workspace.toml").write_text(
        '[workspace]\nversion = "0.1"\n\n[notebooks]\nrecipes = "recipes"\n',
        encoding="utf-8",
    )
    return dest


def test_workspace_root_is_accepted(tmp_path):
    root = make_workspace(tmp_path / "shared")
    actions = prepare_vault(root)
    assert len(actions) == 3  # app.json, plugin files, community-plugins.json
    assert (root / ".obsidian" / "plugins" / PLUGIN_ID / "main.js").exists()
    assert read_json(root / ".obsidian" / "community-plugins.json") == [PLUGIN_ID]


def test_workspace_root_second_run_changes_nothing(tmp_path):
    root = make_workspace(tmp_path / "shared")
    assert prepare_vault(root)  # first run acts
    assert prepare_vault(root) == []  # second run: no actions


def test_packaged_plugin_carries_workspace_support(tmp_path):
    # The markers the manual checklist above exercises must ship in the
    # packaged bundle — catches drift between main.js and this release.
    root = make_workspace(tmp_path / "shared")
    prepare_vault(root)
    plugin_dir = root / ".obsidian" / "plugins" / PLUGIN_ID
    js = (plugin_dir / "main.js").read_text(encoding="utf-8")
    assert '".flip/workspace.toml"' in js  # rootKind + readWorkspaceTable
    assert '"--workspace"' in js  # refresh() runs workspace doctor
    assert 'handle + ":" + String(row.id)' in js  # modal qualifies ids
    manifest = read_json(plugin_dir / "manifest.json")
    assert manifest["version"] == "0.9.0"
    assert "workspaces" in manifest["description"]


# ---------------------------------------------------------------- CLI / export


def test_cli_obsidian_happy_path(tmp_path, monkeypatch):
    root = make_notebook(tmp_path / "demo")
    monkeypatch.chdir(root)
    result = CliRunner().invoke(main, ["obsidian"])
    assert result.exit_code == 0, result.output
    assert "app.json" in result.output
    assert PLUGIN_ID in result.output
    assert "Restricted mode" in result.output
    assert "gitignore" in result.output
    assert (root / ".obsidian" / "plugins" / PLUGIN_ID / "manifest.json").exists()
    # second run says so
    again = CliRunner().invoke(main, ["obsidian"])
    assert again.exit_code == 0, again.output
    assert "nothing to change" in again.output


def test_cli_obsidian_outside_any_root_fails_actionably(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["obsidian"])
    assert result.exit_code == 1
    assert "not inside a flip notebook or beat" in result.output


def test_okf_export_of_prepared_vault_ships_no_obsidian(tmp_path):
    root = make_notebook(tmp_path / "demo", visibility="public")
    prepare_vault(root)
    dest = export_okf(root, tmp_path / "out")
    assert (dest / "index.md").exists()
    assert not (dest / ".obsidian").exists()
    assert not list(dest.rglob(".obsidian"))
