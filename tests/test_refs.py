"""Tests for the reference grammar and notebook uids (SPEC §9, §18):
util.parse_ref/format_ref and util.new_uid."""

from __future__ import annotations

import random

import pytest

from flip.util import UID_ALPHABET, UID_RE, format_ref, new_uid, parse_ref


# --- parse_ref ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("A3", (None, "A3", False)),
        ("TH12", (None, "TH12", False)),
        ("recipes:A3", ("recipes", "A3", False)),
        ("field-notes:C7", ("field-notes", "C7", False)),
        ("r2:Q1", ("r2", "Q1", False)),
        ("recipes#A3", ("recipes", "A3", True)),  # deprecated synonym, flagged
    ],
)
def test_parse_ref_accepts(ref, expected):
    assert parse_ref(ref) == expected


@pytest.mark.parametrize(
    "ref",
    [
        "",  # empty
        "a3",  # ids are uppercase
        "Recipes:A3",  # handles are lowercase
        "recipes/A3",  # '/' is a path, not a ref separator
        "recipes:a3",  # lowercase id
        "recipes:",  # missing id
        ":A3",  # missing handle
        "recipes:A",  # id needs a number
        "recipes::A3",  # double separator
        "2cool:A3",  # handles start with a letter
        "recipes:A3 ",  # trailing junk
    ],
)
def test_parse_ref_rejects_with_grammar_hint(ref):
    with pytest.raises(SystemExit, match="invalid reference"):
        parse_ref(ref)


def test_format_ref_round_trips():
    assert format_ref(None, "A3") == "A3"
    assert format_ref("recipes", "A3") == "recipes:A3"
    for ref in ("A3", "recipes:A3"):
        handle, entity_id, _ = parse_ref(ref)
        assert format_ref(handle, entity_id) == ref


# --- new_uid --------------------------------------------------------------------


def test_new_uid_shape_and_alphabet():
    uid = new_uid()
    assert UID_RE.match(uid)
    assert set(UID_ALPHABET).isdisjoint("aeiou")  # no vowels: no words, no confusion
    assert set(UID_ALPHABET).isdisjoint("il")  # Crockford: no ambiguous glyphs


def test_new_uid_deterministic_with_seeded_rng():
    a = new_uid(random.Random(0))
    b = new_uid(random.Random(0))
    assert a == b
    assert a != new_uid(random.Random(1))


def test_new_uid_unseeded_varies():
    assert new_uid() != new_uid()  # 30^8 space; collision here means a real bug
