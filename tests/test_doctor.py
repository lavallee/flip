"""Tests for flip.doctor — notebook linting (SPEC §12/§14)."""

import json
from pathlib import Path

from flip.doctor import Finding, run_doctor
from flip.profiles import SECTIONS, load_profile
from flip.util import today

MANIFEST = """\
slug = "test"
kind = "{kind}"
status = "{status}"
created = "2026-07-01"
updated = "2026-07-09"
"""


def profile_md(kind: str) -> str:
    profile = load_profile(kind)
    return "\n\n".join(f"## {SECTIONS[s]['heading']}" for s in profile.sections) + "\n"


def make_notebook(
    tmp_path: Path, kind: str = "scout", status: str = "active", policy: str = ""
) -> Path:
    root = tmp_path / "nb"
    root.mkdir(exist_ok=True)
    (root / "notebook.toml").write_text(
        MANIFEST.format(kind=kind, status=status) + policy, encoding="utf-8"
    )
    return root


def make_healthy_scout(tmp_path: Path) -> Path:
    root = make_notebook(tmp_path, kind="scout")
    (root / "notebook.md").write_text(profile_md("scout"), encoding="utf-8")
    (root / "log").mkdir()
    (root / "log" / "decisions.jsonl").write_text("", encoding="utf-8")
    (root / "log" / "passed.jsonl").write_text("", encoding="utf-8")
    return root


def write_jsonl(root: Path, rel: str, rows: list[dict]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def codes(findings: list[Finding], level: str | None = None) -> list[str]:
    return [f.code for f in findings if level is None or f.level == level]


# --- manifest & profile checks ----------------------------------------------


def test_healthy_scout_notebook_has_no_findings(tmp_path):
    root = make_healthy_scout(tmp_path)
    assert run_doctor(root) == []


def test_missing_manifest_is_bad_manifest_error(tmp_path):
    (tmp_path / "notebook.md").write_text("## The tip\n", encoding="utf-8")
    findings = run_doctor(tmp_path)
    assert "bad-manifest" in codes(findings, "ERROR")


def test_invalid_toml_is_bad_manifest_error(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text("slug = [unclosed", encoding="utf-8")
    assert "bad-manifest" in codes(run_doctor(root), "ERROR")


def test_manifest_missing_slug_is_bad_manifest_not_crash(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text('kind = "scout"\n', encoding="utf-8")
    assert "bad-manifest" in codes(run_doctor(root), "ERROR")


def test_unknown_kind_is_error(tmp_path):
    root = make_healthy_scout(tmp_path)
    (root / "notebook.toml").write_text(
        MANIFEST.format(kind="no-such-kind", status="active"), encoding="utf-8"
    )
    findings = run_doctor(root)
    assert "unknown-kind" in codes(findings, "ERROR")


def test_bad_status_and_visibility_are_errors(tmp_path):
    root = make_healthy_scout(tmp_path)
    (root / "notebook.toml").write_text(
        MANIFEST.format(kind="scout", status="zombie") + '\n[policy]\nvisibility = "top-secret"\n',
        encoding="utf-8",
    )
    found = codes(run_doctor(root), "ERROR")
    assert "bad-status" in found
    assert "bad-visibility" in found


def test_missing_required_paths_warn_while_active_or_dormant(tmp_path):
    # SPEC §12: profile minimums are completion requirements, not creation
    # requirements — a fresh notebook must not ERROR before the files can
    # appear through use.
    for status in ("active", "dormant"):
        root = make_notebook(tmp_path, kind="scout", status=status)
        (root / "notebook.md").write_text(profile_md("scout"), encoding="utf-8")
        findings = run_doctor(root)
        missing = [f for f in findings if f.code == "missing-required"]
        assert {f.path for f in missing} == {"log/decisions.jsonl", "log/passed.jsonl"}, status
        assert all(f.level == "WARN" for f in missing), status


def test_missing_required_paths_error_once_closed(tmp_path):
    for status in ("done", "published", "archived"):
        root = make_notebook(tmp_path, kind="scout", status=status)
        (root / "notebook.md").write_text(profile_md("scout"), encoding="utf-8")
        findings = run_doctor(root)
        missing = [f for f in findings if f.code == "missing-required"]
        assert {f.path for f in missing} == {"log/decisions.jsonl", "log/passed.jsonl"}, status
        assert all(f.level == "ERROR" for f in missing), status
        assert all(status in f.message for f in missing), status


def test_forced_policy_mismatch_is_error(tmp_path):
    # engagement forces visibility = client-confidential
    root = make_notebook(
        tmp_path, kind="engagement", policy='\n[policy]\nvisibility = "internal"\n'
    )
    (root / "notebook.md").write_text(profile_md("engagement"), encoding="utf-8")
    findings = run_doctor(root)
    mismatches = [f for f in findings if f.code == "policy-mismatch"]
    assert mismatches and mismatches[0].level == "ERROR"
    assert "client-confidential" in mismatches[0].message


def test_forced_policy_satisfied_no_mismatch(tmp_path):
    root = make_notebook(
        tmp_path,
        kind="engagement",
        policy='\n[policy]\nvisibility = "client-confidential"\n'
        'citation_rule = "public-terminus"\n',
    )
    (root / "notebook.md").write_text(profile_md("engagement"), encoding="utf-8")
    assert "policy-mismatch" not in codes(run_doctor(root))


# --- notebook.md ------------------------------------------------------------


def test_missing_notebook_md_is_error(tmp_path):
    root = make_healthy_scout(tmp_path)
    (root / "notebook.md").unlink()
    assert "missing-notebook" in codes(run_doctor(root), "ERROR")


def test_missing_section_heading_is_warn_per_section(tmp_path):
    root = make_healthy_scout(tmp_path)
    (root / "notebook.md").write_text("## The tip\n\n## Frame\n", encoding="utf-8")
    warns = [f for f in run_doctor(root) if f.code == "missing-section"]
    assert len(warns) == 4  # hypotheses, sources, decisions, gaps
    assert all(f.level == "WARN" for f in warns)
    assert any("Hypotheses & falsifiers" in f.message for f in warns)


# --- sources ----------------------------------------------------------------


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


def test_orphan_ledger_when_local_file_missing(tmp_path):
    root = make_healthy_scout(tmp_path)
    write_jsonl(
        root,
        "sources/ledger.jsonl",
        [
            {
                "id": "A1",
                "kind": "article",
                "local": "sources/raw/A1.html",
                "grade": "?",
                "independence": "original",
                "freshness": "fresh",
                "status": "captured",
                "supports": [],
            },
        ],
    )
    write_jsonl(root, "sources/_provenance.jsonl", [prov_event("A1", "sources/raw/A1.html")])
    findings = run_doctor(root)
    orphans = [f for f in findings if f.code == "orphan-ledger"]
    assert orphans and orphans[0].level == "ERROR"
    assert orphans[0].path == "sources/raw/A1.html"


def test_unlogged_capture_when_no_provenance_event(tmp_path):
    root = make_healthy_scout(tmp_path)
    raw = root / "sources" / "raw"
    raw.mkdir(parents=True)
    (raw / "A1.html").write_text("x", encoding="utf-8")
    write_jsonl(
        root,
        "sources/ledger.jsonl",
        [
            {
                "id": "A1",
                "kind": "article",
                "local": "sources/raw/A1.html",
                "grade": "B",
                "independence": "original",
                "freshness": "fresh",
                "status": "captured",
                "supports": [],
            },
        ],
    )
    findings = run_doctor(root)
    assert "unlogged-capture" in codes(findings, "WARN")
    # the raw file is also unregistered (no provenance at all)
    assert "unregistered-raw" in codes(findings, "WARN")


def test_registered_source_is_clean(tmp_path):
    root = make_healthy_scout(tmp_path)
    raw = root / "sources" / "raw"
    raw.mkdir(parents=True)
    (raw / "A1.html").write_text("x", encoding="utf-8")
    write_jsonl(
        root,
        "sources/ledger.jsonl",
        [
            {
                "id": "A1",
                "kind": "article",
                "local": "sources/raw/A1.html",
                "grade": "B",
                "independence": "original",
                "freshness": "fresh",
                "status": "captured",
                "supports": [],
            },
        ],
    )
    write_jsonl(root, "sources/_provenance.jsonl", [prov_event("A1", "sources/raw/A1.html")])
    assert run_doctor(root) == []


def test_unregistered_raw_tolerates_directory_captures(tmp_path):
    root = make_healthy_scout(tmp_path)
    capture_dir = root / "sources" / "raw" / "A2"
    capture_dir.mkdir(parents=True)
    (capture_dir / "page.html").write_text("x", encoding="utf-8")
    (root / "sources" / "raw" / "A9.pdf").write_bytes(b"x")
    write_jsonl(root, "sources/_provenance.jsonl", [prov_event("A2", "sources/raw/A2")])
    warns = [f for f in run_doctor(root) if f.code == "unregistered-raw"]
    assert [f.path for f in warns] == ["sources/raw/A9.pdf"]


def test_bad_ledger_enums_are_errors(tmp_path):
    root = make_healthy_scout(tmp_path)
    raw = root / "sources" / "raw"
    raw.mkdir(parents=True)
    (raw / "A1.html").write_text("x", encoding="utf-8")
    write_jsonl(
        root,
        "sources/ledger.jsonl",
        [
            {
                "id": "A1",
                "kind": "article",
                "local": "sources/raw/A1.html",
                "grade": "Z",
                "independence": "hearsay",
                "freshness": "moldy",
                "status": "captured",
                "supports": [],
            },
        ],
    )
    write_jsonl(root, "sources/_provenance.jsonl", [prov_event("A1", "sources/raw/A1.html")])
    bad = [f for f in run_doctor(root) if f.code == "bad-enum"]
    assert len(bad) == 3
    assert all(f.level == "ERROR" for f in bad)


def test_bad_jsonl_is_finding_not_crash(tmp_path):
    root = make_healthy_scout(tmp_path)
    prov = root / "sources" / "_provenance.jsonl"
    prov.parent.mkdir(parents=True)
    prov.write_text("{broken\n", encoding="utf-8")
    findings = run_doctor(root)
    bad = [f for f in findings if f.code == "bad-jsonl"]
    assert bad and bad[0].level == "ERROR"
    assert bad[0].path == "sources/_provenance.jsonl"


# --- claims -----------------------------------------------------------------


def claim(
    cid: str, status: str, load_bearing: bool, sources: list[str], corroboration: int = 0
) -> dict:
    return {
        "id": cid,
        "text": f"claim {cid}",
        "status": status,
        "load_bearing": load_bearing,
        "sources": sources,
        "independent_corroboration": corroboration,
        "first_asserted": "2026-07-09",
        "actor": "human:test",
    }


def source_row(sid: str, root: Path, grade: str = "B", independence: str = "original") -> dict:
    """Create the raw file and provenance line for a source; return its ledger row."""
    raw = root / "sources" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    local = f"sources/raw/{sid}.html"
    (root / local).write_text("x", encoding="utf-8")
    with open(root / "sources" / "_provenance.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(prov_event(sid, local)) + "\n")
    return {
        "id": sid,
        "kind": "article",
        "local": local,
        "grade": grade,
        "independence": independence,
        "freshness": "fresh",
        "status": "captured",
        "supports": [],
    }


def test_under_verified_recomputes_and_ignores_stored_count(tmp_path):
    # kind "ledger": claim_min_independent = 2, grade-A suffices
    root = make_notebook(tmp_path, kind="ledger")
    (root / "notebook.md").write_text(profile_md("ledger"), encoding="utf-8")
    rows = [source_row("A1", root, grade="B", independence="republisher")]
    write_jsonl(root, "sources/ledger.jsonl", rows)
    # stored count lies (says 5); recomputation sees 0 original sources
    write_jsonl(
        root, "analysis/claims.jsonl", [claim("C1", "verified", True, ["A1"], corroboration=5)]
    )
    under = [f for f in run_doctor(root) if f.code == "under-verified"]
    assert under and under[0].level == "ERROR"
    assert under[0].path == "analysis/claims.jsonl"


def test_grade_a_primary_satisfies_the_bar(tmp_path):
    root = make_notebook(tmp_path, kind="ledger")
    (root / "notebook.md").write_text(profile_md("ledger"), encoding="utf-8")
    rows = [source_row("A1", root, grade="A", independence="republisher")]
    write_jsonl(root, "sources/ledger.jsonl", rows)
    write_jsonl(root, "analysis/claims.jsonl", [claim("C1", "verified", True, ["A1"])])
    assert "under-verified" not in codes(run_doctor(root))


def test_enough_original_sources_satisfy_the_bar(tmp_path):
    root = make_notebook(tmp_path, kind="ledger")
    (root / "notebook.md").write_text(profile_md("ledger"), encoding="utf-8")
    rows = [source_row("A1", root), source_row("A2", root)]
    write_jsonl(root, "sources/ledger.jsonl", rows)
    write_jsonl(root, "analysis/claims.jsonl", [claim("C1", "verified", True, ["A1", "A2"])])
    assert "under-verified" not in codes(run_doctor(root))


def test_local_profile_can_disable_grade_a_shortcut(tmp_path):
    root = make_notebook(tmp_path, kind="strict")
    (root / "notebook.md").write_text("scratch\n", encoding="utf-8")
    profile_dir = root / ".flip" / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "strict.toml").write_text(
        'id = "strict"\nsections = []\nrequires = []\n'
        "claim_min_independent = 2\nclaim_grade_a_suffices = false\n",
        encoding="utf-8",
    )
    rows = [source_row("A1", root, grade="A", independence="republisher")]
    write_jsonl(root, "sources/ledger.jsonl", rows)
    write_jsonl(root, "analysis/claims.jsonl", [claim("C1", "verified", True, ["A1"])])
    assert "under-verified" in codes(run_doctor(root), "ERROR")


def test_under_verified_dedupes_duplicate_source_ids(tmp_path):
    # kind "ledger": claim_min_independent = 2 — the same source listed twice
    # must count once, not clear the bar.
    root = make_notebook(tmp_path, kind="ledger")
    (root / "notebook.md").write_text(profile_md("ledger"), encoding="utf-8")
    rows = [source_row("A1", root, grade="B", independence="original")]
    write_jsonl(root, "sources/ledger.jsonl", rows)
    write_jsonl(
        root, "analysis/claims.jsonl", [claim("C1", "verified", True, ["A1", "A1"])]
    )
    under = [f for f in run_doctor(root) if f.code == "under-verified"]
    assert under and under[0].level == "ERROR"
    assert "1 independent" in under[0].message


def test_under_verified_ignores_ungraded_sources(tmp_path):
    # Two originals, but one still graded "?": capture-time defaults must not
    # satisfy the bar (SPEC §7.2 — ungraded sources never corroborate).
    root = make_notebook(tmp_path, kind="ledger")
    (root / "notebook.md").write_text(profile_md("ledger"), encoding="utf-8")
    rows = [
        source_row("A1", root, grade="B", independence="original"),
        source_row("A2", root, grade="?", independence="original"),
    ]
    write_jsonl(root, "sources/ledger.jsonl", rows)
    write_jsonl(root, "analysis/claims.jsonl", [claim("C1", "verified", True, ["A1", "A2"])])
    assert "under-verified" in codes(run_doctor(root), "ERROR")


# --- stale freshness ----------------------------------------------------------


def test_stale_freshness_warns_on_old_but_fresh_source(tmp_path):
    root = make_healthy_scout(tmp_path)
    row = source_row("A1", root)
    row["date"] = "2020-01-01"  # far past scout's 18-month threshold
    row["freshness"] = "fresh"
    write_jsonl(root, "sources/ledger.jsonl", [row])
    stale = [f for f in run_doctor(root) if f.code == "stale-freshness"]
    assert stale and stale[0].level == "WARN"
    assert "A1" in stale[0].message and "flip grade" in stale[0].message


def test_stale_freshness_silent_for_recent_dated_or_undated(tmp_path):
    root = make_healthy_scout(tmp_path)
    recent = source_row("A1", root)
    recent["date"] = today()  # fresh and recent
    judged_dated = source_row("A2", root)
    judged_dated["date"] = "2020-01-01"
    judged_dated["freshness"] = "dated"  # already re-judged — nothing to flag
    undated = source_row("A3", root)  # no date at all
    write_jsonl(root, "sources/ledger.jsonl", [recent, judged_dated, undated])
    assert "stale-freshness" not in codes(run_doctor(root))


def test_load_bearing_asserted_claim_is_warn(tmp_path):
    root = make_healthy_scout(tmp_path)
    write_jsonl(root, "analysis/claims.jsonl", [claim("C1", "asserted", True, [])])
    warns = [f for f in run_doctor(root) if f.code == "unaudited-claim"]
    assert warns and warns[0].level == "WARN"


def test_non_load_bearing_asserted_claim_is_fine(tmp_path):
    root = make_healthy_scout(tmp_path)
    write_jsonl(root, "analysis/claims.jsonl", [claim("C1", "asserted", False, [])])
    assert "unaudited-claim" not in codes(run_doctor(root))


def test_invalid_claim_status_is_error(tmp_path):
    root = make_healthy_scout(tmp_path)
    write_jsonl(root, "analysis/claims.jsonl", [claim("C1", "maybe", False, [])])
    bad = [f for f in run_doctor(root) if f.code == "bad-enum"]
    assert bad and bad[0].level == "ERROR"
    assert bad[0].path == "analysis/claims.jsonl"
