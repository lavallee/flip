"""Tests for flip.pages — parse/write inverses, YAML normalization, list
coercion, id resolution across the scanned dirs, and id reservation."""

from __future__ import annotations

from pathlib import Path

from flip import pages
from flip.pages import (
    all_ids,
    allocate_id,
    as_list,
    find_by_id,
    parse,
    reserve_id,
    reserved_ids,
    write_page,
)

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: t
kind: scout
status: active
created: 2020-01-01
updated: 2020-01-01
---
# t
"""


def make_root(tmp_path: Path) -> Path:
    (tmp_path / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    return tmp_path


# --- parse / write_page are inverses ------------------------------------------


def test_parse_strips_write_page_separator(tmp_path):
    path = write_page(tmp_path / "p.md", {"type": "Note"}, "body line\n")
    fm, body = parse(path.read_text(encoding="utf-8"))
    assert fm == {"type": "Note"}
    assert body == "body line\n"  # no leading separator newline


def test_parse_write_round_trip_is_byte_stable(tmp_path):
    path = write_page(tmp_path / "p.md", {"type": "Note", "id": "C1"}, "text\n")
    first = path.read_text(encoding="utf-8")
    fm, body = parse(first)
    write_page(path, fm, body)
    assert path.read_text(encoding="utf-8") == first


def test_parse_keeps_deliberate_extra_blank_lines(tmp_path):
    # a human's extra blank line between frontmatter and body survives the
    # round trip: only write_page's own one-line separator is stripped
    raw = "---\ntype: Note\n---\n\n\nbody\n"
    fm, body = parse(raw)
    assert body == "\nbody\n"
    path = tmp_path / "p.md"
    write_page(path, fm, body)
    assert path.read_text(encoding="utf-8") == raw


def test_parse_page_without_separator_line(tmp_path):
    fm, body = parse("---\ntype: Note\n---\nbody\n")
    assert fm == {"type": "Note"}
    assert body == "body\n"


# --- YAML normalization ---------------------------------------------------------


def test_tz_aware_datetime_converted_to_utc():
    # +02:00 is an instant, not a wall clock: relabeling it Z would shift it
    fm, _body = parse("---\nretrieved: 2026-07-09T14:30:00+02:00\n---\nx\n")
    assert fm["retrieved"] == "2026-07-09T12:30:00Z"


def test_naive_datetime_and_date_stay_iso():
    fm, _body = parse("---\nwhen: 2026-07-09T14:30:00\nday: 2026-07-09\n---\nx\n")
    assert fm["when"] == "2026-07-09T14:30:00"
    assert fm["day"] == "2026-07-09"


def test_tz_aware_datetime_survives_grade_style_round_trip(tmp_path):
    # nested values normalize too, and a rewrite keeps the UTC instant
    path = tmp_path / "p.md"
    path.write_text(
        "---\ntype: Source\nmeta:\n  seen: 2026-01-01T00:30:00+05:30\n---\n\nx\n",
        encoding="utf-8",
    )
    page = pages.read_page(path)
    assert page.fm["meta"]["seen"] == "2025-12-31T19:00:00Z"
    write_page(path, page.fm, page.body)
    assert pages.read_page(path).fm["meta"]["seen"] == "2025-12-31T19:00:00Z"


# --- as_list ---------------------------------------------------------------------


def test_as_list_coercions():
    assert as_list(None) == []
    assert as_list("A3") == ["A3"]  # scalar: one item, never char-split
    assert as_list(["A3", "A4"]) == ["A3", "A4"]
    assert as_list(7) == [7]
    original = ["A3"]
    copy = as_list(original)
    copy.append("A4")
    assert original == ["A3"]  # a copy, not the caller's list


# --- id resolution across SCAN_DIRS ------------------------------------------------


def test_find_by_id_resolves_h_ids_in_analysis(tmp_path):
    root = make_root(tmp_path)
    write_page(
        root / "analysis" / "hypotheses.md",
        {"type": "Hypothesis", "id": "H1", "aliases": ["H1"]},
        "# H1\n",
    )
    page = find_by_id(root, "H1")
    assert page is not None
    assert page.path == root / "analysis" / "hypotheses.md"
    assert "H1" in all_ids(root)
    assert pages.PREFIX_DIR["H"] == "analysis"


def test_find_by_id_routes_th_to_threads_and_t_to_references(tmp_path):
    # TH# (beat threads, SPEC §14) and T# (talk sources) must never shadow
    # each other: find_by_id strips trailing digits, so TH3 → "TH", T3 → "T"
    root = make_root(tmp_path)
    write_page(
        root / "threads" / "bus.md",
        {"type": "Thread", "id": "TH3", "aliases": ["TH3"]},
        "thread\n",
    )
    write_page(
        root / "references" / "talk.md",
        {"type": "Source", "id": "T3", "aliases": ["T3"]},
        "talk\n",
    )
    assert pages.PREFIX_DIR["TH"] == "threads"
    assert pages.PREFIX_DIR["T"] == "references"
    assert find_by_id(root, "TH3").path == root / "threads" / "bus.md"
    assert find_by_id(root, "T3").path == root / "references" / "talk.md"
    assert {"TH3", "T3"} <= set(all_ids(root))


def test_allocate_id_multi_char_prefix_ignores_single_char_ids(tmp_path):
    # a T7 talk source must not advance the TH counter, and vice versa
    root = make_root(tmp_path)
    write_page(
        root / "references" / "talk.md",
        {"type": "Source", "id": "T7", "aliases": ["T7"]},
        "talk\n",
    )
    assert allocate_id(root, "TH") == "TH1"
    assert allocate_id(root, "T") == "T8"


# --- id reservation (.flip/ids) -----------------------------------------------------


def test_allocate_id_reserves_and_survives_page_deletion(tmp_path):
    root = make_root(tmp_path)
    assert allocate_id(root, "C") == "C1"
    # no page was ever written for C1; the reservation alone blocks reuse
    assert reserved_ids(root) == ["C1"]
    assert allocate_id(root, "C") == "C2"
    assert (root / ".flip" / "ids").read_text(encoding="utf-8") == "C1\nC2\n"


def test_all_ids_unions_pages_provenance_and_reservations(tmp_path):
    from flip.util import append_jsonl

    root = make_root(tmp_path)
    write_page(
        root / "claims" / "one.md",
        {"type": "Claim", "id": "C1", "aliases": ["C1"]},
        "one\n",
    )
    append_jsonl(
        root / "sources" / "_provenance.jsonl",
        {"ts": "2026-07-09T10:00:00Z", "source_id": "A1",
         "local_path": "sources/raw/A1.html", "sha256": "ab" * 32,
         "tool": "test", "actor": "human:test"},
    )
    reserve_id(root, "Q7")
    assert {"C1", "A1", "Q7"} <= set(all_ids(root))
