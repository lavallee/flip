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


# --- starter config (flip config init) --------------------------------------


def test_starter_config_is_valid_toml_with_working_web_default():
    import tomllib

    data = tomllib.loads(integrations.STARTER_CONFIG)
    assert data["fetchers"]["web"] == "flip-fetch {url} {dest}"


def test_write_starter_config_creates_refuses_clobber_then_forces(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "h"))
    path, written = integrations.write_starter_config()
    assert written and path.exists()
    assert 'web = "flip-fetch {url} {dest}"' in path.read_text(encoding="utf-8")

    path.write_text("hand-edited", encoding="utf-8")
    same, written2 = integrations.write_starter_config()
    assert same == path and written2 is False
    assert path.read_text(encoding="utf-8") == "hand-edited"  # not clobbered

    _, written3 = integrations.write_starter_config(force=True)
    assert written3 is True
    assert "flip-fetch" in path.read_text(encoding="utf-8")


def test_fetchers_guidance_points_at_config_init(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "empty"))
    with pytest.raises(SystemExit) as ei:
        integrations.resolve("fetchers", "web")
    assert "flip config init" in str(ei.value)


def test_envelope_whitelist_carries_the_conduct_record():
    """`user_agent` and `attempts` must survive the envelope whitelist.

    Regression guard: both were emitted by flip-fetch and silently dropped
    here, because _harvest_envelope returns only ENVELOPE_KEYS. The capture row
    read `user_agent: None` while the fetcher had written the real string — a
    provenance record quietly losing the technique it used, which is the one
    thing SPEC §5.1 says it must never do.
    """
    from flip import integrations

    for key in ("user_agent", "attempts", "strategy"):
        assert key in integrations.ENVELOPE_KEYS


def test_harvest_keeps_user_agent_and_attempts(tmp_path):
    import json as _json

    from flip import integrations

    payload = {"flip": {"strategy": "http-get", "user_agent": "Mozilla/5.0 (test)",
                        "attempts": 3, "not_a_known_key": "dropped"}}
    envelope_file = tmp_path / "flip.json"
    envelope_file.write_text(_json.dumps(payload), encoding="utf-8")
    got = integrations._harvest_envelope([envelope_file], b"")
    assert got["user_agent"] == "Mozilla/5.0 (test)"
    assert got["attempts"] == 3
    assert "not_a_known_key" not in got  # the whitelist still whitelists


# --- the empty-handed capture: a finding, not a defect ----------------------


def test_clean_but_empty_capture_raises_empty_capture_not_a_plain_failure(
    tmp_path, monkeypatch
):
    """Exit 0 with nothing written is a report, not a malfunction.

    Two very different events used to arrive at the same error text: a command
    that could not run, and a command that ran perfectly and found the document
    gated. Only the first is anyone's fault, and only the second is where the
    capture ladder (SPEC §5.1) applies — so they are now different exceptions,
    with `EmptyCapture` carrying what a caller needs to say something useful.
    """
    tool = make_tool(tmp_path, "exit 0\n")
    write_config(tmp_path, monkeypatch, f'[fetchers]\nweb = "{tool} {{url}} {{dest}}"\n')
    resolved = integrations.resolve("fetchers", "web")
    with pytest.raises(integrations.EmptyCapture) as ei:
        integrations.run_capture(resolved, tmp_path, "A1", "https://example.com/x")

    exc = ei.value
    assert isinstance(exc, SystemExit)   # every existing caller is unaffected
    assert exc.key == "web"
    assert exc.tool == str(tool)
    assert exc.captures_stdout is False  # the template promised {dest}
    assert "ran clean (exit 0)" in str(exc)
    assert "brought nothing back" in str(exc)
    # the old text sent the reader to debug a config that was fine
    assert "make sure its command" not in str(exc)


def test_a_command_that_fails_is_still_an_ordinary_failure(tmp_path, monkeypatch):
    """The distinction only means something if the other side keeps its shape:
    a nonzero exit is not an EmptyCapture and must not offer the ladder."""
    tool = make_tool(tmp_path, 'echo "connection refused" >&2\nexit 7\n')
    write_config(tmp_path, monkeypatch, f'[fetchers]\nweb = "{tool} {{url}} {{dest}}"\n')
    resolved = integrations.resolve("fetchers", "web")
    with pytest.raises(SystemExit) as ei:
        integrations.run_capture(resolved, tmp_path, "A1", "https://example.com/x")
    assert not isinstance(ei.value, integrations.EmptyCapture)
    assert "exit 7" in str(ei.value)


# --- reading the operator's own lanes back (SPEC §16) -----------------------


def test_configured_lanes_reports_every_role_key_and_variant(tmp_path, monkeypatch):
    """flip may not know what fills a role, but it can read the config the
    operator wrote and say what is there — which is the only honest way to
    point an agent at tooling flip is forbidden to name."""
    write_config(
        tmp_path, monkeypatch,
        '[fetchers]\n'
        'paper = "your-fetcher {id} {dest}"\n'
        'social = { cmd = "x-fetch {url}", needs = ["cookies"] }\n'
        '[fetchers.web]\n'
        'default = "plain {url} {dest}"\n'
        'browser = "render {url} {dest}"\n'
        '[research]\n'
        'find = "your-research-tool {query}"\n',
    )
    lanes = integrations.configured_lanes()
    assert {(r["role"], r["key"], r["variant"]) for r in lanes} == {
        ("fetchers", "paper", None),
        ("fetchers", "social", None),
        ("fetchers", "web", "default"),
        ("fetchers", "web", "browser"),
        ("research", "find", None),
    }
    social = next(r for r in lanes if r["key"] == "social")
    assert social["command"] == "x-fetch {url}" and social["needs"] == ["cookies"]
    assert integrations.capture_lanes() == {
        "paper": [], "social": [], "web": ["default", "browser"],
    }


def test_configured_lanes_never_raises_on_a_broken_config(tmp_path, monkeypatch):
    """Every caller is either reporting what exists or building an error
    message. Neither may fail on top of the failure it is describing."""
    write_config(tmp_path, monkeypatch, "this is not = valid toml [[[\n")
    assert integrations.configured_lanes() == []
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "nothing-here"))
    assert integrations.configured_lanes() == []
    assert integrations.capture_lanes() == {}
