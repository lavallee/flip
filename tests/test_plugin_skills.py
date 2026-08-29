"""The plugin manifests and shared skills tree are release-critical surfaces."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "src" / "flip" / "skills"
PLUGIN = ROOT / "skills"


def _tree(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_plugin_skills_match_canonical():
    canonical, plugin = _tree(CANONICAL), _tree(PLUGIN)
    assert plugin.keys() == canonical.keys(), (
        "plugin skills/ and src/flip/skills differ in file set; "
        "re-sync with: rm -rf skills && cp -r src/flip/skills skills"
    )
    stale = [name for name, body in canonical.items() if plugin[name] != body]
    assert not stale, (
        f"plugin skills/ out of date for {stale}; "
        "re-sync with: rm -rf skills && cp -r src/flip/skills skills"
    )


def test_plugin_manifests_match_package_and_point_at_shared_skills():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())

    assert claude["name"] == codex["name"] == "flip"
    assert claude["version"] == codex["version"] == version
    assert codex["skills"] == "./skills/"
    assert (ROOT / codex["skills"]).is_dir()
    assert codex["interface"]["defaultPrompt"]
    assert all("smallest useful pilot" not in prompt for prompt in codex["interface"]["defaultPrompt"])


def test_claude_hook_manifest_resolves_commands():
    payload = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    commands = []
    for groups in payload["hooks"].values():
        for group in groups:
            commands.extend(hook["command"] for hook in group["hooks"])
    assert commands
    assert all("${CLAUDE_PLUGIN_ROOT}/hooks/custody_hook.py" in command for command in commands)
    assert (ROOT / "hooks" / "custody_hook.py").is_file()
