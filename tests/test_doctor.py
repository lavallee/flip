"""Tests for flip.doctor — notebook linting against SPEC v0.4 (§15).

Fixtures are hand-built notebooks: index.md manifest, a notebook-local
profile under .flip/profiles/ (so shipped profile data can evolve without
breaking these tests), entity pages written through the pages layer, and
raw/provenance custody where a check needs it.
"""

import json
from pathlib import Path

from flip import pages
from flip.doctor import Finding, run_doctor
from flip.util import append_jsonl, today

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: test
kind: {kind}
status: {status}
created: 2026-07-01
updated: 2026-07-09
{extra}---
# test
"""

NOTEBOOK_MD = """\
---
type: Notebook
description: test
---
# Reporter's notebook — test

## The tip

> replace me
"""


def write_profile(
    root: Path,
    kind: str = "testkind",
    sections: tuple[str, ...] = (),
    requires: tuple[str, ...] = (),
    min_independent: int = 2,
    grade_a_suffices: bool = True,
    forced_policy: dict[str, str] | None = None,
) -> None:
    lines = [
        f'id = "{kind}"',
        "sections = [" + ", ".join(f'"{s}"' for s in sections) + "]",
        "requires = [" + ", ".join(f'"{r}"' for r in requires) + "]",
        f"claim_min_independent = {min_independent}",
        f"claim_grade_a_suffices = {'true' if grade_a_suffices else 'false'}",
    ]
    if forced_policy:
        lines.append("[forced_policy]")
        lines += [f'{k} = "{v}"' for k, v in forced_policy.items()]
    directory = root / ".flip" / "profiles"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{kind}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_notebook(
    tmp_path: Path,
    kind: str = "testkind",
    status: str = "active",
    extra_fm: str = "",
    profile: bool = True,
    **profile_kw,
) -> Path:
    root = tmp_path / "nb"
    root.mkdir(exist_ok=True)
    (root / "index.md").write_text(
        MANIFEST_MD.format(kind=kind, status=status, extra=extra_fm), encoding="utf-8"
    )
    (root / "notebook.md").write_text(NOTEBOOK_MD, encoding="utf-8")
    if profile:
        write_profile(root, kind=kind, **profile_kw)
    return root.resolve()


def prov_event(source_id: str, local_path: str) -> dict:
    return {
        "ts": "2026-07-09T14:31:02Z",
        "source_id": source_id,
        "local_path": local_path,
        "sha256": "0" * 64,
        "bytes": 1,
        "tool": "test",
        "actor": "human:test",
    }


def source_page(
    root: Path,
    sid: str = "A1",
    grade: str = "B",
    independence: str = "original",
    freshness: str = "fresh",
    date: str | None = None,
    raw: bool = True,
    prov: bool = True,
) -> Path:
    """A captured source: references/ page + raw bytes + provenance event."""
    local = f"sources/raw/{sid}.html"
    if raw:
        (root / "sources" / "raw").mkdir(parents=True, exist_ok=True)
        (root / local).write_text("x", encoding="utf-8")
    if prov:
        append_jsonl(root / "sources" / "_provenance.jsonl", prov_event(sid, local))
    fm: dict = {
        "type": "Source",
        "id": sid,
        "aliases": [sid],
        "title": f"source {sid}",
        "local": local,
        "grade": grade,
        "independence": independence,
        "freshness": freshness,
    }
    if date:
        fm["date"] = date
    fm["status"] = "captured"
    return pages.write_page(
        root / "references" / f"{sid.lower()}-page.md", fm, f"# source {sid}\n"
    )


def claim_page(
    root: Path,
    cid: str = "C1",
    status: str = "asserted",
    load_bearing: bool = False,
    sources: list[str] | None = None,
    corroboration: int = 0,
    body: str | None = None,
) -> Path:
    fm = {
        "type": "Claim",
        "id": cid,
        "aliases": [cid],
        "description": f"claim {cid}",
        "status": status,
        "load_bearing": load_bearing,
        "sources": sources or [],
        "independent_corroboration": corroboration,
        "first_asserted": "2026-07-09",
        "actor": "human:test",
    }
    return pages.write_page(
        root / "claims" / f"{cid.lower()}-claim.md", fm, body or f"claim {cid}\n"
    )


def codes(findings: list[Finding], level: str | None = None) -> list[str]:
    return [f.code for f in findings if level is None or f.level == level]


# --- manifest & profile ---------------------------------------------------------


def test_healthy_notebook_has_no_findings(tmp_path):
    root = make_notebook(tmp_path)
    assert run_doctor(root) == []


def test_healthy_populated_notebook_has_no_findings(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="original")
    claim_page(root, "C1", status="needs-2nd", sources=["A1"], corroboration=1)
    assert run_doctor(root) == []


def test_missing_manifest_is_bad_manifest_error(tmp_path):
    (tmp_path / "notebook.md").write_text(NOTEBOOK_MD, encoding="utf-8")
    assert "bad-manifest" in codes(run_doctor(tmp_path), "ERROR")


def test_unparseable_manifest_frontmatter_is_bad_manifest(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "index.md").write_text("---\nslug: [unclosed\n---\n# x\n", encoding="utf-8")
    assert "bad-manifest" in codes(run_doctor(root), "ERROR")


def test_manifest_missing_slug_is_bad_manifest_not_crash(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "index.md").write_text("---\nflip: '0.4'\nkind: scout\n---\n# x\n", encoding="utf-8")
    assert "bad-manifest" in codes(run_doctor(root), "ERROR")


def test_unknown_kind_is_error(tmp_path):
    root = make_notebook(tmp_path, kind="no-such-kind", profile=False)
    assert "unknown-kind" in codes(run_doctor(root), "ERROR")


def test_bad_status_and_visibility_are_errors(tmp_path):
    root = make_notebook(tmp_path, status="zombie", extra_fm="visibility: top-secret\n")
    found = codes(run_doctor(root), "ERROR")
    assert "bad-status" in found
    assert "bad-visibility" in found


def test_missing_required_paths_warn_while_active_or_dormant(tmp_path):
    # SPEC §13: profile minimums are completion requirements, not creation
    # requirements — a fresh notebook must not ERROR before the files can
    # appear through use.
    for status in ("active", "dormant"):
        root = make_notebook(
            tmp_path, status=status, requires=("references", "log/passed.jsonl")
        )
        missing = [f for f in run_doctor(root) if f.code == "missing-required"]
        assert {f.path for f in missing} == {"references", "log/passed.jsonl"}, status
        assert all(f.level == "WARN" for f in missing), status


def test_missing_required_paths_error_once_closed(tmp_path):
    for status in ("done", "published", "archived"):
        root = make_notebook(
            tmp_path, status=status, requires=("references", "log/passed.jsonl")
        )
        missing = [f for f in run_doctor(root) if f.code == "missing-required"]
        assert {f.path for f in missing} == {"references", "log/passed.jsonl"}, status
        assert all(f.level == "ERROR" for f in missing), status
        assert all(status in f.message for f in missing), status


def test_forced_policy_mismatch_is_error(tmp_path):
    root = make_notebook(
        tmp_path, forced_policy={"visibility": "client-confidential"}
    )  # manifest defaults to internal
    mismatches = [f for f in run_doctor(root) if f.code == "policy-mismatch"]
    assert mismatches and mismatches[0].level == "ERROR"
    assert "client-confidential" in mismatches[0].message
    assert mismatches[0].path == "index.md"


def test_forced_policy_satisfied_no_mismatch(tmp_path):
    root = make_notebook(
        tmp_path,
        extra_fm="visibility: client-confidential\n",
        forced_policy={"visibility": "client-confidential"},
    )
    assert "policy-mismatch" not in codes(run_doctor(root))


# --- notebook.md ------------------------------------------------------------


def test_missing_notebook_md_is_error(tmp_path):
    root = make_notebook(tmp_path)
    (root / "notebook.md").unlink()
    assert "missing-notebook" in codes(run_doctor(root), "ERROR")


def test_missing_section_heading_is_warn_per_section(tmp_path):
    root = make_notebook(tmp_path, sections=("tip", "frame", "gaps"))
    warns = [f for f in run_doctor(root) if f.code == "missing-section"]
    # notebook.md has only "The tip": frame and gaps are missing
    assert len(warns) == 2
    assert all(f.level == "WARN" for f in warns)
    assert any("Frame" in f.message for f in warns)
    assert any("Gaps & self-critique" in f.message for f in warns)


# --- okf conformance ----------------------------------------------------------


def test_unparseable_entity_page_is_bad_frontmatter_error(tmp_path):
    root = make_notebook(tmp_path)
    (root / "references").mkdir()
    (root / "references" / "broken.md").write_text(
        "---\nid: [unclosed\n---\nbody\n", encoding="utf-8"
    )
    bad = [f for f in run_doctor(root) if f.code == "bad-frontmatter"]
    assert bad and bad[0].level == "ERROR"
    assert bad[0].path == "references/broken.md"


def test_entity_page_without_type_is_missing_type_warn(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(root / "questions" / "bare.md", {"id": "Q1", "aliases": ["Q1"]}, "why?\n")
    warns = [f for f in run_doctor(root) if f.code == "missing-type"]
    assert warns and warns[0].level == "WARN"
    assert warns[0].path == "questions/bare.md"
    assert "type: Question" in warns[0].message


def test_analysis_pages_are_conformance_checked(tmp_path):
    root = make_notebook(tmp_path)
    (root / "analysis").mkdir()
    (root / "analysis" / "untyped.md").write_text("# loose prose\n", encoding="utf-8")
    pages.write_page(root / "analysis" / "typed.md", {"type": "Finding"}, "# ok\n")
    warns = [f for f in run_doctor(root) if f.code == "missing-type"]
    assert [f.path for f in warns] == ["analysis/untyped.md"]


def test_notebook_md_without_type_is_missing_type_warn(tmp_path):
    root = make_notebook(tmp_path)
    (root / "notebook.md").write_text("# no frontmatter\n\n## The tip\n", encoding="utf-8")
    warns = [f for f in run_doctor(root) if f.code == "missing-type"]
    assert [f.path for f in warns] == ["notebook.md"]
    assert "type: Notebook" in warns[0].message


def test_underscore_prefixed_files_are_skipped(tmp_path):
    root = make_notebook(tmp_path)
    (root / "references").mkdir()
    (root / "references" / "_scratch.md").write_text(
        "---\nid: [unclosed\n---\nprivate scratch\n", encoding="utf-8"
    )
    assert run_doctor(root) == []


def test_reserved_index_with_frontmatter_is_error(tmp_path):
    root = make_notebook(tmp_path)
    (root / "references").mkdir()
    (root / "references" / "index.md").write_text(
        "---\ntype: Source\nid: A1\n---\n# References\n", encoding="utf-8"
    )
    found = [f for f in run_doctor(root) if f.code == "reserved-frontmatter"]
    assert found and found[0].level == "ERROR"
    assert found[0].path == "references/index.md"


def test_reserved_log_md_with_frontmatter_is_error(tmp_path):
    root = make_notebook(tmp_path)
    (root / "log.md").write_text("---\ntype: Log\n---\n# Update Log\n", encoding="utf-8")
    assert "reserved-frontmatter" in codes(run_doctor(root), "ERROR")


def test_generated_frontmatter_free_views_are_clean(tmp_path):
    root = make_notebook(tmp_path)
    (root / "references").mkdir()
    (root / "references" / "index.md").write_text("# References\n", encoding="utf-8")
    (root / "log.md").write_text("# Update Log\n", encoding="utf-8")
    assert run_doctor(root) == []  # root index.md frontmatter is the sanctioned one


# --- id integrity ----------------------------------------------------------------


def test_entity_page_without_id_is_error(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(root / "questions" / "noid.md", {"type": "Question"}, "why?\n")
    found = [f for f in run_doctor(root) if f.code == "missing-id"]
    assert found and found[0].level == "ERROR"
    assert found[0].path == "questions/noid.md"


def test_id_prefix_must_match_directory(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "claims" / "misfiled.md",
        {"type": "Claim", "id": "Q7", "aliases": ["Q7"], "status": "asserted"},
        "text\n",
    )
    found = [f for f in run_doctor(root) if f.code == "wrong-prefix"]
    assert found and found[0].level == "ERROR"
    assert "questions/" in found[0].message  # points at where Q# belongs


def test_malformed_id_is_error(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "decisions" / "odd.md",
        {"type": "Decision", "id": "d-one", "aliases": ["d-one"]},
        "text\n",
    )
    assert "bad-id" in codes(run_doctor(root), "ERROR")


def test_aliases_must_contain_the_id(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "questions" / "unaliased.md",
        {"type": "Question", "id": "Q1", "aliases": ["something-else"], "status": "open"},
        "why?\n",
    )
    found = [f for f in run_doctor(root) if f.code == "missing-alias"]
    assert found and found[0].level == "WARN"
    assert "[[Q1]]" in found[0].message


def test_duplicate_ids_across_pages_is_error(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1")
    fm = {"type": "Source", "id": "A1", "aliases": ["A1"], "title": "again"}
    pages.write_page(root / "references" / "again.md", fm, "# again\n")
    found = [f for f in run_doctor(root) if f.code == "duplicate-id"]
    assert found and found[0].level == "ERROR"
    assert "A1" in found[0].message


def test_duplicate_h_id_in_analysis_is_error(tmp_path):
    # H# hypothesis pages live under analysis/ (SPEC §9); their ids join the
    # notebook-wide duplicate check like any other entity id
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "analysis" / "hypotheses.md",
        {"type": "Hypothesis", "id": "H1", "aliases": ["H1"]},
        "# H1: the dip is real\n",
    )
    pages.write_page(
        root / "analysis" / "rival.md",
        {"type": "Hypothesis", "id": "H1", "aliases": ["H1"]},
        "# H1 again\n",
    )
    found = [f for f in run_doctor(root) if f.code == "duplicate-id"]
    assert found and found[0].level == "ERROR"
    assert "H1" in found[0].message


def test_analysis_pages_need_no_id(tmp_path):
    # analysis/ holds concept pages: graduated prose without ids stays legal
    root = make_notebook(tmp_path)
    pages.write_page(root / "analysis" / "findings.md", {"type": "Finding"}, "# ok\n")
    findings = run_doctor(root)
    assert "missing-id" not in codes(findings)
    assert findings == []


def test_scalar_alias_is_accepted(tmp_path):
    # `aliases: Q1` (a YAML scalar) is one alias, not a missing list
    root = make_notebook(tmp_path)
    (root / "questions").mkdir()
    (root / "questions" / "scalar.md").write_text(
        "---\ntype: Question\nid: Q1\naliases: Q1\nstatus: open\n---\n\nwhy?\n",
        encoding="utf-8",
    )
    assert "missing-alias" not in codes(run_doctor(root))


def test_claim_scalar_sources_not_char_split(tmp_path):
    # a hand-edited `sources: A1` must count as the one source A1, not the
    # characters "A" and "1" (which would recompute corroboration as 0)
    root = make_notebook(tmp_path, min_independent=1)
    source_page(root, "A1", grade="B", independence="original")
    (root / "claims").mkdir()
    (root / "claims" / "hand.md").write_text(
        "---\ntype: Claim\nid: C1\naliases: [C1]\nstatus: asserted\n"
        "sources: A1\nindependent_corroboration: 1\n---\n\ntext\n",
        encoding="utf-8",
    )
    assert "corroboration-drift" not in codes(run_doctor(root))


def test_sessions_have_no_id_scheme(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "sessions" / "2026-07-09T1000-sweep.md",
        {"type": "Work Session", "actor": "agent:claude", "started": "2026-07-09T10:00:00Z"},
        "## Goal\n",
    )
    findings = run_doctor(root)
    assert "missing-id" not in codes(findings)
    assert findings == []


# --- link rot ---------------------------------------------------------------------


def test_dangling_citation_is_warn(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1")
    claim_page(
        root,
        "C1",
        sources=["A1"],
        corroboration=1,
        body=(
            "claim C1\n\n# Citations\n"
            "[1] [here](../references/a1-page.md)\n"
            "[2] [gone](../references/gone.md)\n"
            "[3] [web](https://example.com/page.md)\n"
        ),
    )
    dangling = [f for f in run_doctor(root) if f.code == "dangling-citation"]
    assert len(dangling) == 1
    assert dangling[0].level == "WARN"
    assert "gone.md" in dangling[0].message
    assert dangling[0].path == "claims/c1-claim.md"


def test_link_rot_handles_fragments_bundle_paths_and_outside_links(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1")
    claim_page(
        root,
        "C1",
        sources=["A1"],
        corroboration=1,
        body=(
            "claim C1\n\n"
            "[anchored](../references/a1-page.md#quote)\n"
            "[bundle-absolute](/references/a1-page.md)\n"
            "[outside](../../elsewhere.md)\n"
        ),
    )
    assert "dangling-citation" not in codes(run_doctor(root))


# --- corroboration drift -----------------------------------------------------------


def test_corroboration_drift_is_warn_with_refresh_hint(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="original")
    claim_page(root, "C1", status="needs-2nd", sources=["A1"], corroboration=0)  # stale: now 1
    drift = [f for f in run_doctor(root) if f.code == "corroboration-drift"]
    assert drift and drift[0].level == "WARN"
    assert "flip claim status" in drift[0].message
    assert drift[0].path == "claims/c1-claim.md"


def test_no_drift_when_stored_count_matches(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="original")
    claim_page(root, "C1", status="needs-2nd", sources=["A1"], corroboration=1)
    assert "corroboration-drift" not in codes(run_doctor(root))


# --- under-verified claims ----------------------------------------------------------


def test_under_verified_recomputes_and_ignores_stored_count(tmp_path):
    root = make_notebook(tmp_path, min_independent=2)
    source_page(root, "A1", grade="B", independence="republisher")
    # stored count lies (says 5); recomputation sees 0 original sources
    claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1"], corroboration=5)
    under = [f for f in run_doctor(root) if f.code == "under-verified"]
    assert under and under[0].level == "ERROR"
    assert under[0].path == "claims/c1-claim.md"


def test_grade_a_primary_satisfies_the_bar(tmp_path):
    root = make_notebook(tmp_path, min_independent=2)
    source_page(root, "A1", grade="A", independence="republisher")
    claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1"])
    assert "under-verified" not in codes(run_doctor(root))


def test_enough_original_sources_satisfy_the_bar(tmp_path):
    root = make_notebook(tmp_path, min_independent=2)
    source_page(root, "A1")
    source_page(root, "A2")
    claim_page(
        root, "C1", status="verified", load_bearing=True, sources=["A1", "A2"], corroboration=2
    )
    assert "under-verified" not in codes(run_doctor(root))


def test_profile_can_disable_grade_a_shortcut(tmp_path):
    root = make_notebook(tmp_path, min_independent=2, grade_a_suffices=False)
    source_page(root, "A1", grade="A", independence="republisher")
    claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1"])
    assert "under-verified" in codes(run_doctor(root), "ERROR")


def test_under_verified_dedupes_duplicate_source_ids(tmp_path):
    # The same source listed twice must count once, not clear a bar of 2.
    root = make_notebook(tmp_path, min_independent=2)
    source_page(root, "A1", grade="B", independence="original")
    claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1", "A1"])
    under = [f for f in run_doctor(root) if f.code == "under-verified"]
    assert under and under[0].level == "ERROR"
    assert "1 independent" in under[0].message


def test_under_verified_ignores_ungraded_sources(tmp_path):
    # Two originals, but one still graded "?": capture-time defaults must not
    # satisfy the bar (SPEC §5.4 — ungraded sources never corroborate).
    root = make_notebook(tmp_path, min_independent=2)
    source_page(root, "A1", grade="B", independence="original")
    source_page(root, "A2", grade="?", independence="original")
    claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1", "A2"])
    assert "under-verified" in codes(run_doctor(root), "ERROR")


def test_load_bearing_asserted_claim_is_warn(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", status="asserted", load_bearing=True)
    warns = [f for f in run_doctor(root) if f.code == "unaudited-claim"]
    assert warns and warns[0].level == "WARN"


def test_non_load_bearing_asserted_claim_is_fine(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", status="asserted", load_bearing=False)
    assert "unaudited-claim" not in codes(run_doctor(root))


def test_invalid_claim_status_is_error(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", status="maybe")
    bad = [f for f in run_doctor(root) if f.code == "bad-enum"]
    assert bad and bad[0].level == "ERROR"
    assert bad[0].path == "claims/c1-claim.md"


# --- custody: pages ↔ raw bytes ↔ provenance ------------------------------------------


def test_orphan_custody_when_local_file_missing(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", raw=False)  # page + provenance, but no raw bytes
    orphans = [f for f in run_doctor(root) if f.code == "orphan-custody"]
    assert orphans and orphans[0].level == "ERROR"
    assert orphans[0].path == "sources/raw/A1.html"


def test_unlogged_capture_when_no_provenance_event(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", prov=False)
    findings = run_doctor(root)
    assert "unlogged-capture" in codes(findings, "WARN")
    # the raw file is also unregistered (no provenance at all)
    assert "unregistered-raw" in codes(findings, "WARN")


def test_orphan_provenance_when_page_is_gone(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1")
    append_jsonl(
        root / "sources" / "_provenance.jsonl", prov_event("A9", "sources/raw/A9.html")
    )
    found = [f for f in run_doctor(root) if f.code == "orphan-provenance"]
    assert found and found[0].level == "WARN"
    assert "A9" in found[0].message


def test_unregistered_raw_tolerates_directory_captures(tmp_path):
    root = make_notebook(tmp_path)
    capture_dir = root / "sources" / "raw" / "A2"
    capture_dir.mkdir(parents=True)
    (capture_dir / "page.html").write_text("x", encoding="utf-8")
    (root / "sources" / "raw" / "A9.pdf").write_bytes(b"x")
    append_jsonl(root / "sources" / "_provenance.jsonl", prov_event("A2", "sources/raw/A2"))
    warns = [f for f in run_doctor(root) if f.code == "unregistered-raw"]
    assert [f.path for f in warns] == ["sources/raw/A9.pdf"]


def test_bad_source_enums_are_errors(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="Z", independence="hearsay", freshness="moldy")
    bad = [f for f in run_doctor(root) if f.code == "bad-enum"]
    assert len(bad) == 3
    assert all(f.level == "ERROR" for f in bad)
    assert all(f.path == "references/a1-page.md" for f in bad)


def test_bad_jsonl_is_finding_not_crash(tmp_path):
    root = make_notebook(tmp_path)
    prov = root / "sources" / "_provenance.jsonl"
    prov.parent.mkdir(parents=True)
    prov.write_text("{broken\n", encoding="utf-8")
    (root / "log").mkdir()
    (root / "log" / "log.jsonl").write_text("also broken\n", encoding="utf-8")
    bad = [f for f in run_doctor(root) if f.code == "bad-jsonl"]
    assert {f.path for f in bad} == {"sources/_provenance.jsonl", "log/log.jsonl"}
    assert all(f.level == "ERROR" for f in bad)


# --- stale freshness ----------------------------------------------------------


def test_stale_freshness_warns_on_old_but_fresh_source(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", date="2020-01-01", freshness="fresh")  # far past 18 months
    stale = [f for f in run_doctor(root) if f.code == "stale-freshness"]
    assert stale and stale[0].level == "WARN"
    assert "A1" in stale[0].message and "flip grade" in stale[0].message


def test_stale_freshness_silent_for_recent_dated_or_undated(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", date=today(), freshness="fresh")  # fresh and recent
    source_page(root, "A2", date="2020-01-01", freshness="dated")  # already re-judged
    source_page(root, "A3")  # no date at all
    assert "stale-freshness" not in codes(run_doctor(root))


def test_findings_are_json_serializable(tmp_path):
    # the CLI emits findings via --json; dataclass fields must stay plain
    root = make_notebook(tmp_path)
    claim_page(root, "C1", status="maybe")
    from dataclasses import asdict

    payload = json.dumps([asdict(f) for f in run_doctor(root)])
    assert "bad-enum" in payload


# --- beat back-link (SPEC §14) --------------------------------------------------


def make_beat_with_notebook(tmp_path: Path, link: str = "county#TH1") -> Path:
    """A beat at tmp_path with one thread, and a hand-built notebook under it
    carrying links.beat — the shape `flip beat graduate` leaves behind."""
    from flip import beat

    beat.create_beat(tmp_path, "county", mission="cover it")
    beat.add_thread(tmp_path, "an angle", "arc")
    extra = f"links:\n  beat: {link}\n"
    return make_notebook(tmp_path, extra_fm=extra)


def test_beat_link_resolving_above_is_silent(tmp_path):
    root = make_beat_with_notebook(tmp_path)
    assert "broken-beat-link" not in codes(run_doctor(root))


def test_beat_link_without_beat_above_warns(tmp_path):
    root = make_notebook(tmp_path, extra_fm="links:\n  beat: county#TH1\n")
    broken = [f for f in run_doctor(root) if f.code == "broken-beat-link"]
    assert broken and broken[0].level == "WARN"
    assert "county#TH1" in broken[0].message
    assert "no beat root" in broken[0].message


def test_beat_link_slug_mismatch_warns(tmp_path):
    root = make_beat_with_notebook(tmp_path, link="other-beat#TH1")
    broken = [f for f in run_doctor(root) if f.code == "broken-beat-link"]
    assert broken and broken[0].level == "WARN"
    assert "'other-beat'" in broken[0].message and "'county'" in broken[0].message


def test_beat_link_missing_thread_warns(tmp_path):
    root = make_beat_with_notebook(tmp_path, link="county#TH9")
    broken = [f for f in run_doctor(root) if f.code == "broken-beat-link"]
    assert broken and broken[0].level == "WARN"
    assert "TH9" in broken[0].message


def test_no_links_beat_no_beat_checks(tmp_path):
    root = make_notebook(tmp_path)
    assert "broken-beat-link" not in codes(run_doctor(root))
