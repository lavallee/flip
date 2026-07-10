"""flip obsidian — prepare a notebook (or beat) to open cleanly as a vault.

Obsidian is the reference human client for flip (SPEC §12): frontmatter is
the Properties panel, `aliases` make [[A3]]-style id links resolve, and the
relative markdown links flip writes light up the graph view. Two things
vanilla Obsidian gets wrong out of the box, this module fixes:

- **Link authoring.** New Obsidian installs write wikilinks with shortest
  paths; flip writes relative markdown links (SPEC §9). Merge-writing
  `.obsidian/app.json` (`useMarkdownLinks: true`, `newLinkFormat:
  "relative"`) makes links a human drags into a page match the ones flip
  generates — every other key in an existing app.json survives.
- **The metadata flip adds.** The packaged companion plugin (doctor
  findings, the hot view, a status bar summary, open-by-id — all driven by
  `flip … --json`) installs into `.obsidian/plugins/flip-notebook/` and is
  enabled via `community-plugins.json`.

`.obsidian/` is editor-local state (SPEC §12): flip never reads it back,
dot-dirs stay out of every export/bag payload, and it belongs in the
notebook's gitignore. Everything here is merge-write and idempotent — a
second run changes nothing and says so.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .beat import is_beat_root
from .util import is_notebook_root

OBSIDIAN_DIR = ".obsidian"
PLUGIN_ID = "flip-notebook"
PLUGIN_FILES = ("manifest.json", "main.js", "styles.css")

# Vault link settings that make Obsidian author what flip authors (SPEC §9):
# relative markdown links, so agent-written and human-written edges match.
APP_SETTINGS = {"useMarkdownLinks": True, "newLinkFormat": "relative"}


def prepare_vault(root: Path, with_plugin: bool = True) -> list[str]:
    """Prepare `root` (a notebook or beat root) as an Obsidian vault.

    Merge-writes `.obsidian/app.json`, installs the packaged flip plugin,
    and enables it in `.obsidian/community-plugins.json`. Returns the list
    of actions taken — empty when the vault was already prepared.
    """
    root = Path(root)
    if not (is_notebook_root(root) or is_beat_root(root)):
        raise SystemExit(
            f"{root} is not a flip notebook or beat root (no index.md with flip/"
            "flip_beat frontmatter); run this at a root, or `flip new <slug>` / "
            "`flip beat new <slug>` to create one"
        )
    obsidian = root / OBSIDIAN_DIR
    actions: list[str] = []
    verb = _merge_app_json(obsidian / "app.json")
    if verb:
        actions.append(
            f"{verb} {OBSIDIAN_DIR}/app.json (useMarkdownLinks: true, newLinkFormat: relative)"
        )
    if with_plugin:
        written = _install_plugin(obsidian / "plugins" / PLUGIN_ID)
        if written:
            actions.append(
                f"installed {OBSIDIAN_DIR}/plugins/{PLUGIN_ID}/ ({', '.join(written)})"
            )
        if _enable_plugin(obsidian / "community-plugins.json"):
            actions.append(f"enabled {PLUGIN_ID} in {OBSIDIAN_DIR}/community-plugins.json")
    return actions


def _read_json(path: Path, expect: type):
    """Existing Obsidian config, or None when the file is absent. A file that
    is unreadable as the expected JSON shape is a user's real config we must
    not clobber — refuse with the filename rather than overwrite."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(
            f"{path} is not valid JSON ({e}); fix or remove it, then rerun `flip obsidian`"
        ) from None
    if not isinstance(data, expect):
        raise SystemExit(
            f"{path} is not a JSON {expect.__name__.replace('dict', 'object')} "
            "as Obsidian expects; fix or remove it, then rerun `flip obsidian`"
        )
    return data


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _merge_app_json(path: Path) -> str | None:
    """Set the link-authoring keys in app.json, preserving every other key.

    Returns "created"/"updated", or None when nothing needed to change.
    """
    existing = _read_json(path, dict)
    merged = dict(existing or {})
    merged.update(APP_SETTINGS)
    if existing == merged:
        return None
    _write_json(path, merged)
    return "created" if existing is None else "updated"


def _install_plugin(dest: Path) -> list[str]:
    """Copy the packaged plugin into `dest`; returns the filenames written
    (only the ones whose content differed — a clean reinstall writes nothing)."""
    package_dir = resources.files("flip") / "obsidian_plugin"
    written: list[str] = []
    for name in PLUGIN_FILES:
        content = (package_dir / name).read_bytes()
        target = dest / name
        if target.exists() and target.read_bytes() == content:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written.append(name)
    return written


def _enable_plugin(path: Path) -> bool:
    """Merge PLUGIN_ID into community-plugins.json (a JSON list of plugin
    ids); creates the file when absent. Returns True when the list changed."""
    enabled = _read_json(path, list)
    if enabled is not None and PLUGIN_ID in enabled:
        return False
    _write_json(path, (enabled or []) + [PLUGIN_ID])
    return True
