"""Plugin state boundaries and typed subprocess hooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flip import doctor, extensions, loop, scaffold
from flip.manifest import load_manifest


def _plugin(tmp_path: Path, *, hook: str = "frontier.provide@1",
            body: str | None = None) -> Path:
    root = tmp_path / "provider"
    root.mkdir()
    (root / "flip-plugin.toml").write_text(
        f'''[plugin]
id = "example/local-worklist"
version = "0.1.0"
summary = "Fixture provider"
capabilities = ["execute:filter", "read:notebook"]

[[filters]]
id = "worklist"
hook = "{hook}"
protocol = "flip-filter/1"
command = ["./provider.py"]
needs = ["execute:filter", "read:notebook"]
''', encoding="utf-8",
    )
    script = body or '''#!/usr/bin/env python3
import json, sys
request = json.load(sys.stdin)
print(json.dumps({"protocol": "flip-filter/1", "items": [{
  "lane": "local-worklist", "id": "WL1", "text": "read the filing",
  "why": "checked-in worklist row"
}]}))
'''
    command = root / "provider.py"
    command.write_text(script, encoding="utf-8")
    command.chmod(0o755)
    return root


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    return scaffold.create_notebook(tmp_path / "notebook", "notebook", "ledger")


def test_link_enable_and_frontier_provider_keep_states_separate(root: Path, tmp_path: Path):
    plugin = extensions.link_plugin(_plugin(tmp_path))
    assert plugin.pin == "example/local-worklist@0.1.0"
    assert load_manifest(root).plugins == []  # linked is not enabled

    extensions.enable_plugin(root, plugin.id)
    assert load_manifest(root).plugins == [plugin.pin]
    assert (root / ".flip/extensions.lock").is_file()

    data = loop.next_view(root, scope="notebook", explain=True)
    assert [row["id"] for row in data["items"]] == ["WL1"]
    assert data["items"][0]["extension"].endswith("/worklist")
    assert any(step["result"] == "provided" for step in data["trace"])

    state = extensions.plugin_data(plugin, root)
    assert state["materialized"] and state["valid"] and state["enabled"]
    assert not state["cataloged"] and not state["exercised"]


def test_provider_failure_is_visible_and_does_not_sink_core_frontier(
    root: Path, tmp_path: Path
):
    script = "#!/usr/bin/env python3\nraise SystemExit(7)\n"
    plugin = extensions.link_plugin(_plugin(tmp_path, body=script))
    extensions.enable_plugin(root, plugin.id)
    data = loop.next_view(root, scope="notebook", explain=True)
    assert data["items"] == []
    assert any(step["result"] == "error-skipped" for step in data["trace"])


def test_check_provider_reports_through_stable_doctor_codes(root: Path, tmp_path: Path):
    script = '''#!/usr/bin/env python3
import json, sys
json.load(sys.stdin)
print(json.dumps({"protocol": "flip-filter/1", "findings": [{
  "level": "WARN", "code": "missing-disclosure",
  "message": "draft needs disclosure.md", "path": "drafts/article.md"
}]}))
'''
    plugin = extensions.link_plugin(_plugin(tmp_path, hook="check.provide@1", body=script))
    extensions.enable_plugin(root, plugin.id)
    findings = doctor.run_doctor(root)
    extension_rows = [finding for finding in findings if finding.code == "extension-check"]
    assert len(extension_rows) == 1
    assert "missing-disclosure" in extension_rows[0].message


def test_filter_test_exercises_without_enabling(root: Path, tmp_path: Path):
    plugin = extensions.link_plugin(_plugin(tmp_path))
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"scope": {"root": str(root)}}), encoding="utf-8")
    handler = extensions.find_handler(f"{plugin.id}/worklist")
    result = extensions.test_handler(handler, fixture)
    assert result["items"][0]["id"] == "WL1"
    assert load_manifest(root).plugins == []


def test_lock_content_drift_is_a_doctor_error(root: Path, tmp_path: Path):
    plugin_root = _plugin(tmp_path)
    plugin = extensions.link_plugin(plugin_root)
    extensions.enable_plugin(root, plugin.id)
    with (plugin_root / "provider.py").open("a", encoding="utf-8") as stream:
        stream.write("\n# reviewed change not yet re-enabled\n")
    findings = doctor.run_doctor(root)
    assert any(
        finding.code == "bad-plugin" and "content drift" in finding.message
        for finding in findings
    )


def test_incompatible_plugin_refuses_link(root: Path, tmp_path: Path):
    plugin_root = _plugin(tmp_path)
    manifest_path = plugin_root / "flip-plugin.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            'summary = "Fixture provider"',
            'summary = "Fixture provider"\nrequires_flip = ">=99.0"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="requires Flip >=99.0"):
        extensions.link_plugin(plugin_root)


def test_registry_lists_a_link_that_later_goes_missing(root: Path, tmp_path: Path):
    plugin_root = _plugin(tmp_path)
    plugin = extensions.link_plugin(plugin_root)
    (plugin_root / "flip-plugin.toml").rename(plugin_root / "moved.toml")
    rows = extensions.registry_rows(root)
    assert rows[0]["id"] == plugin.id
    assert rows[0]["materialized"] and not rows[0]["valid"]
    assert extensions.unlink_plugin(plugin.id)
    assert extensions.registry_rows(root) == []
