"""Tests for flip.manifest — TOML round-trips, escaping, extras, slug rules."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from flip.manifest import (
    Manifest,
    _toml_value,
    load_manifest,
    render_manifest,
    save_manifest,
    touch_updated,
)
from flip.util import today


def write_manifest(root: Path, text: str) -> Path:
    (root / "notebook.toml").write_text(text, encoding="utf-8")
    return root


# --- extras preservation ------------------------------------------------------


def test_unknown_keys_and_tables_survive_touch_updated(tmp_path):
    write_manifest(
        tmp_path,
        'slug = "t"\n'
        'kind = "scout"\n'
        'status = "active"\n'
        'created = "2020-01-01"\n'
        'updated = "2020-01-01"\n'
        'description = "hand-added prose the tooling must not eat"\n'
        "tags = [\"schools\", \"nj\"]\n"
        "\n"
        "[beat]\n"
        'mission = "school funding in this county"\n'
        "cadence_days = 14\n"
        "sub = { nested = true, level = 2 }\n",
    )
    touch_updated(tmp_path)  # first mutating command
    data = tomllib.loads((tmp_path / "notebook.toml").read_text(encoding="utf-8"))
    assert data["updated"] == today()  # the mutation happened
    assert data["description"] == "hand-added prose the tooling must not eat"
    assert data["tags"] == ["schools", "nj"]
    assert data["beat"]["mission"] == "school funding in this county"
    assert data["beat"]["cadence_days"] == 14
    assert data["beat"]["sub"] == {"nested": True, "level": 2}
    # and a second load sees them as extras, still intact
    m = load_manifest(tmp_path)
    assert m.extras["description"] == "hand-added prose the tooling must not eat"
    assert m.extras["beat"]["cadence_days"] == 14


def test_extras_survive_save_load_round_trip(tmp_path):
    m = Manifest(
        slug="t",
        kind="scout",
        created="2020-01-01",
        updated="2020-01-01",
        extras={"description": "why", "beat": {"mission": "x"}},
    )
    save_manifest(tmp_path, m)
    again = load_manifest(tmp_path)
    assert again.extras == {"description": "why", "beat": {"mission": "x"}}


# --- escaping -----------------------------------------------------------------


def test_newline_title_round_trips(tmp_path):
    title = 'line one\nline "two"\twith\ttabs\r'
    m = Manifest(slug="t", title=title, kind="scout")
    save_manifest(tmp_path, m)
    # the file must parse (previously a raw newline broke the TOML) ...
    assert load_manifest(tmp_path).title == title


def test_control_chars_and_backslashes_escape(tmp_path):
    weird = "bell\x07 back\\slash \x1b[0m del\x7f"
    m = Manifest(slug="t", title=weird, kind="scout", tools={"web": weird})
    save_manifest(tmp_path, m)
    again = load_manifest(tmp_path)
    assert again.title == weird
    assert again.tools["web"] == weird


def test_toml_value_types():
    assert _toml_value(True) == "true"
    assert _toml_value(False) == "false"
    assert _toml_value(3) == "3"
    assert _toml_value(["a", 1]) == '["a", 1]'
    assert _toml_value("a\nb") == '"a\\nb"'
    assert _toml_value({"k": "v", "n": 1}) == '{ k = "v", n = 1 }'
    # nested dicts render as inline tables recursively
    assert _toml_value({"outer": {"inner": True}}) == "{ outer = { inner = true } }"


def test_render_manifest_routes_every_value_through_escaping():
    m = Manifest(slug="t", kind='we"ird', status="active", host="a\nb")
    text = render_manifest(m)
    parsed = tomllib.loads(text)  # must be valid TOML whatever the values
    assert parsed["kind"] == 'we"ird'
    assert parsed["host"] == "a\nb"


# --- slug validation ----------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["", "Has Spaces", 'quo"te', "new\nline", "-leading-dash", ".leading-dot", "UPPER"],
)
def test_save_manifest_rejects_bad_slug(tmp_path, bad):
    with pytest.raises(SystemExit, match="invalid slug"):
        save_manifest(tmp_path, Manifest(slug=bad))
    assert not (tmp_path / "notebook.toml").exists()


@pytest.mark.parametrize("good", ["nj-schools", "a", "x2", "a.b_c-d", "2026-review"])
def test_save_manifest_accepts_good_slug(tmp_path, good):
    save_manifest(tmp_path, Manifest(slug=good))
    assert load_manifest(tmp_path).slug == good
