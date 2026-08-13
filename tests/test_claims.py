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

# id, slug, title, grade, independence, support — the judgment matrix the bar
# tests need. A1/A3 are independence="independent" (judged via the tuple's
# spine) and corroborate. A2 is judged only via a migration-seed marker
# (support.seeded == "legacy-grade", design D-A): it derives to grade A so it
# clears the grade-A-suffices path, but carries no `independence` key, so it
# never counts toward corroboration. A4 is captured but never judged at all —
# no independence key, no seed — an inert "?" that must corroborate nothing
# (SPEC §5.4).
SOURCE_ROWS = [
    ("A1", "orig-b", "orig B", "B", "independent",
     {"basis": "single-operator", "method": "n=200 survey"}),
    ("A2", "repub-a", "repub A", "A", None, {"seeded": "legacy-grade"}),
    ("A3", "orig-c", "orig C", "C", "independent", None),
    ("A4", "unjudged", "unjudged", "?", None, None),
]


def source_fm(
    sid: str,
    title: str,
    grade: str,
    independence: str | None = None,
    support: dict | None = None,
) -> dict:
    fm: dict = {
        "type": "Source", "id": sid, "aliases": [sid], "title": title,
        "local": f"sources/raw/{sid}.html", "grade": grade, "status": "captured",
    }
    if independence:
        fm["independence"] = independence
        fm["freshness"] = "fresh"
    if support:
        fm["support"] = support
    return fm


SOURCE_FMS = [
    source_fm(sid, title, grade, ind, sup)
    for sid, _, title, grade, ind, sup in SOURCE_ROWS
]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    (tmp_path / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    return tmp_path.resolve()


@pytest.fixture
def sourced(root: Path) -> Path:
    for sid, slug, title, grade, ind, sup in SOURCE_ROWS:
        pages.write_page(
            root / "references" / f"{slug}.md",
            source_fm(sid, title, grade, ind, sup),
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
    assert fm["sources"] == [
        {"id": "A1", "resource": "/references/orig-b.md", "title": "orig B"},
        {"id": "A2", "resource": "/references/repub-a.md", "title": "repub A"},
    ]
    assert claims.source_ids(fm) == ["A1", "A2"]
    assert fm["independent_corroboration"] == 1  # only A1 is independence=independent
    assert fm["first_asserted"] == util.today()
    assert pages.generated_by(fm) == "agent:test"
    assert "notes" not in fm
    # the page is the canonical record, slugged from the claim text
    assert page.path == sourced / "claims" / "the-sky-is-blue.md"
    assert pages.read_page(page.path).fm == fm


def test_add_claim_absence_corpus_scope(sourced: Path):
    page = claims.add_claim(sourced, "no filing names the trust", ["A1"],
                            absent_from="corpus")
    assert page.fm["absence"] == {"scope": "corpus"}


def test_add_claim_absence_named_surfaces_records_coverage(sourced: Path):
    page = claims.add_claim(
        sourced, "no registry entry exists", ["A1"],
        absent_from="named_surfaces",
        surfaces=["state registry", "court index", "  "],
    )
    assert page.fm["absence"] == {
        "scope": "named_surfaces",
        "surfaces": ["state registry", "court index"],
    }


def test_add_claim_absence_beyond_corpus_requires_surfaces(sourced: Path):
    with pytest.raises(SystemExit, match="asserts more than this corpus"):
        claims.add_claim(sourced, "nothing anywhere", ["A1"],
                         absent_from="named_surfaces")


def test_add_claim_surface_without_scope_raises(sourced: Path):
    with pytest.raises(SystemExit, match="--surface given without --absent-from"):
        claims.add_claim(sourced, "text", ["A1"], surfaces=["somewhere"])


def test_add_claim_invalid_absence_scope_raises(sourced: Path):
    with pytest.raises(SystemExit, match="invalid absent_from 'universe'"):
        claims.add_claim(sourced, "text", ["A1"], absent_from="universe")


def test_add_claim_without_absence_writes_no_key(sourced: Path):
    page = claims.add_claim(sourced, "the sky is blue", ["A1"])
    assert "absence" not in page.fm


def test_add_claim_derives_from_records_edges(sourced: Path):
    claims.add_claim(sourced, "base finding", ["A1"])
    page = claims.add_claim(sourced, "built on it", ["A1"], derives_from=["C1"])
    assert page.fm["derives_from"] == ["C1"]


def test_add_claim_derives_from_unknown_or_nonclaim_raises(sourced: Path):
    with pytest.raises(SystemExit, match="unknown claim id 'C9'"):
        claims.add_claim(sourced, "text", ["A1"], derives_from=["C9"])
    with pytest.raises(SystemExit, match="unknown claim id 'A1'"):
        claims.add_claim(sourced, "text", ["A1"], derives_from=["A1"])


def test_claim_derivation_post_hoc_add_and_rm(sourced: Path):
    claims.add_claim(sourced, "base", ["A1"])
    claims.add_claim(sourced, "middle", ["A1"])
    page, added = claims.add_claim_derivation(sourced, "C2", ["C1"])
    assert added == ["C1"] and page.fm["derives_from"] == ["C1"]
    with pytest.raises(SystemExit, match="already derives from C1"):
        claims.add_claim_derivation(sourced, "C2", ["C1"])
    page = claims.remove_claim_derivation(sourced, "C2", "C1")
    assert "derives_from" not in page.fm
    with pytest.raises(SystemExit, match="does not derive from C1"):
        claims.remove_claim_derivation(sourced, "C2", "C1")


def test_claim_derivation_refuses_self_and_cycles(sourced: Path):
    claims.add_claim(sourced, "base", ["A1"])
    claims.add_claim(sourced, "middle", ["A1"], derives_from=["C1"])
    with pytest.raises(SystemExit, match="cannot derive from itself"):
        claims.add_claim_derivation(sourced, "C1", ["C1"])
    with pytest.raises(SystemExit, match="would close a cycle"):
        claims.add_claim_derivation(sourced, "C1", ["C2"])  # C2 rests on C1


def test_unit_without_value_refused_before_id_allocation(sourced: Path):
    # a refusal after allocate_id would burn a C# forever (ids never reused)
    with pytest.raises(SystemExit, match="--unit given without --value"):
        claims.add_claim(sourced, "quant", ["A1"], unit="ms")
    assert claims.add_claim(sourced, "next", ["A1"]).fm["id"] == "C1"


def test_unsupported_reason_dual_role_citation_counts_like_corroboration(sourced: Path):
    # same id cited as evidence AND subject: subject wins everywhere else
    # (evidence_ids collapses it), so the derivation walk must agree
    fm = {"id": "C1", "status": "asserted",
          "sources": [{"id": "A1"}, {"id": "A1", "role": "subject"}]}
    assert claims.evidence_ids(fm) == []
    assert claims.unsupported_reason(fm) == \
        "no evidence sources and no surviving verification"


def test_unsupported_reason_vocabulary(sourced: Path):
    supported = claims.add_claim(sourced, "well backed", ["A1"])
    assert claims.unsupported_reason(supported.fm) is None
    bare = claims.add_claim(sourced, "nothing backs this", [])
    assert claims.unsupported_reason(bare.fm) == \
        "no evidence sources and no surviving verification"
    retracted = claims.add_claim(sourced, "walked back", ["A1"])
    retracted.fm["status"] = "retracted"
    assert claims.unsupported_reason(retracted.fm) == "status retracted"


def test_add_claim_body_has_text_notes_and_citations(sourced: Path):
    page = claims.add_claim(
        sourced, "the sky is blue", ["A1", "ZZ9"], notes="single vendor study"
    )
    body = pages.read_page(page.path).body
    # parse keeps the blank separator line after the frontmatter, hence lstrip
    assert body.lstrip("\n").startswith("the sky is blue[^A1][^ZZ9]\n")
    assert "_single vendor study_" in body
    assert "# Citations" not in body  # no more heading; footnote defs instead
    assert "[^A1]: [orig B](../references/orig-b.md)" in body
    assert "[^ZZ9]: ZZ9 (not captured)" in body  # dangling citation, plain form


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
    assert page.fm["sources"] == []
    assert load_manifest(sourced).updated == util.today()


def test_add_claim_no_sources_yet_gives_zero(root: Path):
    page = claims.add_claim(root, "x", ["A1", "A2"])
    assert page.fm["independent_corroboration"] == 0
    assert page.fm["sources"] == [{"id": "A1"}, {"id": "A2"}]  # nothing resolvable
    assert "[^A1][^A2]" in page.body  # cited dangling all the same
    assert "[^A1]: A1 (not captured)" in page.body
    assert "[^A2]: A2 (not captured)" in page.body


def test_add_claim_unknown_and_duplicate_sources(sourced: Path):
    page = claims.add_claim(sourced, "x", ["A1", "A1", "ZZ9"])
    assert page.fm["independent_corroboration"] == 1  # deduped, unknown id ignored
    assert page.fm["sources"] == [
        {"id": "A1", "resource": "/references/orig-b.md", "title": "orig B"},
        {"id": "ZZ9"},
    ]  # deduped; unknown id keeps just its id
    assert claims.source_ids(page.fm) == ["A1", "ZZ9"]


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
    assert page.fm["sources"] == [{"id": "A1"}]
    pages.write_page(
        root / "references" / "orig-b.md",
        source_fm("A1", "orig B", "B", "independent"),
        "# orig B\n",
    )
    updated = claims.set_claim_status(root, "C1", "needs-2nd")
    assert updated.fm["independent_corroboration"] == 1
    assert updated.fm["status"] == "needs-2nd"
    assert updated.fm["sources"] == [
        {"id": "A1", "resource": "/references/orig-b.md", "title": "orig B"}
    ]
    on_disk = pages.read_page(updated.path)
    assert on_disk.fm["independent_corroboration"] == 1
    assert "[^A1]: [orig B](../references/orig-b.md)" in on_disk.body  # citation refreshed


def test_set_status_refreshes_citations_after_source_rename(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    # simulate `flip rename A1 primary-study`: the page moves, the id stays
    (sourced / "references" / "orig-b.md").rename(
        sourced / "references" / "primary-study.md"
    )
    updated = claims.set_claim_status(sourced, "C1", "needs-2nd")
    assert updated.fm["sources"] == [
        {"id": "A1", "resource": "/references/primary-study.md", "title": "orig B"}
    ]
    body = pages.read_page(updated.path).body
    assert "(../references/primary-study.md)" in body
    assert "orig-b.md" not in body


def test_set_status_round_trips_foreign_frontmatter_and_prose(sourced: Path):
    page = claims.add_claim(sourced, "the sky is blue", ["A1"])
    # a human annotates the page in Obsidian: foreign key + prose above the
    # generated footnote-definition lines (no more "# Citations" heading)
    edited = pages.read_page(page.path)
    edited.fm["review_flag"] = "check with desk"
    body = edited.body.replace(
        "\n\n[^A1]:",
        "\n\nEditor caveat: metric definition shifted in 2024.\n\n[^A1]:",
    )
    pages.write_page(page.path, edited.fm, body)

    updated = claims.set_claim_status(sourced, "C1", "needs-2nd")

    on_disk = pages.read_page(page.path)
    assert on_disk.fm["review_flag"] == "check with desk"  # foreign key survives
    assert "Editor caveat: metric definition shifted in 2024." in on_disk.body
    assert on_disk.body.count("[^A1]: [orig B]") == 1  # def regenerated, not duplicated
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
    # scout profile: claim_min_independent = 1; A1 is independence=independent
    claims.add_claim(sourced, "x", ["A1"])
    assert claims.set_claim_status(sourced, "C1", "verified").fm["status"] == "verified"


def test_verify_grade_a_suffices(sourced: Path):
    # A2 has no independence key (0 independent corroboration) but derives to
    # grade A via a migration-seed marker, and scout allows grade-A shortcuts
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
    claims.add_claim(sourced, "x", ["A1", "A2"])  # 1 independent, grade A present but moot
    with pytest.raises(SystemExit, match=r"cannot verify C1: 1 independent.*of 2 required"):
        claims.set_claim_status(sourced, "C1", "verified")
    # status unchanged on disk
    assert claim_page(sourced, "C1").fm["status"] == "asserted"


def test_verify_no_sources_message_names_gap(sourced: Path):
    claims.add_claim(sourced, "x", [])
    with pytest.raises(SystemExit, match=r"evidence: none.*grade A"):
        claims.set_claim_status(sourced, "C1", "verified")


# --- ungraded sources never corroborate (SPEC §5.4) ---------------------------


def test_corroboration_count_ignores_ungraded_and_dedupes():
    fms = SOURCE_FMS
    assert claims.corroboration_count(fms, ["A4"]) == 0  # grade "?" is inert
    assert claims.corroboration_count(fms, ["A1", "A4"]) == 1
    assert claims.corroboration_count(fms, ["A1", "A1", "A1"]) == 1  # deduped
    assert claims.corroboration_count(fms, ["A2"]) == 0  # judged (legacy seed), not independence=independent
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
    assert "cannot verify C1: 0 independent source(s)" in msg
    assert "A4" in msg and "flip grade" in msg  # names the unjudged source
    assert claim_page(sourced, "C1").fm["status"] == "asserted"


def test_grading_the_source_then_allows_verification(sourced: Path):
    from flip import sources as sources_mod

    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    with pytest.raises(SystemExit):
        claims.set_claim_status(sourced, "C1", "verified")
    sources_mod.grade_source(
        sourced, "A4", independence="independent", basis="single-operator", method="site visit"
    )
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

    assert updated.fm["independent_corroboration"] == 1  # A1 is judged independent
    assert updated.fm["sources"] == [
        {"id": "A1", "resource": "/references/orig-b.md", "title": "orig B"}
    ]
    body = pages.read_page(page.path).body
    assert "[^A1]: [orig B](../references/orig-b.md)" in body
    assert "[^A]" not in body and "[^1]" not in body  # no char-split citations


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


# --- post-hoc source links (A1) ----------------------------------------------


def test_source_add_links_and_recomputes(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])  # 1 independent → corroboration 1
    page, added, _rerolled, warnings = claims.add_claim_sources(sourced, "C1", ["A3"])
    assert added == ["A3"]
    assert warnings == []
    assert claims.source_ids(page.fm) == ["A1", "A3"]
    assert page.fm["sources"] == [
        {"id": "A1", "resource": "/references/orig-b.md", "title": "orig B"},
        {"id": "A3", "resource": "/references/orig-c.md", "title": "orig C"},
    ]
    assert page.fm["independent_corroboration"] == 2  # A1 + A3 both judged independent
    on_disk = pages.read_page(page.path)
    assert "[^A3]: [orig C](../references/orig-c.md)" in on_disk.body  # citations regenerated
    assert on_disk.fm["independent_corroboration"] == 2


def test_source_add_refuses_unknown_id(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    with pytest.raises(SystemExit, match=r"unknown source id\(s\) ZZ9"):
        claims.add_claim_sources(sourced, "C1", ["ZZ9"])
    assert claims.source_ids(claim_page(sourced, "C1").fm) == ["A1"]  # nothing written


def test_source_add_warns_on_ungraded(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    page, added, _rerolled, warnings = claims.add_claim_sources(sourced, "C1", ["A4"])
    assert added == ["A4"]
    assert warnings == [("A4", "unjudged")]  # graded "?" — links, but never counts
    assert page.fm["independent_corroboration"] == 1  # still just A1


def test_source_add_refuses_when_all_already_linked(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    with pytest.raises(SystemExit, match="already cites A1"):
        claims.add_claim_sources(sourced, "C1", ["A1"])


def test_source_rm_unlinks_and_recomputes(sourced: Path):
    claims.add_claim(sourced, "x", ["A1", "A3"])
    page = claims.remove_claim_source(sourced, "C1", "A1")
    assert claims.source_ids(page.fm) == ["A3"]
    assert page.fm["sources"] == [
        {"id": "A3", "resource": "/references/orig-c.md", "title": "orig C"}
    ]
    assert page.fm["independent_corroboration"] == 1
    assert "orig-b.md" not in pages.read_page(page.path).body


def test_source_rm_refuses_uncited(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    with pytest.raises(SystemExit, match="does not cite A3"):
        claims.remove_claim_source(sourced, "C1", "A3")


def test_source_ops_unknown_claim_raises(sourced: Path):
    with pytest.raises(SystemExit, match=r"no claim 'C9'"):
        claims.add_claim_sources(sourced, "C9", ["A1"])


# --- verification records (A2) -----------------------------------------------


def test_verify_records_appended(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    page = claims.verify_claim(sourced, "C1", "adversarial",
                               against=["A1", "A3"], note="skeptic pass")
    rec = page.fm["verified"][0]
    assert rec["method"] == "adversarial"
    assert rec["by"] == "agent:test"
    assert rec["against"] == ["A1", "A3"]
    assert rec["at"].startswith(util.today())  # full ISO-8601 UTC datetime
    assert rec["note"] == "skeptic pass"
    assert pages.read_page(page.path).fm["verified"] == page.fm["verified"]


def test_verify_is_append_only(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    claims.verify_claim(sourced, "C1", "adversarial")
    page = claims.verify_claim(sourced, "C1", "recomputation")
    assert [v["method"] for v in page.fm["verified"]] == ["adversarial", "recomputation"]


def test_verify_invalid_method_raises(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    with pytest.raises(SystemExit, match="invalid verification method"):
        claims.verify_claim(sourced, "C1", "vibes")


def test_verified_gate_passes_on_adversarial_record(sourced: Path):
    # A4 is ungraded → 0 corroboration; scout needs 1. An adversarial record
    # clears the gate on its own (A2).
    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    with pytest.raises(SystemExit):
        claims.set_claim_status(sourced, "C1", "verified")
    claims.verify_claim(sourced, "C1", "adversarial", note="sought disconfirming, found none")
    page = claims.set_claim_status(sourced, "C1", "verified")
    assert page.fm["status"] == "verified"
    assert page.fm["independent_corroboration"] == 0  # gate passed without corroboration


def test_verified_gate_refusal_names_both_paths(sourced: Path):
    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    with pytest.raises(SystemExit) as ei:
        claims.set_claim_status(sourced, "C1", "verified")
    msg = str(ei.value)
    assert "independent source(s)" in msg  # the corroboration path
    assert "flip claim verify C1" in msg and "adversarial" in msg  # the verification path


def test_independent_sources_record_does_not_satisfy_gate(sourced: Path):
    # independent-sources records the corroboration reasoning but is not a
    # gating method — only the recomputed source count is.
    claims.add_claim(sourced, "x", ["A4"], load_bearing=True)
    claims.verify_claim(sourced, "C1", "independent-sources", note="argued 2 lines up")
    with pytest.raises(SystemExit, match="cannot verify C1"):
        claims.set_claim_status(sourced, "C1", "verified")


# --- uncountable sources: a wrong count is worse than a missing one -------------


def test_uncountable_sources_names_pre_08_pages():
    stale = source_fm("A7", "Old", "A", "original")
    current = source_fm("A8", "New", "A", "independent")
    fms = [stale, current]
    assert claims.corroboration_count(fms, ["A7", "A8"]) == 1  # A7 drops out
    assert claims.uncountable_sources(fms, ["A7", "A8"]) == ["A7"]  # and here is why
    assert claims.uncountable_sources(fms, ["A8"]) == []
    assert claims.uncountable_sources(fms, ["A7", "A7"]) == ["A7"]  # deduped
    assert claims.uncountable_sources(fms, ["ZZ9"]) == []  # dangling: not ours to explain


def test_verify_refusal_explains_that_the_count_is_not_a_verdict(root: Path):
    # The exact shape that cost an agent-run: a claim whose only source shows a
    # confident A but carries pre-0.8 vocabulary, so corroboration reads 0 and
    # the refusal used to blame the evidence.
    pages.write_page(
        root / "references" / "stale.md",
        source_fm("A1", "Carried over", "A", "original"),
        "# Carried over\n",
    )
    claims.add_claim(root, "x", ["A1"], load_bearing=True)
    with pytest.raises(SystemExit) as ei:
        claims.set_claim_status(root, "C1", "verified")
    msg = str(ei.value)
    assert "A1 carries pre-0.8 independence vocabulary" in msg
    assert "cannot be counted either way" in msg
    assert "not a verdict on the evidence" in msg
    assert "flip migrate" in msg
    # and it is NOT reported as a merely-unjudged source: that advice is wrong here
    assert "still unjudged" not in msg


# --- citation roles: what a citation is FOR (SPEC §7) ---------------------------
#
# The distinction these tests defend: a claim ABOUT a document cannot be
# corroborated, because the only conceivable second source is a second READING
# of the same document — an independent reader, not an independent causal path
# to the fact. Reporting that situation as `independent_corroboration: 0` is
# the same wrong number `uncountable_sources` exists to prevent: it reads as
# "the evidence is thin" when the truth is "this axis does not apply here".


def _attribution_test(root: Path, claim_id: str, against: str, result: str = "survived"):
    """A severe attribution test — all four of Mayo's conditions written, so
    `test_severity` reads it as severe and it can stand in for the count."""
    return claims.record_test(
        root,
        claim_id,
        probe="attribution",
        error=f"That the claim is not what {against} says",
        would_detect="A string search of the text returning the disputed phrase",
        if_absent="Zero hits, and an abstract naming something else entirely",
        against=[against],
        result=result,
    )


def test_a_subject_citation_carries_its_role_and_the_count_is_absent(sourced: Path):
    # The epistemics C30 shape: the claim is about the rebuttal, so the
    # rebuttal is the fact-maker rather than a witness. The key is GONE, not
    # zero — only a missing number prompts anybody to look at why.
    page = claims.add_claim(sourced, "the paper never mentions Persson", [], subjects=["A1"])
    assert page.fm["sources"] == [
        {"id": "A1", "role": "subject", "resource": "/references/orig-b.md", "title": "orig B"}
    ]
    assert "independent_corroboration" not in page.fm
    assert claims.subject_ids(page.fm) == ["A1"]
    assert claims.evidence_ids(page.fm) == []
    assert claims.corroboration_applies(page.fm) is False
    # the citation edge is untouched: the footnote is a link, not an annotation
    assert "[^A1]" in page.body
    assert "[^A1]: [orig B](../references/orig-b.md)" in page.body


def test_an_evidence_citation_is_the_default_and_writes_no_role_key(sourced: Path):
    # The muse C26/A9 shape: "writers hold this belief" is a claim about the
    # world with many possible witnesses, so corroboration applies and counts
    # exactly as it did before roles existed. No notebook needs migrating
    # because the default is the absence of the key.
    page = claims.add_claim(sourced, "writers hold this belief", ["A1", "A3"])
    assert page.fm["sources"] == [
        {"id": "A1", "resource": "/references/orig-b.md", "title": "orig B"},
        {"id": "A3", "resource": "/references/orig-c.md", "title": "orig C"},
    ]
    assert page.fm["independent_corroboration"] == 2
    assert claims.citation_role(page.fm["sources"][0]) == "evidence"


def test_a_claim_citing_nothing_still_counts_zero(sourced: Path):
    # The distinction the whole design turns on. "Nobody cited anything" is a
    # real zero — the question applies and no one answered it — and that number
    # is exactly the one that should prompt a look. Only a subject citation
    # says the instrument itself is the wrong one.
    page = claims.add_claim(sourced, "x", [])
    assert page.fm["independent_corroboration"] == 0
    assert claims.corroboration_applies(page.fm) is True


def test_a_mixed_claim_counts_only_its_witnesses(sourced: Path):
    page = claims.add_claim(
        sourced, "the paper says X and outlets report it", ["A1", "A3"], subjects=["A2"]
    )
    assert claims.evidence_ids(page.fm) == ["A1", "A3"]
    assert claims.subject_ids(page.fm) == ["A2"]
    assert page.fm["independent_corroboration"] == 2  # A2 is not in the count
    assert claims.corroboration_applies(page.fm) is True


def test_subject_wins_when_one_source_is_cited_both_ways(sourced: Path):
    # A document the claim is about cannot also be an independent witness to
    # what it says about that document, so the disagreement collapses one way
    # only — and it collapses toward the role that does NOT count.
    page = claims.add_claim(sourced, "x", ["A1"], subjects=["A1"])
    assert claims.subject_ids(page.fm) == ["A1"]
    assert claims.evidence_ids(page.fm) == []
    assert "independent_corroboration" not in page.fm


def test_an_unreadable_role_reads_as_evidence_so_a_typo_cannot_dodge_the_bar(sourced: Path):
    fm = {"sources": [{"id": "A1", "role": "subjekt"}]}
    assert claims.citation_role(fm["sources"][0]) == "evidence"
    assert claims.evidence_ids(fm) == ["A1"]
    assert claims.corroboration_applies(fm) is True  # doctor's bad-enum names it


def test_re_roling_to_subject_removes_the_stored_count(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"])
    assert claim_page(sourced, "C1").fm["independent_corroboration"] == 1
    page, added, rerolled, _warnings = claims.add_claim_sources(
        sourced, "C1", [], subjects=["A1"]
    )
    assert added == [] and rerolled == ["A1"]
    # the stale count would now read as a verdict on evidence the claim never
    # claimed to have, so it goes rather than dropping to zero
    assert "independent_corroboration" not in page.fm
    assert "independent_corroboration" not in claim_page(sourced, "C1").fm


def test_re_roling_back_to_evidence_restores_the_count(sourced: Path):
    claims.add_claim(sourced, "x", [], subjects=["A1"])
    page, _added, rerolled, _warnings = claims.add_claim_sources(sourced, "C1", ["A1"])
    assert rerolled == ["A1"]
    assert page.fm["independent_corroboration"] == 1


def test_source_add_refuses_a_citation_already_in_the_role_given(sourced: Path):
    claims.add_claim(sourced, "x", [], subjects=["A1"])
    with pytest.raises(SystemExit, match=r"already cites A1 in the role given"):
        claims.add_claim_sources(sourced, "C1", [], subjects=["A1"])


def test_subject_citations_do_not_earn_the_ungraded_warning(sourced: Path):
    # "it won't count toward the bar" is not news about a citation whose whole
    # declaration is that the bar does not apply; a warning fired where its
    # advice is meaningless is how operators learn to skim warnings.
    claims.add_claim(sourced, "x", ["A1"])
    _page, _added, _rerolled, warnings = claims.add_claim_sources(
        sourced, "C1", [], subjects=["A4"]  # A4 is graded "?"
    )
    assert warnings == []


def test_removing_the_last_witness_removes_the_count(sourced: Path):
    claims.add_claim(sourced, "x", ["A1"], subjects=["A2"])
    page = claims.remove_claim_source(sourced, "C1", "A1")
    assert "independent_corroboration" not in page.fm
    assert claims.subject_ids(page.fm) == ["A2"]


def test_status_change_drops_a_hand_written_count_from_a_subject_only_claim(sourced: Path):
    page = claims.add_claim(sourced, "x", [], subjects=["A1"])
    page.fm["independent_corroboration"] = 0  # hand edit, or a pre-0.16 page
    pages.write_page(page.path, page.fm, page.body)
    _attribution_test(sourced, "C1", "A1")
    updated = claims.set_claim_status(sourced, "C1", "needs-2nd")
    assert "independent_corroboration" not in updated.fm


# --- the verified gate on a subject-only claim ---------------------------------


def test_verify_refused_on_a_subject_claim_with_no_attribution_test(sourced: Path):
    claims.add_claim(sourced, "the paper never mentions Persson", [], subjects=["A1"])
    with pytest.raises(SystemExit) as ei:
        claims.set_claim_status(sourced, "C1", "verified")
    msg = str(ei.value)
    # the refusal must not read as "your evidence is thin" — the bar is
    # inapplicable, not unmet, and the wrong repair is the expensive one
    assert "the corroboration bar has nothing to count" in msg
    assert "Do not add a second source to clear this" in msg
    assert "--probe attribution" in msg
    assert claim_page(sourced, "C1").fm["status"] == "asserted"  # refusal writes nothing


def test_a_severe_surviving_attribution_test_reaches_verified(sourced: Path):
    # The whole point of the substitution: the audit that IS available, taken.
    # A1 is `self-reported`-adjacent here only in the sense that it cannot
    # corroborate a claim about itself — no count could ever clear this gate.
    claims.add_claim(sourced, "the paper never mentions Persson", [], subjects=["A1"])
    _attribution_test(sourced, "C1", "A1")
    page = claims.set_claim_status(sourced, "C1", "verified")
    assert page.fm["status"] == "verified"
    assert "independent_corroboration" not in page.fm


def test_a_bent_attribution_test_does_not_reach_verified(sourced: Path):
    # Severity is what makes the substitution worth anything. A record missing
    # `if_absent` describes a probe that may fire either way, and a probe that
    # fires either way discriminates nothing (SIST p.16).
    claims.add_claim(sourced, "x", [], subjects=["A1"])
    claims.record_test(
        sourced, "C1", probe="attribution", error="that it says otherwise",
        would_detect="a string search", against=["A1"], result="survived",
    )
    with pytest.raises(SystemExit, match=r"no severe, surviving one is on record"):
        claims.set_claim_status(sourced, "C1", "verified")


def test_a_failed_attribution_test_is_still_refused_by_the_exposure_gate(sourced: Path):
    # The substitution never opens a door the test record closes: a severe
    # attribution FAILURE derives `misattributed`, which is refused before the
    # count — or its absence — is even consulted.
    claims.add_claim(sourced, "x", [], subjects=["A1"])
    _attribution_test(sourced, "C1", "A1", result="failed")
    with pytest.raises(SystemExit, match=r"exposure is 'misattributed'"):
        claims.set_claim_status(sourced, "C1", "verified")


def test_every_subject_must_be_audited_not_just_one(sourced: Path):
    claims.add_claim(sourced, "two documents disagree", [], subjects=["A1", "A3"])
    _attribution_test(sourced, "C1", "A1")
    with pytest.raises(SystemExit, match=r"no severe, surviving one is on record against A3"):
        claims.set_claim_status(sourced, "C1", "verified")
    assert claims.unaudited_subjects(claim_page(sourced, "C1").fm) == ["A3"]


def test_an_adversarial_record_still_clears_the_gate_on_a_subject_claim(sourced: Path):
    # A2's other path is untouched. The change substitutes for the count that
    # cannot be taken; it does not narrow the routes that already existed.
    claims.add_claim(sourced, "x", [], subjects=["A1"])
    claims.verify_claim(sourced, "C1", "adversarial", against=["A1"])
    assert claims.set_claim_status(sourced, "C1", "verified").fm["status"] == "verified"


def test_the_gate_is_not_weakened_for_a_claim_with_any_witness(sourced: Path):
    # Only where the count has no meaning. A claim with one witness and one
    # subject faces the ordinary bar, and an attribution test on the subject
    # does not buy its way past it.
    claims.add_claim(sourced, "x", ["A4"], subjects=["A1"])  # A4 is ungraded
    _attribution_test(sourced, "C1", "A1")
    with pytest.raises(SystemExit) as ei:
        claims.set_claim_status(sourced, "C1", "verified")
    assert "0 independent source(s)" in str(ei.value)
    assert "cited as what this claim is ABOUT and never counted" in str(ei.value)


def test_a_verify_refusal_names_the_subject_it_declined_to_count(sourced: Path):
    # A source vanishing from a count without explanation is how an operator
    # spends an afternoon regrading pages that were never the problem.
    claims.add_claim(sourced, "x", ["A3"], subjects=["A2"])
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
    with pytest.raises(SystemExit) as ei:
        claims.set_claim_status(sourced, "C1", "verified")
    assert "A2 is cited as what this claim is ABOUT" in str(ei.value)
