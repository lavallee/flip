"""Tests for flip.transcripts — conversations kept verbatim, cited by passage."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from flip import claims, doctor, pages, sessions, sources, transcripts, util

ROOT_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: t
kind: scout
status: active
created: 2020-01-01
updated: 2020-01-01
visibility: internal
renders_public: false
source_trail_public: false
citation_rule: public-terminus
---
# t
"""

# 40 numbered lines — line N reads "line N: …", so a range assertion can
# check it pinned the lines it claimed to.
CHAT = "\n".join(f"line {i}: some conversation text" for i in range(1, 41)) + "\n"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    (tmp_path / "index.md").write_text(ROOT_MD, encoding="utf-8")
    return tmp_path


@pytest.fixture
def chat(tmp_path: Path) -> Path:
    path = tmp_path / "_chat.md"
    path.write_text(CHAT, encoding="utf-8")
    return path


def _capture(root: Path, chat: Path, **kw) -> pages.Page:
    return transcripts.capture_transcript(root, chat, **kw)


# --- capture -----------------------------------------------------------------


def test_capture_lands_under_custody_with_a_t_id(root: Path, chat: Path):
    page = _capture(root, chat, title="Theory chat")
    assert page.fm["id"] == "T1"  # a conversation is a T, like a talk
    assert page.fm["medium"] == "conversation"
    assert page.fm["lines"] == 40
    assert page.fm["grade"] == "?"  # capture is custody, never judgment
    raw = root / page.fm["local"]
    assert raw.read_text(encoding="utf-8") == CHAT  # verbatim


def test_capture_records_human_in_loop_not_copy(root: Path, chat: Path):
    """The bytes came from a person saving a conversation they were in; `copy`
    would describe moving the file and understate where it came from."""
    _capture(root, chat)
    events = util.read_jsonl(root / "sources" / "_provenance.jsonl")
    assert [e["strategy"] for e in events] == ["human-in-loop"]
    assert events[0]["sha256"] == hashlib.sha256(CHAT.encode()).hexdigest()


def test_short_transcript_is_not_thin(root: Path, chat: Path):
    """The thin-capture heuristic looks for a consent wall standing in for a
    document — a handed-over file has no such failure mode, and every brief
    conversation was being flagged."""
    assert sources.capture_fidelity(
        {"strategy": "human-in-loop", "bytes": 300}
    ) == "faithful"


def test_capture_records_participants_and_model(root: Path, chat: Path):
    page = _capture(root, chat, participants=["human:marc", "agent:claude"],
                    model="claude-opus-5")
    assert page.fm["participants"] == ["human:marc", "agent:claude"]
    assert page.fm["model"] == "claude-opus-5"


def test_capture_refuses_missing_and_empty_files(root: Path, tmp_path: Path):
    with pytest.raises(SystemExit, match="no transcript file"):
        transcripts.capture_transcript(root, tmp_path / "nope.md")
    empty = tmp_path / "_empty.md"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="is empty"):
        transcripts.capture_transcript(root, empty)


# --- excerpts ----------------------------------------------------------------


def test_excerpt_pins_the_lines_it_says(root: Path, chat: Path):
    _capture(root, chat)
    record = transcripts.add_excerpt(root, "T1", "relevance-null", 8, 12)
    assert record["lines"] == [8, 12]
    page = pages.find_by_id(root, "T1")
    assert "> line 8: some conversation text" in page.body
    assert "> line 12: some conversation text" in page.body
    assert "line 7:" not in page.body and "line 13:" not in page.body


def test_excerpt_quote_is_derived_from_custody_not_authored(root: Path, chat: Path):
    """The stored sha is of the real passage — an excerpt flip vouches for is
    one it can recompute."""
    _capture(root, chat)
    record = transcripts.add_excerpt(root, "T1", "x", 3, 4)
    expected = "\n".join(CHAT.splitlines()[2:4])
    assert record["sha256"] == hashlib.sha256(expected.encode()).hexdigest()


def test_excerpt_anchors_the_label_as_a_heading(root: Path, chat: Path):
    """`references/<slug>.md#relevance-null` must resolve wherever headings
    slugify — that anchor is what a claim's `resource` points at."""
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "relevance-null", 1, 2)
    assert "### relevance-null\n" in pages.find_by_id(root, "T1").body


def test_excerpt_refuses_a_duplicate_label(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "x", 1, 2)
    with pytest.raises(SystemExit, match="already pins"):
        transcripts.add_excerpt(root, "T1", "x", 5, 6)


def test_excerpt_refuses_a_range_past_the_end(root: Path, chat: Path):
    """Clamping would store a shorter passage under a label claiming otherwise."""
    _capture(root, chat)
    with pytest.raises(SystemExit, match="runs past the end"):
        transcripts.add_excerpt(root, "T1", "x", 38, 60)
    with pytest.raises(SystemExit, match="starts past the end"):
        transcripts.add_excerpt(root, "T1", "y", 90, 95)


def test_excerpt_refuses_bad_labels_and_ranges(root: Path, chat: Path):
    _capture(root, chat)
    with pytest.raises(SystemExit, match="invalid excerpt label"):
        transcripts.add_excerpt(root, "T1", "Not A Slug", 1, 2)
    with pytest.raises(SystemExit, match="invalid line range"):
        transcripts.add_excerpt(root, "T1", "x", 5, 3)


def test_excerpt_refuses_a_non_transcript_source(root: Path, tmp_path: Path):
    doc = tmp_path / "_doc.md"
    doc.write_text("hello\n", encoding="utf-8")
    sources.add_source(root, str(doc), kind="file")
    with pytest.raises(SystemExit, match="not a transcript"):
        transcripts.add_excerpt(root, "F1", "x", 1, 1)


def test_prose_above_the_excerpts_section_round_trips(root: Path, chat: Path):
    _capture(root, chat, note="the conversation that built the position")
    transcripts.add_excerpt(root, "T1", "x", 1, 2)
    body = pages.find_by_id(root, "T1").body
    assert "the conversation that built the position" in body
    assert body.index("the conversation") < body.index("## Excerpts")


# --- citing a passage --------------------------------------------------------


def test_claim_cites_a_passage_and_deep_links_it(root: Path, chat: Path):
    _capture(root, chat, title="Theory chat")
    transcripts.add_excerpt(root, "T1", "relevance-null", 8, 12)
    page = claims.add_claim(root, "Intention-attribution returns null",
                            ["T1§relevance-null"])
    entry = page.fm["sources"][0]
    assert entry["id"] == "T1"  # the id stays a source id
    assert entry["excerpts"] == ["relevance-null"]
    assert entry["resource"].endswith("#relevance-null")
    assert claims.source_refs(page.fm) == ["T1§relevance-null"]
    assert claims.source_ids(page.fm) == ["T1"]


def test_two_passages_of_one_source_are_one_piece_of_evidence(root: Path, chat: Path):
    """Two citations, one source: only the second number may reach the bar."""
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    transcripts.add_excerpt(root, "T1", "b", 5, 6)
    page = claims.add_claim(root, "A claim", ["T1§a", "T1§b"])
    assert claims.source_ids(page.fm) == ["T1"]
    assert claims.source_refs(page.fm) == ["T1§a", "T1§b"]
    assert page.body.count("[^T1]") == 2  # one marker, one definition
    assert "— a, b" in page.body


def test_status_change_keeps_the_pins(root: Path, chat: Path):
    """Regenerating attribution from ids alone silently unpinned every excerpt."""
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    claims.add_claim(root, "A claim", ["T1§a"])
    page = claims.set_claim_status(root, "C1", "unconfirmed")
    assert claims.source_refs(page.fm) == ["T1§a"]


def test_linking_a_passage_after_the_fact(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    claims.add_claim(root, "A claim", [])
    page, added, _rerolled, _warnings = claims.add_claim_sources(root, "C1", ["T1§a"])
    assert added == ["T1§a"]
    assert claims.source_refs(page.fm) == ["T1§a"]


def test_linker_refuses_an_unpinned_label(root: Path, chat: Path):
    _capture(root, chat)
    claims.add_claim(root, "A claim", [])
    with pytest.raises(SystemExit, match="pins no excerpt 'ghost'"):
        claims.add_claim_sources(root, "C1", ["T1§ghost"])


def test_unlinking_a_passage_leaves_the_others(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    transcripts.add_excerpt(root, "T1", "b", 5, 6)
    claims.add_claim(root, "A claim", ["T1§a", "T1§b"])
    page = claims.remove_claim_source(root, "C1", "T1§a")
    assert claims.source_refs(page.fm) == ["T1§b"]


def test_unlinking_the_bare_id_drops_every_passage(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    transcripts.add_excerpt(root, "T1", "b", 5, 6)
    claims.add_claim(root, "A claim", ["T1§a", "T1§b"])
    page = claims.remove_claim_source(root, "C1", "T1")
    assert claims.source_refs(page.fm) == []


# --- unpinning ---------------------------------------------------------------


def test_unpin_refuses_while_a_claim_cites_it(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    claims.add_claim(root, "A claim", ["T1§a"])
    with pytest.raises(SystemExit, match="still cites T1§a"):
        transcripts.remove_excerpt(root, "T1", "a")


def test_unpin_drops_an_uncited_passage(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    transcripts.remove_excerpt(root, "T1", "a")
    assert transcripts.excerpts(root, "T1") == []
    assert "### a" not in pages.find_by_id(root, "T1").body


# --- session wiring ----------------------------------------------------------


def test_session_points_at_the_transcript(root: Path, chat: Path):
    path = sessions.start_session(root, "theory-chat")
    page = _capture(root, chat)
    sessions.attach_transcript(root, path, "T1", page.fm["local"], page.path.stem)
    session = pages.read_page(path)
    assert session.fm["transcript"] == {"id": "T1", "local": "sources/raw/T1.md"}
    assert "## Transcript" in session.body
    assert f"../references/{page.path.stem}.md" in session.body
    # the stub is filled, not duplicated
    assert session.body.count("## Transcript") == 1


# --- doctor ------------------------------------------------------------------


def _codes(root: Path) -> list[str]:
    return [f.code for f in doctor.run_doctor(root)]


def test_doctor_is_quiet_on_a_healthy_transcript(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    claims.add_claim(root, "A claim", ["T1§a"])
    assert not {"excerpt-drift", "dangling-excerpt", "unbacked-excerpt"} & set(_codes(root))


def test_doctor_flags_a_hand_edited_quote(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    page = pages.find_by_id(root, "T1")
    page.fm["excerpts"][0]["sha256"] = "0" * 64
    pages.write_page(page.path, page.fm, page.body)
    assert "excerpt-drift" in _codes(root)


def test_doctor_flags_a_citation_to_an_unpinned_passage(root: Path, chat: Path):
    _capture(root, chat)
    claims.add_claim(root, "A claim", ["T1§ghost"])  # dangling is legal, but counted
    assert "dangling-excerpt" in _codes(root)


def test_doctor_flags_a_pin_whose_custody_is_gone(root: Path, chat: Path):
    _capture(root, chat)
    transcripts.add_excerpt(root, "T1", "a", 1, 2)
    (root / "sources" / "raw" / "T1.md").unlink()
    assert "unbacked-excerpt" in _codes(root)


# --- ref grammar -------------------------------------------------------------


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("T1", ("T1", None)),
        ("T1§relevance-null", ("T1", "relevance-null")),
        ("muse:T1§x", ("muse:T1", "x")),
        ("A3", ("A3", None)),
    ],
)
def test_split_ref(ref: str, expected: tuple[str, str | None]):
    assert util.split_ref(ref) == expected


@pytest.mark.parametrize("ref", ["T1§", "T1§Bad-Label", "T1§-x", "§x", "T1#x"])
def test_split_ref_refuses_malformed(ref: str):
    """A dropped label would cite the whole transcript while reading as one
    exchange, so a malformed one is an error rather than a stripped suffix."""
    with pytest.raises(SystemExit, match="invalid reference"):
        util.split_ref(ref)


def test_format_excerpt_ref():
    assert util.format_excerpt_ref("T1", "x") == "T1§x"
    assert util.format_excerpt_ref("T1", None) == "T1"
