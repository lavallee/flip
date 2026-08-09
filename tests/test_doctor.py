"""Tests for flip.doctor — notebook linting against SPEC v0.4 (§15).

Fixtures are hand-built notebooks: index.md manifest, a notebook-local
profile under .flip/profiles/ (so shipped profile data can evolve without
breaking these tests), entity pages written through the pages layer, and
raw/provenance custody where a check needs it.
"""

import json
from pathlib import Path

from flip import pages
from flip.doctor import Finding, run_doctor, run_workspace_doctor
from flip.manifest import load_manifest
from flip.util import UID_RE, append_jsonl, today
from flip.workspace import load_workspace

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "{flip}"
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
    flip_version: str = "0.4",
    **profile_kw,
) -> Path:
    root = tmp_path / "nb"
    root.mkdir(exist_ok=True)
    (root / "index.md").write_text(
        MANIFEST_MD.format(kind=kind, status=status, extra=extra_fm, flip=flip_version),
        encoding="utf-8",
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
    independence: str = "independent",
    freshness: str = "fresh",
    date: str | None = None,
    raw: bool = True,
    prov: bool = True,
    support: dict | None = None,
) -> Path:
    """A captured source: references/ page + raw bytes + provenance event.

    `independence` defaults to the current (0.8+) vocabulary; pass `support`
    (a dict merged onto the page's `support` tuple, e.g. {"basis": ...,
    "method": ...}) when a test needs the stored `grade` to match what
    `derive_grade` recomputes from the tuple (no grade-drift)."""
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
    if support:
        fm["support"] = support
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
        "sources": [{"id": sid} for sid in (sources or [])],
        "independent_corroboration": corroboration,
        "first_asserted": "2026-07-09",
        "generated": {"by": "human:test", "at": "2026-07-09T14:31:02Z"},
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
    # independent + a strong-enough basis/method so the stored grade "B"
    # matches what derive_grade recomputes from the support tuple (no drift).
    source_page(
        root, "A1", grade="B", independence="independent",
        support={"basis": "survey", "method": "cross-check"},
    )
    claim_page(root, "C1", status="needs-2nd", sources=["A1"], corroboration=1)
    findings = run_doctor(root)
    # Nothing is WRONG with this notebook. The one notice it does draw is the
    # appears-with-use kind: a document is in custody and has no readable
    # derivative yet, which is a true statement about a notebook nobody has run
    # `flip extract` in. Asserting `== []` here would have forced that check to
    # be gated on machine configuration to stay quiet, and doctor's output must
    # not depend on what happens to be installed.
    assert [f for f in findings if not f.expected] == []
    assert codes(findings) == ["missing-derivative"]


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
        # E3: appears-with-use notices are flagged expected so the CLI can
        # segregate them from real findings.
        assert all(f.expected for f in missing), status


def test_missing_required_paths_error_once_closed(tmp_path):
    for status in ("done", "published", "archived"):
        root = make_notebook(
            tmp_path, status=status, requires=("references", "log/passed.jsonl")
        )
        missing = [f for f in run_doctor(root) if f.code == "missing-required"]
        assert {f.path for f in missing} == {"references", "log/passed.jsonl"}, status
        assert all(f.level == "ERROR" for f in missing), status
        assert all(status in f.message for f in missing), status
        # once due, these are real ERRORs, never "expected until use"
        assert not any(f.expected for f in missing), status


def test_pursuit_profile_minimums(tmp_path, monkeypatch):
    # Lane B: the shipped pursuit profile requires questions/, claims/,
    # drafts/question-plan.md, log — WARN while active (D13), ERROR once done.
    from flip.manifest import save_manifest
    from flip.scaffold import create_notebook

    monkeypatch.setenv("FLIP_ACTOR", "agent:test")
    root = create_notebook(tmp_path / "q", "q", "pursuit", title="the question")
    required = {"questions", "claims", "drafts/question-plan.md", "log"}
    findings = run_doctor(root)
    missing = [f for f in findings if f.code == "missing-required"]
    # questions/ and drafts/question-plan.md are seeded; claims/ and log appear
    # with use — those are the only ones outstanding, and only at WARN.
    assert {f.path for f in missing} <= required
    assert all(f.level == "WARN" for f in missing)
    assert not codes(findings, "ERROR")

    m = load_manifest(root)
    m.status = "done"
    save_manifest(root, m)
    missing_done = [f for f in run_doctor(root) if f.code == "missing-required"]
    assert missing_done and all(f.level == "ERROR" for f in missing_done)


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
    source_page(root, "A1", grade="B", independence="independent")
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
    source_page(root, "A1", grade="B", independence="independent")
    claim_page(root, "C1", status="needs-2nd", sources=["A1"], corroboration=0)  # stale: now 1
    drift = [f for f in run_doctor(root) if f.code == "corroboration-drift"]
    assert drift and drift[0].level == "WARN"
    assert "flip claim status" in drift[0].message
    assert drift[0].path == "claims/c1-claim.md"


def test_no_drift_when_stored_count_matches(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
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
    # A single grade-A primary (independent + a strong basis, so derive_grade
    # actually recomputes "A") clears the verified bar via the grade-A
    # shortcut even though its lone corroboration count (1) falls short of
    # the profile's min_independent (2).
    root = make_notebook(tmp_path, min_independent=2)
    source_page(
        root, "A1", grade="A", independence="independent",
        support={"basis": "official-record"},
    )
    claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1"])
    assert "under-verified" not in codes(run_doctor(root))


def test_enough_independent_sources_satisfy_the_bar(tmp_path):
    root = make_notebook(tmp_path, min_independent=2)
    source_page(root, "A1", independence="independent")
    source_page(root, "A2", independence="independent")
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
    source_page(root, "A1", grade="B", independence="independent")
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


def test_under_verified_cleared_by_adversarial_record(tmp_path):
    # A2: a recorded adversarial/recomputation check clears the verified gate
    # even below the corroboration bar — the doctor mirror of set_claim_status.
    root = make_notebook(tmp_path, min_independent=2)
    source_page(root, "A1", grade="B", independence="republisher")  # 0 original
    path = claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1"])
    page = pages.read_page(path)
    page.fm["verified"] = [{"method": "adversarial", "by": "agent:test",
                            "at": f"{today()}T14:31:02Z"}]
    pages.write_page(path, page.fm, page.body)
    assert "under-verified" not in codes(run_doctor(root))


def test_load_bearing_asserted_claim_is_warn(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", status="asserted", load_bearing=True)
    warns = [f for f in run_doctor(root) if f.code == "unaudited-claim"]
    assert warns and warns[0].level == "WARN"


def test_non_load_bearing_asserted_claim_is_fine(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", status="asserted", load_bearing=False)
    assert "unaudited-claim" not in codes(run_doctor(root))


def test_asserted_claim_with_corroboration_is_not_unaudited(tmp_path):
    # A2: unaudited-claim ends the permanent nag — a load-bearing asserted
    # claim that has *some* corroboration no longer warns.
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    claim_page(root, "C1", status="asserted", load_bearing=True, sources=["A1"])
    assert "unaudited-claim" not in codes(run_doctor(root))


def test_asserted_claim_with_verification_record_is_not_unaudited(tmp_path):
    # neither corroboration nor a source, but a recorded check silences the nag
    root = make_notebook(tmp_path)
    path = claim_page(root, "C1", status="asserted", load_bearing=True)
    page = pages.read_page(path)
    page.fm["verified"] = [{"method": "adversarial", "by": "agent:test",
                            "at": f"{today()}T14:31:02Z"}]
    pages.write_page(path, page.fm, page.body)
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


# --- ref separator deprecation (SPEC §9: '#' → ':', reads removed in 0.10) -------


def test_beat_link_colon_is_canonical_and_silent(tmp_path):
    root = make_beat_with_notebook(tmp_path, link="county:TH1")
    found = codes(run_doctor(root))
    assert "broken-beat-link" not in found
    assert "deprecated-ref-separator" not in found


def test_beat_link_hash_warns_deprecated(tmp_path):
    root = make_beat_with_notebook(tmp_path, link="county#TH1")
    warns = [f for f in run_doctor(root) if f.code == "deprecated-ref-separator"]
    assert warns and warns[0].level == "WARN"
    assert "flip migrate" in warns[0].message
    assert "0.10" in warns[0].message
    # the link still resolves through the fallback parse
    assert "broken-beat-link" not in codes(run_doctor(root))


def test_beat_link_colon_missing_thread_still_warns(tmp_path):
    root = make_beat_with_notebook(tmp_path, link="county:TH9")
    broken = [f for f in run_doctor(root) if f.code == "broken-beat-link"]
    assert broken and "TH9" in broken[0].message


# --- missing-alias wording (aliases are autocomplete, not resolution) -------------


def test_missing_alias_explains_autocomplete_not_resolution(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "questions" / "unaliased.md",
        {"type": "Question", "id": "Q1", "aliases": ["something-else"], "status": "open"},
        "why?\n",
    )
    found = [f for f in run_doctor(root) if f.code == "missing-alias"]
    assert found
    assert "autocomplete" in found[0].message
    assert "add aliases: [Q1]" in found[0].message


# --- missing-uid, gated on the declared profile version (SPEC §4) -----------------


def test_missing_uid_fires_when_manifest_declares_05(tmp_path):
    root = make_notebook(tmp_path, flip_version="0.5")
    found = [f for f in run_doctor(root) if f.code == "missing-uid"]
    assert found and found[0].level == "WARN"
    assert "flip migrate" in found[0].message
    assert found[0].path == "index.md"


def test_missing_uid_quiet_on_unmigrated_04(tmp_path):
    root = make_notebook(tmp_path, flip_version="0.4")
    assert "missing-uid" not in codes(run_doctor(root))


def test_no_missing_uid_when_uid_present(tmp_path):
    root = make_notebook(tmp_path, flip_version="0.5", extra_fm="uid: nb-7k3m9p2x\n")
    assert "missing-uid" not in codes(run_doctor(root))


# --- workspace mode (SPEC §18) -----------------------------------------------------

WS_NB_MD = """\
---
okf_version: "0.1"
flip: "0.5"
slug: {slug}
{extra}kind: ledger
status: active
created: 2026-07-01
updated: 2026-07-09
---
# {slug}
"""


def make_workspace(tmp_path: Path) -> Path:
    ws_root = tmp_path / "ws"
    ws_root.mkdir(exist_ok=True)
    return ws_root


def ws_notebook(ws_root: Path, rel: str, slug: str | None = None, uid: str = "") -> Path:
    """A minimal bindable notebook at ws_root/rel."""
    root = ws_root / rel
    root.mkdir(parents=True, exist_ok=True)
    extra = f"uid: {uid}\n" if uid else ""
    (root / "index.md").write_text(
        WS_NB_MD.format(slug=slug or rel, extra=extra), encoding="utf-8"
    )
    return root


def question(root: Path, qid: str, aliases: list[str] | None = None, stem: str | None = None):
    return pages.write_page(
        root / "questions" / f"{stem or qid.lower()}.md",
        {"type": "Question", "id": qid,
         "aliases": aliases if aliases is not None else [qid], "status": "open"},
        "why?\n",
    )


def write_table(ws_root: Path, notebooks: dict[str, str], version: str = "0.1") -> None:
    lines = [f'[workspace]\nversion = "{version}"\n\n[notebooks]\n']
    lines += [f'{h} = "{p}"\n' for h, p in notebooks.items()]
    (ws_root / ".flip").mkdir(parents=True, exist_ok=True)
    (ws_root / ".flip" / "workspace.toml").write_text("".join(lines), encoding="utf-8")


def test_healthy_workspace_has_no_findings(tmp_path):
    ws = make_workspace(tmp_path)
    recipes = ws_notebook(ws, "recipes", uid="nb-r2k9m3p7")
    gardening = ws_notebook(ws, "gardening", uid="nb-g2k9m3p7")
    question(recipes, "Q1", aliases=["Q1", "recipes:Q1"])
    question(gardening, "Q2", aliases=["Q2", "gardening:Q2"], stem="soil-ph")
    write_table(ws, {"recipes": "recipes", "gardening": "gardening"})
    assert run_workspace_doctor(ws) == []


def test_bad_workspace_file_is_error(tmp_path):
    ws = make_workspace(tmp_path)
    (ws / ".flip").mkdir()
    (ws / ".flip" / "workspace.toml").write_text("not [ toml\n", encoding="utf-8")
    findings = run_workspace_doctor(ws)
    assert codes(findings, "ERROR") == ["bad-workspace-file"]
    assert findings[0].path == ".flip/workspace.toml"


def test_duplicate_handle_is_bad_workspace_file(tmp_path):
    # duplicate TOML keys are a parse error, so a duplicated handle surfaces
    # as bad-workspace-file with tomllib's line-anchored message
    ws = make_workspace(tmp_path)
    (ws / ".flip").mkdir()
    (ws / ".flip" / "workspace.toml").write_text(
        '[workspace]\nversion = "0.1"\n\n[notebooks]\n'
        'recipes = "recipes"\nrecipes = "other"\n',
        encoding="utf-8",
    )
    findings = run_workspace_doctor(ws)
    assert codes(findings, "ERROR") == ["bad-workspace-file"]


def test_invalid_handle_is_handle_syntax_error(tmp_path):
    ws = make_workspace(tmp_path)
    ws_notebook(ws, "recipes")
    write_table(ws, {"Recipes": "recipes"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "handle-syntax"]
    assert found and found[0].level == "ERROR"
    assert "'Recipes'" in found[0].message


def test_dangling_entry_when_path_missing(tmp_path):
    ws = make_workspace(tmp_path)
    write_table(ws, {"recipes": "recipes"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "dangling-workspace-entry"]
    assert found and found[0].level == "ERROR"
    assert "does not exist" in found[0].message
    assert "flip ws rm recipes" in found[0].message


def test_dangling_entry_when_not_a_notebook(tmp_path):
    ws = make_workspace(tmp_path)
    (ws / "plain").mkdir()
    (ws / "plain" / "index.md").write_text("# just a directory\n", encoding="utf-8")
    write_table(ws, {"plain": "plain"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "dangling-workspace-entry"]
    assert found and "not a notebook root" in found[0].message


def test_duplicate_uid_is_single_warn_listing_handles(tmp_path):
    ws = make_workspace(tmp_path)
    ws_notebook(ws, "recipes", uid="nb-x2k9m3p7")
    ws_notebook(ws, "gardening", uid="nb-x2k9m3p7")
    write_table(ws, {"recipes": "recipes", "gardening": "gardening"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "duplicate-uid"]
    assert len(found) == 1 and found[0].level == "WARN"
    assert "recipes" in found[0].message and "gardening" in found[0].message
    assert "nb-x2k9m3p7" in found[0].message


def test_missing_uid_warn_with_ws_relative_path(tmp_path):
    ws = make_workspace(tmp_path)
    ws_notebook(ws, "recipes")  # no uid
    write_table(ws, {"recipes": "recipes"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "missing-uid"]
    assert found and found[0].level == "WARN"
    assert found[0].path == "recipes/index.md"
    assert "--fix" in found[0].message


def test_unregistered_notebook_warn(tmp_path):
    ws = make_workspace(tmp_path)
    ws_notebook(ws, "field-notes", uid="nb-f2k9m3p7")
    write_table(ws, {})
    found = [f for f in run_workspace_doctor(ws) if f.code == "unregistered-notebook"]
    assert found and found[0].level == "WARN"
    assert found[0].path == "field-notes"
    assert "flip ws add field-notes" in found[0].message


def test_ambiguous_id_is_one_finding_with_capped_examples(tmp_path):
    ws = make_workspace(tmp_path)
    recipes = ws_notebook(ws, "recipes", uid="nb-r2k9m3p7")
    gardening = ws_notebook(ws, "gardening", uid="nb-g2k9m3p7")
    for i in range(1, 8):  # Q1..Q7 live in both notebooks
        question(recipes, f"Q{i}", stem=f"q{i}-recipes")
        question(gardening, f"Q{i}", stem=f"q{i}-gardening")
    write_table(ws, {"recipes": "recipes", "gardening": "gardening"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "ambiguous-id"]
    assert len(found) == 1 and found[0].level == "WARN"
    assert "7 id(s)" in found[0].message
    assert "Q1 (gardening, recipes)" in found[0].message
    assert "Q6" not in found[0].message  # examples capped at 5
    assert "+2 more" in found[0].message


def test_slug_collision_is_one_aggregated_finding(tmp_path):
    ws = make_workspace(tmp_path)
    recipes = ws_notebook(ws, "recipes", uid="nb-r2k9m3p7")
    gardening = ws_notebook(ws, "gardening", uid="nb-g2k9m3p7")
    question(recipes, "Q1", stem="harvest-plan")
    question(gardening, "Q2", stem="harvest-plan")
    write_table(ws, {"recipes": "recipes", "gardening": "gardening"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "slug-collision"]
    assert len(found) == 1 and found[0].level == "WARN"
    assert "harvest-plan (gardening, recipes)" in found[0].message


def test_stale_alias_flags_wrong_handle_for_own_id(tmp_path):
    ws = make_workspace(tmp_path)
    recipes = ws_notebook(ws, "recipes", uid="nb-r2k9m3p7")
    # pantry:Q1 predates a rename; gardening:Q9 names a different id → foreign, kept
    question(recipes, "Q1", aliases=["Q1", "recipes:Q1", "pantry:Q1", "gardening:Q9"])
    write_table(ws, {"recipes": "recipes"})
    found = [f for f in run_workspace_doctor(ws) if f.code == "stale-alias"]
    assert len(found) == 1 and found[0].level == "WARN"
    assert "pantry:Q1" in found[0].message
    assert found[0].path == "recipes/questions/q1.md"


def test_stale_alias_ignores_nested_workspace_handles(tmp_path):
    # The same notebook bound by an outer AND an inner (nested) workspace
    # under different handles: each table's doctor must treat the other
    # table's handle as legitimate, not stale — stripping it would break the
    # other workspace's autocomplete and ping-pong under --fix forever.
    outer = make_workspace(tmp_path)
    nb = ws_notebook(outer, "inner/shared", slug="shared", uid="nb-s2k9m3p7")
    inner = outer / "inner"
    question(nb, "Q1", aliases=["Q1", "shared:Q1", "outershared:Q1", "pantry:Q1"])
    write_table(outer, {"outershared": "inner/shared"})
    write_table(inner, {"shared": "shared"})

    outer_stale = [f for f in run_workspace_doctor(outer) if f.code == "stale-alias"]
    assert len(outer_stale) == 1
    assert "pantry:Q1" in outer_stale[0].message  # truly stale: still flagged
    assert "shared:Q1" not in outer_stale[0].message  # the inner table's handle

    inner_stale = [f for f in run_workspace_doctor(inner) if f.code == "stale-alias"]
    assert len(inner_stale) == 1
    assert "pantry:Q1" in inner_stale[0].message
    assert "outershared:Q1" not in inner_stale[0].message  # the outer table's handle


def test_fix_does_not_ping_pong_across_nested_workspaces(tmp_path):
    outer = make_workspace(tmp_path)
    nb = ws_notebook(outer, "inner/shared", slug="shared", uid="nb-s2k9m3p7")
    inner = outer / "inner"
    question(nb, "Q1", aliases=["Q1", "shared:Q1", "outershared:Q1"])
    write_table(outer, {"outershared": "inner/shared"})
    write_table(inner, {"shared": "shared"})
    assert run_workspace_doctor(outer, fix=True) == []
    assert run_workspace_doctor(inner, fix=True) == []
    page = pages.read_page(nb / "questions" / "q1.md")
    assert page.fm["aliases"] == ["Q1", "shared:Q1", "outershared:Q1"]


# --- workspace --fix ---------------------------------------------------------------


def test_fix_binds_unregistered_notebook_with_suffix(tmp_path):
    ws = make_workspace(tmp_path)
    ws_notebook(ws, "recipes", uid="nb-r2k9m3p7")
    ws_notebook(ws, "orchard", slug="recipes", uid="nb-c2k9m3p7")  # slug collides
    write_table(ws, {"recipes": "recipes"})
    findings = run_workspace_doctor(ws, fix=True)
    unreg = [f for f in findings if f.code == "unregistered-notebook"]
    assert unreg and "recipes-2" in unreg[0].message
    assert load_workspace(ws).notebooks["recipes-2"] == "orchard"


def test_fix_backfills_uid_and_qualifies_aliases(tmp_path):
    ws = make_workspace(tmp_path)
    recipes = ws_notebook(ws, "recipes")  # no uid
    question(recipes, "Q1", aliases=["Q1", "old:Q1"])  # stale alias from a rename
    write_table(ws, {"recipes": "recipes"})
    findings = run_workspace_doctor(ws, fix=True)
    assert "missing-uid" in codes(findings)
    assert "stale-alias" in codes(findings)
    assert UID_RE.match(load_manifest(recipes).uid)
    page = pages.read_page(recipes / "questions" / "q1.md")
    assert page.fm["aliases"] == ["Q1", "recipes:Q1"]


def test_fix_is_idempotent(tmp_path):
    ws = make_workspace(tmp_path)
    recipes = ws_notebook(ws, "recipes")  # no uid
    question(recipes, "Q1", aliases=["Q1", "old:Q1"])
    ws_notebook(ws, "orchard", slug="orchard-survey", uid="nb-c2k9m3p7")
    write_table(ws, {"recipes": "recipes"})
    assert run_workspace_doctor(ws, fix=True) != []
    watched = [
        ws / ".flip" / "workspace.toml",
        recipes / "index.md",
        recipes / "questions" / "q1.md",
        ws / "orchard" / "index.md",
    ]
    snapshot = [p.read_bytes() for p in watched]
    assert run_workspace_doctor(ws, fix=True) == []
    assert [p.read_bytes() for p in watched] == snapshot


def test_fix_never_rewrites_a_table_with_invalid_handles(tmp_path):
    # binding fixes write workspace.toml; a handle-syntax ERROR blocks that
    ws = make_workspace(tmp_path)
    ws_notebook(ws, "recipes", uid="nb-r2k9m3p7")
    ws_notebook(ws, "orchard", slug="orchard-survey", uid="nb-c2k9m3p7")
    write_table(ws, {"Recipes": "recipes"})
    before = (ws / ".flip" / "workspace.toml").read_bytes()
    findings = run_workspace_doctor(ws, fix=True)
    assert "handle-syntax" in codes(findings, "ERROR")
    unreg = [f for f in findings if f.code == "unregistered-notebook"]
    assert unreg and "flip ws add orchard" in unreg[0].message  # suggestion, not bound
    assert (ws / ".flip" / "workspace.toml").read_bytes() == before


# --- one cause, many symptoms ---------------------------------------------------


def test_vocabulary_drift_leads_with_the_cause(tmp_path):
    # 272 warnings and 4 errors once had ONE root cause, every warning on its
    # own line, and the errors looked like an evidence problem when they were a
    # vocabulary problem. The cause line comes first and names both sides.
    root = make_notebook(tmp_path)
    for sid in ("A1", "A2", "A3"):
        source_page(root, sid, grade="A", independence="original")
    claim_page(root, "C1", sources=["A1", "A2"])
    claim_page(root, "C2", sources=["A3"])
    findings = run_doctor(root)
    assert findings[0].code == "vocabulary-drift"
    msg = findings[0].message
    assert "3 source(s) carry pre-0.8 independence vocabulary" in msg
    assert "2 claim(s) (C1, C2)" in msg
    assert "flip migrate" in msg
    # the per-source symptoms still carry their paths for anything scripted
    assert codes(findings).count("pre-08-vocabulary") == 3


def test_no_cause_line_when_the_vocabulary_is_current(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent",
                support={"basis": "survey", "method": "read it"})
    assert "vocabulary-drift" not in codes(run_doctor(root))


def test_parked_source_is_told_to_re_judge_not_to_migrate(tmp_path):
    # `flip migrate` cannot translate 'original' — it only parks it — so
    # telling a parked page's owner to migrate is advice that does nothing.
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="?", independence="original",
                support={"pre_08_grade": "A"})
    stale = [f for f in run_doctor(root) if f.code == "pre-08-vocabulary"]
    assert len(stale) == 1
    assert "no migration can translate it" in stale[0].message
    assert "the pre-0.8 letter was A" in stale[0].message
    assert "flip grade A1" in stale[0].message


def test_under_verified_says_the_count_is_not_a_verdict(tmp_path):
    root = make_notebook(tmp_path, min_independent=1, grade_a_suffices=False)
    source_page(root, "A1", grade="A", independence="original")
    claim_page(root, "C1", status="verified", load_bearing=True, sources=["A1"])
    under = [f for f in run_doctor(root) if f.code == "under-verified"]
    assert len(under) == 1
    assert "could not be counted either way" in under[0].message
    assert "understates the evidence" in under[0].message


# --- a recorded failure is a finding, not corruption ----------------------------


def test_failed_capture_row_is_not_an_orphan(tmp_path):
    # A fetch failure allocates an id and writes a `status: failed` provenance
    # row with no page — deliberately, so "searched, gone" stays distinguishable
    # from "did not look". orphan-provenance used to nag about it forever, with
    # hand-editing JSONL as the only way to silence it.
    root = make_notebook(tmp_path)
    append_jsonl(
        root / "sources" / "_provenance.jsonl",
        {"ts": "2026-07-09T14:31:02Z", "source_id": "A7",
         "url": "https://example.com/gone", "status": "failed",
         "error": "HTTP 404", "actor": "agent:test"},
    )
    assert "orphan-provenance" not in codes(run_doctor(root))


def test_an_empty_handed_capture_row_is_not_an_orphan_either(tmp_path):
    # `not-captured` is the third state: the tool ran fine and the document was
    # not there. Like `failed` it has an id and no page BY DESIGN — the row is
    # the finding — so doctor must not read it as a missing page.
    root = make_notebook(tmp_path)
    append_jsonl(
        root / "sources" / "_provenance.jsonl",
        {"ts": "2026-07-09T14:31:02Z", "source_id": "P3",
         "url": "10.1017/S0140525X04000056", "status": "not-captured",
         "tool": "papertool", "finding": "ran clean and brought nothing back",
         "actor": "agent:test"},
    )
    got = codes(run_doctor(root))
    assert "orphan-provenance" not in got
    assert "thin-capture" not in got  # no bytes landed, so there is no fidelity


def test_a_real_orphan_is_still_reported(tmp_path):
    root = make_notebook(tmp_path)
    append_jsonl(root / "sources" / "_provenance.jsonl", prov_event("A7", "sources/raw/A7.html"))
    assert "orphan-provenance" in codes(run_doctor(root))


# --- a recomputation nobody can locate ------------------------------------------


def test_recomputation_without_against_is_flagged(tmp_path):
    root = make_notebook(tmp_path)
    path = claim_page(root, "C1", sources=[])
    fm = pages.read_page(path).fm
    fm["verified"] = [{"by": "agent:test", "at": "2026-07-30T10:00:00Z",
                       "method": "recomputation"}]
    pages.write_page(path, fm, "claim C1\n")
    flagged = [f for f in run_doctor(root) if f.code == "unlocatable-recomputation"]
    assert len(flagged) == 1
    assert "session id, script path, or derivation record" in flagged[0].message


def test_recomputation_with_against_is_clean(tmp_path):
    root = make_notebook(tmp_path)
    path = claim_page(root, "C1", sources=[])
    fm = pages.read_page(path).fm
    fm["verified"] = [{"by": "agent:test", "at": "2026-07-30T10:00:00Z",
                       "method": "recomputation",
                       "against": ["sessions/2026-07-30-recompute.md"]}]
    pages.write_page(path, fm, "claim C1\n")
    assert "unlocatable-recomputation" not in codes(run_doctor(root))


# --- capture fidelity: what the capture actually achieved (SPEC §5.1) -----------


def capture_event(sid: str, strategy: str, size: int, mime: str = "text/html") -> dict:
    return {
        "ts": "2026-07-31T10:00:00Z", "source_id": sid,
        "local_path": f"sources/raw/{sid}.html", "sha256": "0" * 64,
        "bytes": size, "mime": mime, "tool": "some-tool", "strategy": strategy,
        "actor": "agent:test",
    }


def test_thin_capture_is_named(tmp_path):
    # 800 bytes of markup is a consent wall or a JS shell, not the document —
    # and it produces the same sha256, ledger row and grade "?" as a real one.
    root = make_notebook(tmp_path)
    source_page(root, "A1", prov=False)
    append_jsonl(root / "sources" / "_provenance.jsonl", capture_event("A1", "http-get", 800))
    thin = [f for f in run_doctor(root) if f.code == "thin-capture"]
    assert len(thin) == 1
    assert "800 bytes" in thin[0].message
    assert "climb the ladder" in thin[0].message


def test_a_record_capture_is_named_as_what_it_is(tmp_path):
    """A record capture is thin by construction and thin on purpose — someone
    said out loud that the document was out of reach. Doctor still names it,
    because a record must never quietly read as the thing it stands for, but
    the wording is a description rather than an accusation and it sits under
    "expected until use" instead of reading as breakage."""
    root = make_notebook(tmp_path)
    source_page(root, "P1", prov=False)
    ev = capture_event("P1", "record-only", 280, mime="application/json")
    append_jsonl(root / "sources" / "_provenance.jsonl", ev)
    thin = [f for f in run_doctor(root) if f.code == "thin-capture"]
    assert len(thin) == 1
    assert "record capture" in thin[0].message
    assert "corroborates nothing" in thin[0].message
    assert "flip pass" in thin[0].message
    assert thin[0].expected is True
    assert "bytes of markup" not in thin[0].message  # not the consent-wall text


def test_a_real_capture_is_not_flagged(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", prov=False)
    append_jsonl(root / "sources" / "_provenance.jsonl", capture_event("A1", "http-get", 40_000))
    assert "thin-capture" not in codes(run_doctor(root))


def test_a_later_real_capture_supersedes_an_early_thin_one(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", prov=False)
    append_jsonl(root / "sources" / "_provenance.jsonl", capture_event("A1", "http-get", 800))
    append_jsonl(root / "sources" / "_provenance.jsonl",
                 capture_event("A1", "self-contained-archive", 900_000))
    assert "thin-capture" not in codes(run_doctor(root))  # history, not a finding


def test_a_tool_name_in_strategy_is_flagged_as_unvocabularied(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", prov=False)
    append_jsonl(root / "sources" / "_provenance.jsonl", capture_event("A1", "flip-fetch", 40_000))
    found = [f for f in run_doctor(root) if f.code == "unvocabularied-method"]
    assert len(found) == 1
    assert "reads like a tool name" in found[0].message
    assert found[0].expected is True  # legacy rows shouldn't read as breakage


def test_failed_capture_rows_are_not_judged_for_fidelity(tmp_path):
    root = make_notebook(tmp_path)
    append_jsonl(
        root / "sources" / "_provenance.jsonl",
        {"ts": "2026-07-31T10:00:00Z", "source_id": "A9", "status": "failed",
         "error": "HTTP 403", "actor": "agent:test"},
    )
    got = codes(run_doctor(root))
    assert "thin-capture" not in got and "unvocabularied-method" not in got


def test_the_envelope_sidecar_is_not_judged_as_a_capture(tmp_path):
    # A multi-file capture writes a row per file. flip.json is metadata and
    # always tiny — judging it reported every enveloped capture as thin.
    root = make_notebook(tmp_path)
    source_page(root, "A1", prov=False)
    real = capture_event("A1", "http-get", 165_231)
    real["local_path"] = "sources/raw/A1/capture.html"
    sidecar = capture_event("A1", "http-get", 221, mime="application/json")
    sidecar["local_path"] = "sources/raw/A1/flip.json"
    for ev in (real, sidecar):
        append_jsonl(root / "sources" / "_provenance.jsonl", ev)
    assert "thin-capture" not in codes(run_doctor(root))


def test_the_largest_file_of_one_capture_is_the_one_judged(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", prov=False)
    for name, size in (("thumb.html", 400), ("capture.html", 90_000)):
        ev = capture_event("A1", "http-get", size)
        ev["local_path"] = f"sources/raw/A1/{name}"
        append_jsonl(root / "sources" / "_provenance.jsonl", ev)
    assert "thin-capture" not in codes(run_doctor(root))


def test_unaudited_claim_sees_a_recorded_test(tmp_path):
    """A severe test IS an audit, and reading only corroboration missed it.

    On a real notebook this fired on a claim carrying a severe attribution test
    and told its author to "record a check" — which they had, moments earlier,
    with the command the message did not mention. What the test FOUND is not
    this check's business; silence here is the absence of the thing it is about,
    not approval.
    """
    from flip import claims as claims_mod

    root = make_notebook(tmp_path)
    claims_mod.add_claim(root, "a load-bearing claim", [], load_bearing=True)
    assert "unaudited-claim" in codes(run_doctor(root))

    claims_mod.record_test(
        root, "C1", probe="attribution",
        error="that the source does not contain this",
        would_detect="a string search of the captured text returning nothing",
        if_absent="the sentence present verbatim, which is what was found",
        against=["A1"], result="survived",
    )
    assert "unaudited-claim" not in codes(run_doctor(root))


def test_a_bent_test_does_not_count_as_an_audit(tmp_path):
    """Mayo's bipartition, enforced: a probe that cannot say what it would have
    seen otherwise is bad evidence, no test — and must not buy silence."""
    from flip import claims as claims_mod

    root = make_notebook(tmp_path)
    claims_mod.add_claim(root, "a load-bearing claim", [], load_bearing=True)
    claims_mod.record_test(root, "C1", probe="substance", error="vague unease",
                           result="survived")
    assert "unaudited-claim" in codes(run_doctor(root))


# --- citation roles: the audit that IS available, taken or not (SPEC §7) --------


def _subject_claim(root, cid="C1", status="asserted", load_bearing=True, subject="A1"):
    """A claim citing one source as what it is ABOUT — no stored count, because
    the axis does not apply to it."""
    from flip import claims as claims_mod

    return claims_mod.add_claim(
        root, f"claim {cid} about a document", [], load_bearing=load_bearing,
        subjects=[subject],
    )


def _severe_attribution(root, cid, against, result="survived"):
    from flip import claims as claims_mod

    return claims_mod.record_test(
        root, cid, probe="attribution",
        error=f"that the claim is not what {against} says",
        would_detect="a string search of the captured text returning the phrase",
        if_absent="zero hits, and an abstract naming something else",
        against=[against], result=result,
    )


def test_a_subject_citation_with_no_attribution_test_is_named(tmp_path):
    """The audit that IS available, not taken — and the anti-abuse half of the
    role design. A `subject` role is authored, so it can be used to duck a bar
    the claim should have faced; what stops that from being invisible is that
    the role is legible on the page and this finding names the untaken test."""
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    _subject_claim(root, "C1")
    warns = [f for f in run_doctor(root) if f.code == "unaudited-claim"]
    assert warns and warns[0].level == "WARN"
    msg = warns[0].message
    assert "A second source is not the ask here and never will be" in msg
    assert "--probe attribution" in msg


def test_a_subject_claim_that_took_its_audit_is_quiet(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    _subject_claim(root, "C1")
    _severe_attribution(root, "C1", "A1")
    assert "unaudited-claim" not in codes(run_doctor(root))


def test_a_subject_claim_is_never_told_to_find_corroboration(tmp_path):
    """The generic nag and the subject nag share a code and must not both fire:
    an operator handed 'link independent sources' next to 'run an attribution
    test' has been offered a cheaper exit than the one that applies, and a
    warning with a cheaper exit is one people take the exit from."""
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    _subject_claim(root, "C1")
    warns = [f for f in run_doctor(root) if f.code == "unaudited-claim"]
    assert len(warns) == 1
    assert "link independent sources" not in warns[0].message


def test_a_verified_subject_claim_with_no_audit_is_under_verified(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    path = _subject_claim(root, "C1").path
    page = pages.read_page(path)
    page.fm["status"] = "verified"  # hand-edited past the gate
    pages.write_page(path, page.fm, page.body)
    errs = [f for f in run_doctor(root) if f.code == "under-verified"]
    assert errs and errs[0].level == "ERROR"
    assert "is not unmet here, it is inapplicable" in errs[0].message
    assert "do not add a source to clear this" in errs[0].message


def test_a_verified_subject_claim_with_its_audit_is_not_under_verified(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    path = _subject_claim(root, "C1").path
    _severe_attribution(root, "C1", "A1")
    page = pages.read_page(path)
    page.fm["status"] = "verified"
    pages.write_page(path, page.fm, page.body)
    assert "under-verified" not in codes(run_doctor(root))


def test_a_stored_count_on_a_subject_only_claim_is_drift(tmp_path):
    """A pre-0.16 page, or a hand edit: the number is not stale, it is about a
    question the claim cannot be asked."""
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    path = _subject_claim(root, "C1").path
    page = pages.read_page(path)
    page.fm["independent_corroboration"] = 0
    pages.write_page(path, page.fm, page.body)
    drift = [f for f in run_doctor(root) if f.code == "corroboration-drift"]
    assert drift and "there is nothing for the count to count" in drift[0].message


def test_a_mixed_claim_keeps_its_count_and_drifts_normally(tmp_path):
    from flip import claims as claims_mod

    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    source_page(root, "A2", grade="B", independence="independent")
    page = claims_mod.add_claim(root, "mixed", ["A1"], load_bearing=True, subjects=["A2"])
    assert page.fm["independent_corroboration"] == 1  # A2 is not counted
    assert "corroboration-drift" not in codes(run_doctor(root))


def test_an_unreadable_citation_role_is_a_bad_enum(tmp_path):
    """It still reads as evidence, so nothing is quietly excused — but the
    operator who meant `subject` has to be told the page does not say so."""
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    path = claim_page(root, "C1", sources=["A1"])
    page = pages.read_page(path)
    page.fm["sources"] = [{"id": "A1", "role": "subjekt"}]
    pages.write_page(path, page.fm, page.body)
    bad = [f for f in run_doctor(root) if f.code == "bad-enum"]
    assert bad and bad[0].level == "ERROR"
    assert "being read as 'evidence'" in bad[0].message


def test_misattribution_on_a_subject_does_not_advise_unlinking(tmp_path):
    """Unlinking is the wrong repair when the source is what the claim is
    about: drop the citation and the claim has nothing left to be true of."""
    root = make_notebook(tmp_path)
    source_page(root, "A1", grade="B", independence="independent")
    _subject_claim(root, "C1")
    _severe_attribution(root, "C1", "A1", result="failed")
    warns = [f for f in run_doctor(root) if f.code == "misattributed-citation"]
    assert warns
    assert "Do NOT unlink" in warns[0].message
    assert "flip claim source rm" not in warns[0].message
