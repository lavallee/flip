"""The Claude Code and Codex plugins' shared skills/ tree is a synced copy of
the canonical skills packaged with the CLI (src/flip/skills). RELEASING.md says `cp -r`;
this test is what makes that instruction load-bearing — any drift between
the two trees fails the suite byte-for-byte in both directions."""

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
