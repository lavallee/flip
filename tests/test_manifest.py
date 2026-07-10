"""Tests for flip.manifest — root index.md frontmatter round-trips, extras,
escaping through YAML, body preservation, and slug rules (SPEC §4, §6.6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flip.manifest import (
    Manifest,
    load_manifest,
    manifest_frontmatter,
    save_manifest,
    touch_updated,
)
from flip.pages import parse
from flip.util import ROOT_FILE, today


def write_index(root: Path, fm_lines: str, body: str = "# t\n") -> Path:
    (root / ROOT_FILE).write_text(f"---\n{fm_lines}---\n\n{body}", encoding="utf-8")
    return root


def read_index(root: Path) -> tuple[dict, str]:
    return parse((root / ROOT_FILE).read_text(encoding="utf-8"))


# --- extras preservation ------------------------------------------------------


def test_unknown_keys_and_maps_survive_touch_updated(tmp_path):
    write_index(
        tmp_path,
        "flip: '0.4'\n"
        "slug: t\n"
        "kind: scout\n"
        "status: active\n"
        "created: '2020-01-01'\n"
        "updated: '2020-01-01'\n"
        "description: hand-added prose the tooling must not eat\n"
        "tags: [schools, nj]\n"
        "beat:\n"
        "  mission: school funding in this county\n"
        "  cadence_days: 14\n"
        "  sub: {nested: true, level: 2}\n",
    )
    touch_updated(tmp_path)  # first mutating command
    fm, _body = read_index(tmp_path)
    assert fm["updated"] == today()  # the mutation happened
    assert fm["description"] == "hand-added prose the tooling must not eat"
    assert fm["tags"] == ["schools", "nj"]
    assert fm["beat"]["mission"] == "school funding in this county"
    assert fm["beat"]["cadence_days"] == 14
    assert fm["beat"]["sub"] == {"nested": True, "level": 2}
    # and a second load sees them as extras, still intact
    m = load_manifest(tmp_path)
    assert m.extras["description"] == "hand-added prose the tooling must not eat"
    assert m.extras["beat"]["cadence_days"] == 14


def test_known_keys_with_foreign_types_survive_touch_updated(tmp_path):
    # a hand edit can legally leave a known key with a foreign-typed value
    # (tools as a string, links as a list, relations as a map): the typed
    # field keeps its default, but the value must ride along in extras and
    # re-emit verbatim — never be silently deleted on the next mutation
    write_index(
        tmp_path,
        "flip: '0.4'\n"
        "slug: t\n"
        "kind: scout\n"
        "status: active\n"
        "created: '2020-01-01'\n"
        "updated: '2020-01-01'\n"
        "tools: single-file 1.22\n"
        "links: [corpus://nj-schools]\n"
        "relations: {parent: beat-1}\n"
        "consumers: not-a-list\n",
    )
    m = load_manifest(tmp_path)
    assert m.tools == {} and m.links == {}  # typed fields keep their defaults
    assert m.extras["tools"] == "single-file 1.22"
    assert m.extras["links"] == ["corpus://nj-schools"]
    assert m.extras["relations"] == {"parent": "beat-1"}
    assert m.extras["consumers"] == "not-a-list"

    touch_updated(tmp_path)  # the mutation that used to delete them

    fm, _body = read_index(tmp_path)
    assert fm["updated"] == today()
    assert fm["tools"] == "single-file 1.22"
    assert fm["links"] == ["corpus://nj-schools"]
    assert fm["relations"] == {"parent": "beat-1"}
    assert fm["consumers"] == "not-a-list"
    # and the round-trip is stable: a second load classifies them the same way
    again = load_manifest(tmp_path)
    assert again.extras["tools"] == "single-file 1.22"


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


def test_touch_updated_is_idempotent_within_a_day(tmp_path):
    save_manifest(tmp_path, Manifest(slug="t"))
    touch_updated(tmp_path)
    first = (tmp_path / ROOT_FILE).read_bytes()
    touch_updated(tmp_path)
    assert (tmp_path / ROOT_FILE).read_bytes() == first  # byte-stable, no churn


# --- escaping (YAML now, same intent as the old TOML tests) --------------------


def test_newline_title_round_trips(tmp_path):
    title = 'line one\nline "two"\twith\ttabs'
    m = Manifest(slug="t", title=title, kind="scout")
    save_manifest(tmp_path, m)
    # the file must parse whatever the values (previously raw newlines broke TOML)
    assert load_manifest(tmp_path).title == title


def test_control_chars_and_backslashes_escape(tmp_path):
    weird = "bell\x07 back\\slash \x1b[0m del\x7f"
    m = Manifest(slug="t", title=weird, kind="scout", tools={"web": weird})
    save_manifest(tmp_path, m)
    again = load_manifest(tmp_path)
    assert again.title == weird
    assert again.tools["web"] == weird


def test_weird_values_route_through_yaml_everywhere(tmp_path):
    m = Manifest(slug="t", kind='we"ird', status="active", host="a\nb")
    save_manifest(tmp_path, m)
    fm, _body = read_index(tmp_path)  # must parse whatever the values
    assert fm["kind"] == 'we"ird'
    assert fm["host"] == "a\nb"


# --- frontmatter shape / body ownership ----------------------------------------


def test_manifest_frontmatter_declares_okf_and_flip_versions():
    fm = manifest_frontmatter(Manifest(slug="t"))
    keys = list(fm)
    assert keys[:3] == ["okf_version", "flip", "slug"]  # canonical order, OKF-first
    assert fm["okf_version"] == "0.1"
    assert fm["flip"] == "0.4"


def test_save_manifest_preserves_existing_body(tmp_path):
    save_manifest(tmp_path, Manifest(slug="t", title="T"))
    _fm, body = read_index(tmp_path)
    assert body.lstrip("\n") == "# T\n"  # a fresh notebook gets a minimal heading
    listing = "# T\n\n* [References](references/) - 1 captured source\n"
    save_manifest(tmp_path, load_manifest(tmp_path), body=listing)
    touch_updated(tmp_path)  # body untouched by frontmatter-only rewrites
    _fm, body = read_index(tmp_path)
    assert body.lstrip("\n") == listing


def test_policy_property_shape():
    m = Manifest(slug="t", visibility="public", renders_public=True)
    assert m.policy == {
        "visibility": "public",
        "renders_public": True,
        "source_trail_public": False,
        "citation_rule": "public-terminus",
    }
    assert m.policy_get("visibility") == "public"


# --- unhappy paths --------------------------------------------------------------


def test_load_manifest_without_index_is_actionable(tmp_path):
    with pytest.raises(SystemExit, match="not a flip notebook root"):
        load_manifest(tmp_path)


def test_load_manifest_without_slug_is_actionable(tmp_path):
    write_index(tmp_path, "flip: '0.4'\ntitle: no slug here\n")
    with pytest.raises(SystemExit, match="missing required key 'slug'"):
        load_manifest(tmp_path)


def test_save_manifest_rejects_bad_status_and_visibility(tmp_path):
    with pytest.raises(SystemExit, match="invalid status"):
        save_manifest(tmp_path, Manifest(slug="t", status="sideways"))
    with pytest.raises(SystemExit, match="invalid visibility"):
        save_manifest(tmp_path, Manifest(slug="t", visibility="sideways"))
    assert not (tmp_path / ROOT_FILE).exists()


# --- slug validation ----------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["", "Has Spaces", 'quo"te', "new\nline", "-leading-dash", ".leading-dot", "UPPER"],
)
def test_save_manifest_rejects_bad_slug(tmp_path, bad):
    with pytest.raises(SystemExit, match="invalid slug"):
        save_manifest(tmp_path, Manifest(slug=bad))
    assert not (tmp_path / ROOT_FILE).exists()


@pytest.mark.parametrize("good", ["nj-schools", "a", "x2", "a.b_c-d", "2026-review"])
def test_save_manifest_accepts_good_slug(tmp_path, good):
    save_manifest(tmp_path, Manifest(slug=good))
    assert load_manifest(tmp_path).slug == good
