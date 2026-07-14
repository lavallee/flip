"""Tests for flip.integrations: the shared plugin layer — config resolution
(string / inline-table / named-variant forms), the command runner, the return
envelope harvest, and per-role actionable errors."""

import stat

import pytest

from flip import integrations


def write_config(tmp_path, monkeypatch, toml_text):
    home = tmp_path / "fliphome"
    home.mkdir(exist_ok=True)
    (home / "config.toml").write_text(toml_text, encoding="utf-8")
    monkeypatch.setenv("FLIP_HOME", str(home))
    return home


def make_tool(tmp_path, body):
    script = tmp_path / "faketool"
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


# --- resolve: config forms --------------------------------------------------


def test_resolve_bare_string(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, '[fetchers]\nweb = "myfetch {url} {dest}"\n')
    r = integrations.resolve("fetchers", "web")
    assert r.template == "myfetch {url} {dest}"
    assert r.name is None and r.needs == []


def test_resolve_inline_table_cmd_and_needs(tmp_path, monkeypatch):
    write_config(
        tmp_path, monkeypatch,
        '[fetchers]\nsocial = { cmd = "x-fetch {url}", needs = ["cookies"] }\n',
    )
    r = integrations.resolve("fetchers", "social")
    assert r.template == "x-fetch {url}"
    assert r.needs == ["cookies"]


def test_resolve_variant_map_default_and_via(tmp_path, monkeypatch):
    write_config(
        tmp_path, monkeypatch,
        '[fetchers.web]\n'
        'default = "plain {url} {dest}"\n'
        'browser = { cmd = "browser {url} {dest}" }\n',
    )
    assert integrations.resolve("fetchers", "web").template == "plain {url} {dest}"
    assert integrations.resolve("fetchers", "web").name == "default"
    picked = integrations.resolve("fetchers", "web", via="browser")
    assert picked.template == "browser {url} {dest}"
    assert picked.name == "browser"


def test_resolve_unknown_via_lists_variants(tmp_path, monkeypatch):
    write_config(
        tmp_path, monkeypatch,
        '[fetchers.web]\ndefault = "a {url}"\nbrowser = "b {url}"\n',
    )
    with pytest.raises(SystemExit) as ei:
        integrations.resolve("fetchers", "web", via="nope")
    assert "default" in str(ei.value) and "browser" in str(ei.value)


def test_resolve_via_on_single_command_errors(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, '[fetchers]\nweb = "plain {url}"\n')
    with pytest.raises(SystemExit, match="single command"):
        integrations.resolve("fetchers", "web", via="browser")


def test_resolve_missing_config_gives_role_guidance(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "empty"))
    with pytest.raises(SystemExit) as ei:
        integrations.resolve("research", "find")
    msg = str(ei.value)
    assert "[research]" in msg
    assert 'find = "your-research-tool {query}"' in msg


def test_resolve_missing_key_gives_role_guidance(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, "[knowledge]\n")
    with pytest.raises(SystemExit) as ei:
        integrations.resolve("knowledge", "recall")
    msg = str(ei.value)
    assert "[knowledge]" in msg
    assert 'recall = "your-knowledge-tool {query}"' in msg


def test_invalid_toml_names_the_file(tmp_path, monkeypatch):
    home = write_config(tmp_path, monkeypatch, "[fetchers]\nweb = ")
    with pytest.raises(SystemExit) as ei:
        integrations.resolve("fetchers", "web")
    assert str(home / "config.toml") in str(ei.value)
    assert "invalid TOML" in str(ei.value)


# --- tokenization -----------------------------------------------------------


def test_tokenize_template_posix_mode_handles_quotes():
    assert integrations._tokenize_template('fetch "{url}" --out {dest}') == [
        "fetch", "{url}", "--out", "{dest}",
    ]


def test_tokenize_template_windows_mode_keeps_backslash_paths(monkeypatch):
    template = r'C:\Tools\fetch.exe {url} --out {dest}'
    monkeypatch.setattr(integrations.os, "name", "posix")
    assert integrations._tokenize_template(template)[0] == "C:Toolsfetch.exe"
    monkeypatch.setattr(integrations.os, "name", "nt")
    assert integrations._tokenize_template(template)[0] == r"C:\Tools\fetch.exe"


def test_build_argv_substitutes_all_placeholders():
    argv = integrations._build_argv(
        "t {url} {id} {query} {dest}",
        {"url": "U", "id": "I", "query": "Q", "dest": "D"},
    )
    assert argv == ["t", "U", "I", "Q", "D"]


# --- envelope harvest -------------------------------------------------------


def test_harvest_envelope_from_stdout(tmp_path):
    stdout = b'{"flip": {"title": "T", "strategy": "s", "junk": 1}}'
    env = integrations._harvest_envelope([], stdout)
    assert env == {"title": "T", "strategy": "s"}  # only whitelisted keys


def test_harvest_envelope_prefers_flip_json_file(tmp_path):
    fj = tmp_path / "flip.json"
    fj.write_text('{"flip": {"title": "FromFile"}}', encoding="utf-8")
    env = integrations._harvest_envelope([fj], b'{"flip": {"title": "FromStdout"}}')
    assert env == {"title": "FromFile"}


def test_harvest_envelope_none_when_absent_or_malformed(tmp_path):
    assert integrations._harvest_envelope([], b'{"data": 1}') is None
    assert integrations._harvest_envelope([], b"not json") is None
    assert integrations._harvest_envelope([], b"") is None


# --- runners ----------------------------------------------------------------


def test_run_query_parses_json(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, "printf '[{\"url\": \"https://x.test\"}]'")
    write_config(tmp_path, monkeypatch, f'[research]\nfind = "{tool} {{query}}"\n')
    run = integrations.run_query(integrations.resolve("research", "find"), tmp_path, "anything")
    assert run.data == [{"url": "https://x.test"}]
    assert run.raw == '[{"url": "https://x.test"}]'


def test_run_query_non_json_leaves_data_none(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, 'printf "plain text answer"')
    write_config(tmp_path, monkeypatch, f'[research]\nask = "{tool} {{query}}"\n')
    run = integrations.run_query(integrations.resolve("research", "ask"), tmp_path, "q")
    assert run.data is None
    assert run.raw == "plain text answer"


def test_run_query_nonzero_exit_errors(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, 'echo "backend down" >&2\nexit 2\n')
    write_config(tmp_path, monkeypatch, f'[knowledge]\nrecall = "{tool} {{query}}"\n')
    with pytest.raises(SystemExit) as ei:
        integrations.run_query(integrations.resolve("knowledge", "recall"), tmp_path, "q")
    assert "exit 2" in str(ei.value) and "backend down" in str(ei.value)
