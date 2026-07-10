"""Tests for flip.claims — claim entity pages and the verification bar."""

from __future__ import annotations

from pathlib import Path

import pytest

from flip import claims, pages, util
from flip.manifest import load_manifest

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

# id, slug, title, grade, independence — the judgment matrix the bar tests need.
SOURCE_ROWS = [
    ("A1", "orig-b", "orig B", "B", "original"),
    ("A2", "repub-a", "repub A", "A", "republisher"),
    ("A3", "orig-c", "orig C", "C", "original"),
    # captured but never judged: capture-time defaults (original/fresh) are
    # inert while grade is "?" — this page must corroborate nothing (SPEC §5.4)
    ("A4", "unjudged", "unjudged", "?", "original"),
]


def source_fm(sid: str, title: str, grade: str, independence: str) -> dict:
    return {
        "type": "Source", "id": sid, "aliases": [sid], "title": title,
        "local": f"sources/raw/{sid}.html", "grade": grade,
        "independence": independence, "freshness": "fresh", "status": "captured",
    }


SOURCE_FMS = [source_fm(sid, title, grade, ind) for sid, _, title, grade, ind in SOURCE_ROWS]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    (tmp_path / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    return tmp_path.resolve()


@pytest.fixture
def sourced(root: Path) -> Path:
    for sid, slug, title, grade, ind in SOURCE_ROWS:
        pages.write_page(
            root / "references" / f"{slug}.md",
            source_fm(sid, title, grade, ind),
            f"# {title}\n",
        )
    return root


def claim_page(root: Path, claim_id: str) -> pages.Page:
    page = pages.find_by_id(root, claim_id)
    assert page is not None, f"no page for {claim_id}"
    return page


# --- add_claim ---------------------------------------------------------------


def test_add_claim_shape_and_corroboration(sourced: Path):
    page = claims.add_claim(sourced, "the sky is blue", ["A1", "A2"], load_bearing=True)
    fm = page.fm
    assert fm["type"] == "Claim"
    assert fm["id"] == "C1"
    assert fm["aliases"] == ["C1"]
    assert fm["description"] == "the sky is blue"
    assert fm["status"] == "asserted"
    assert fm["load_bearing"] is True
    assert fm["sources"] == ["A1", "A2"]
    assert fm["supports"] == ["/references/orig-b", "/references/repub-a"]
    assert fm["independent_corroboration"] == 1  # only A1 is independence=original
    assert fm["first_asserted"] == util.today()
    assert fm["actor"] == "agent:test"
    assert "notes" not in fm
    # the page is the canonical record, slugged from the claim text
    assert page.path == sourced / "claims" / "the-sky-is-blue.md"
    assert pages.read_page(page.path).fm == fm


def test_add_claim_body_has_text_notes_and_citations(sourced: Path):
    page = claims.add_claim(
        sourced, "the sky is blue", ["A1", "ZZ9"], notes="single vendor study"
    )
    body = pages.read_page(page.path).body
    # parse keeps the blank separator line after the frontmatter, hence lstrip
    assert body.lstrip("\n").startswith("the sky is blue\n")
    assert "_single vendor study_" in body
    assert "# Citations" in body
    assert "[1] [orig B](../references/orig-b.md)" in body
    assert "[2] ZZ9" in body  # dangling citation is plain text, not a link


def test_citation_links_point_at_real_files(sourced: Path):
    page = claims.add_claim(sourced, "x", ["A1", "A3"])
    for rel in ("../references/orig-b.md", "../references/orig-c.md"):
        assert f"({rel})" in page.body
        assert (page.path.parent / rel).resolve().is_file()


def test_add_claim_description_truncated_to_160(sourced: Path):
    long = "word " * 60
    page = claims.add_claim(sourced, long, [])
    assert len(page.fm["description"]) <= 160
    assert page.fm["description"].endswith("…")
    assert long.strip() in page.body  # the full text lives in the body


def test_add_claim_notes_and_touch(sourced: Path):
    page = claims.add_claim(sourced, "x", [], notes="single vendor study")
    assert page.fm["notes"] == "single vendor study"
    assert page.fm["independent_corroboration"] == 0
    assert page.fm["supports"] == []
    assert load_manifest(sourced).updated == util.today()


def test_add_claim_no_sources_yet_gives_zero(root: Path):
    page = claims.add_claim(root, "x", ["A1", "A2"])
    assert page.fm["independent_corroboration"] == 0
    assert page.fm["supports"] == []  # nothing resolvable
    assert "[1] A1" in page.body  # cited dangling all the same


def test_add_claim_unknown_and_duplicate_sources(sourced: Path):
    page = claims.add_claim(sourced, "x", ["A1", "A1", "ZZ9"])
    assert page.fm["independent_corroboration"] == 1  # deduped, unknown id ignored
    assert page.fm["sources"] == ["A1", "A1", "ZZ9"]  # as given
    assert page.fm["supports"] == ["/references/orig-b"]  # deduped, resolvable only


def test_add_claim_empty_text_raises(sourced: Path):
    with pytest.raises(SystemExit, match="empty claim text"):
        claims.add_claim(sourced, "  ", ["A1"])


def test_claim_ids_never_reused(sourced: Path):
    claims.add_claim(sourced, "one", [])
    claims.add_claim(sourced, "two", [])
    claims.set_claim_status(sourced, "C2", "retracted")
    assert claims.add_claim(sourced, "three", []).fm["id"] == "C3"


def test_claim_id_not_reused_after_page_deletion(sourced: Path):
    # deleting a claim page must not free its id (SPEC §9): the allocation is
    # backstopped by the append-only .flip/ids reservation file
    first = claims.add_claim(sourced, "one", [])
    assert first.fm["id"] == "C1"
    first.path.unlink()
    assert claims.add_claim(sourced, "two", []).fm["id"] == "C2"
    reserved = (sourced / ".flip" / "ids").read_text(encoding="utf-8").splitlines()
    assert reserved == ["C1", "C2"]


def test_claim_slug_collision_gets_numeric_suffix(sourced: Path):
    first = claims.add_claim(sourced, "the sky is blue", [])
    second = claims.add_claim(sourced, "the sky is blue!", [])  # same slug basis
    assert first.path.name == "the-sky-is-blue.md"
    assert second.path.name == "the-sky-is-blue-2.md"
    assert second.fm["id"] == "C2"


# --- set_claim_status --------------------------------------------------------


def test_set_status_invalid_raises(sourced: Path):
    claims.add_claim(sourced, "x", [])
    with pytest.raises(SystemExit, match="invalid claim status 'bogus'"):
        claims.set_claim_status(sourced, "C1", "bogus")


def test_set_status_unknown_claim_raises(sourced: Path):
    claims.add_claim(sourced, "x", [])
    with pytest.raises(SystemExit, match=r"no claim 'C9'.*known: C1"):
        claims.set_claim_status(sourced, "C9", "needs-2nd")


def test_set_status_recomputes_corroboration_and_supports(root: Path):
    page = claims.add_claim(root, "x", ["A1"])  # no reference pages yet
    assert page.fm["independent_corroboration"] == 0
    assert page.fm["supports"] == []
    pages.write_page(
        root / "references" / "orig-b.md",
        source_fm("A1", "orig B", "B", "original"),
        "# orig B\n",
    )
    updated = claims.set_claim_status(root, "C1", "needs-2nd")
    assert updated.fm["independent_corroboration"] == 1
    assert updated.fm["status"] == "needs-2nd"
    assert updated.fm["supports"] == ["/references/orig-b"]
    on_disk = pages.read_page(updated.path)
    assert on_disk.fm["independent_corroboration"] == 1
    assert "[1] [orig B](../references/orig-b.md)" in on_disk.body  # citation refreshed


def test_set_status_refreshes_citations_after_source_rename(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    # simulate `flip rename A1 primary-study`: the page moves, the id stays
    (sourced / "references" / "orig-b.md").rename(
        sourced / "references" / "primary-study.md"
    )
    updated = claims.set_claim_status(sourced, "C1", "needs-2nd")
    assert updated.fm["supports"] == ["/references/primary-study"]
    body = pages.read_page(updated.path).body
    assert "(../references/primary-study.md)" in body
    assert "orig-b.md" not in body


def test_set_status_round_trips_foreign_frontmatter_and_prose(sourced: Path):
    page = claims.add_claim(sourced, "the sky is blue", ["A1"])
    # a human annotates the page in Obsidian: foreign key + prose above citations
    edited = pages.read_page(page.path)
    edited.fm["review_flag"] = "check with desk"
    body = edited.body.replace(
        "# Citations", "Editor caveat: metric definition shifted in 2024.\n\n# Citations"
    )
    pages.write_page(page.path, edited.fm, body)

    updated = claims.set_claim_status(sourced, "C1", "needs-2nd")

    on_disk = pages.read_page(page.path)
    assert on_disk.fm["review_flag"] == "check with desk"  # foreign key survives
    assert "Editor caveat: metric definition shifted in 2024." in on_disk.body
    assert on_disk.body.count("# Citations") == 1  # block regenerated, not duplicated
    assert on_disk.fm["status"] == "needs-2nd"
    assert updated.fm == on_disk.fm


def test_set_status_rewrites_are_byte_stable(sourced: Path):
    # read-modify-write must not accrete whitespace (SPEC §12): re-setting the
    # same status leaves the file byte-identical.
    page = claims.add_claim(sourced, "x", ["A1"], notes="caveat")
    claims.set_claim_status(sourced, "C1", "needs-2nd")
    first = page.path.read_text(encoding="utf-8")
    claims.set_claim_status(sourced, "C1", "needs-2nd")
    assert page.path.read_text(encoding="utf-8") == first


def test_verify_meets_min_independent(sourced: Path):
    # scout profile: claim_min_independent = 1; A1 is original
    claims.add_claim(sourced, "x", ["A1"])
    assert claims.set_claim_status(sourced, "C1", "verified").fm["status"] == "verified"


def test_verify_grade_a_suffices(sourced: Path):
    # A2 is a republisher (0 original) but grade A, and scout allows grade-A shortcuts
    claims.add_claim(sourced, "x", ["A2"])
    page = claims.set_claim_status(sourced, "C1", "verified")
    assert page.fm["status"] == "verified"
    assert page.fm["independent_corroboration"] == 0


def test_verify_below_bar_raises_actionable(sourced: Path):
    # strict local profile: 2 independent required, grade A does not suffice
    strict = sourced / ".flip" / "profiles" / "strict.toml"
    strict.parent.mkdir(parents=True)
    strict.write_text(
        'id = "strict"\nclaim_min_independent = 2\nclaim_grade_a_suffices = false\n',
        encoding="utf-8",
    )
    index = sourced / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace("kind: scout", "kind: strict"),
        encoding="utf-8",
    )
    claims.add_claim(sourced, "x", ["A1", "A2"])  # 1 original, grade A present but moot
    with pytest.raises(SystemExit, match=r"cannot verify C1: 1 independent.*of 2 required"):
        claims.set_claim_status(sourced, "C1", "verified")
    # status unchanged on disk
    assert claim_page(sourced, "C1").fm["status"] == "asserted"


def test_verify_no_sources_message_names_gap(sourced: Path):
    claims.add_claim(sourced, "x", [])
    with pytest.raises(SystemExit, match=r"sources: none.*grade A"):
        claims.set_claim_status(sourced, "C1", "verified")


# --- ungraded sources never corroborate (SPEC §5.4) ---------------------------


def test_corroboration_count_ignores_ungraded_and_dedupes():
    fms = SOURCE_FMS
    assert claims.corroboration_count(fms, ["A4"]) == 0  # grade "?" is inert
    assert claims.corroboration_count(fms, ["A1", "A4"]) == 1
    assert claims.corroboration_count(fms, ["A1", "A1", "A1"]) == 1  # deduped
    assert claims.corroboration_count(fms, ["A2"]) == 0  # judged but republisher
    assert claims.corroboration_count(fms, ["A1", "A3", "ZZ9"]) == 2


def test_add_claim_ungraded_source_counts_zero(sourced: Path):
    page = claims.add_claim(sourced, "x", ["A4"])
    assert page.fm["independent_corroboration"] == 0


def test_verify_refused_when_only_source_is_ungraded(sourced: Path):
    # scout needs 1 independent original; A4's capture-time defaults say
    # original/fresh but it was never judged — the bar must not see it.
    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    with pytest.raises(SystemExit) as ei:
        claims.set_claim_status(sourced, "C1", "verified")
    msg = str(ei.value)
    assert "cannot verify C1: 0 independent original source(s)" in msg
    assert "A4" in msg and "flip grade" in msg  # names the unjudged source
    assert claim_page(sourced, "C1").fm["status"] == "asserted"


def test_grading_the_source_then_allows_verification(sourced: Path):
    from flip import sources as sources_mod

    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    with pytest.raises(SystemExit):
        claims.set_claim_status(sourced, "C1", "verified")
    sources_mod.grade_source(sourced, "A4", grade="B", independence="original")
    page = claims.set_claim_status(sourced, "C1", "verified")
    assert page.fm["status"] == "verified"
    assert page.fm["independent_corroboration"] == 1


# --- scalar-typed list fields (hand edits) -------------------------------------


def test_set_status_tolerates_scalar_sources(sourced: Path):
    # a hand-edited page can legally say `sources: A1` (a YAML scalar): it is
    # ONE source id, never the characters "A" and "1"
    page = claims.add_claim(sourced, "x", ["A1"])
    edited = pages.read_page(page.path)
    edited.fm["sources"] = "A1"  # what `sources: A1` parses to
    pages.write_page(page.path, edited.fm, edited.body)

    updated = claims.set_claim_status(sourced, "C1", "needs-2nd")

    assert updated.fm["independent_corroboration"] == 1  # A1 is judged original
    assert updated.fm["supports"] == ["/references/orig-b"]
    body = pages.read_page(page.path).body
    assert "[1] [orig B](../references/orig-b.md)" in body
    assert "[1] A\n" not in body and "[2] 1" not in body  # no char-split citations


# --- list_claims -------------------------------------------------------------


def test_list_claims_all_and_filtered(sourced: Path):
    claims.add_claim(sourced, "one", ["A1"])
    claims.add_claim(sourced, "two", [])
    claims.set_claim_status(sourced, "C1", "verified")
    assert [c["id"] for c in claims.list_claims(sourced)] == ["C1", "C2"]
    assert [c["id"] for c in claims.list_claims(sourced, status="verified")] == ["C1"]
    assert claims.list_claims(sourced, status="retracted") == []
    rows = claims.list_claims(sourced)
    assert rows[0]["slug"] == "one"
    assert rows[0]["path"] == "claims/one.md"


def test_list_claims_invalid_status_raises(sourced: Path):
    with pytest.raises(SystemExit, match="invalid claim status"):
        claims.list_claims(sourced, status="nope")


def test_list_claims_empty_notebook(root: Path):
    assert claims.list_claims(root) == []


# --- mutators validate the notebook before writing ----------------------------


def test_add_claim_outside_notebook_writes_nothing(tmp_path: Path):
    outside = tmp_path / "not-a-notebook"
    outside.mkdir()
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        claims.add_claim(outside, "x", [])
    assert not (outside / "claims").exists()


def test_set_claim_status_outside_notebook_raises(tmp_path: Path):
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        claims.set_claim_status(tmp_path, "C1", "retracted")
