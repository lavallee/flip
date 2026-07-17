"""Tests for flip.migrate: v0.3 ledgers → pages, and the 0.5 profile pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from flip import pages
from flip.manifest import FLIP_PROFILE_VERSION, load_manifest
from flip.migrate import migrate
from flip.util import UID_RE, is_notebook_root, next_id, today, write_jsonl

# What the profile pass reports on a v0.3 chain: the notebook has never had a
# uid, and v0.3 manifests carry no links.beat with '#'.
PROFILE_COUNTS = {"uid_added": 1, "beat_link_rewritten": 0,
                  "profile": FLIP_PROFILE_VERSION}

NOTEBOOK_TOML = """\
slug = "demo"
title = "Demo notebook"
kind = "scout"
status = "active"
created = 2026-07-01
updated = "2026-07-08"
description = "hand-added prose the tooling must not eat"

[policy]
visibility = "internal"
renders_public = false
source_trail_public = true
citation_rule = "public-terminus"
custom_gate = "editor-signoff"

[links]
corpus = "corpus://nj-schools"

[tools]
web = "single-file 1.22"

[beat]
mission = "school funding"
"""

SOURCE_ROWS = [
    {
        "id": "A1", "kind": "web", "title": "Vendor study",
        "url": "https://example.com/study", "local": "sources/raw/A1/page.html",
        "date": "2025-11-01", "authors": ["V. Endor"], "publisher": "example.com",
        "grade": "B", "independence": "original", "freshness": "fresh",
        "status": "captured", "notes": "single vendor; treat with care",
        "supports": ["C1"],
    },
    # same title → slug collision must yield vendor-study-2
    {"id": "A2", "kind": "web", "title": "Vendor study",
     "url": "https://example.com/study2", "local": "sources/raw/A2/page.html"},
    # no title → slug and title from the local basename; judgment defaults
    {"id": "F1", "kind": "file", "local": "sources/raw/F1.csv"},
]

CLAIM_ROWS = [
    {
        "id": "C1", "text": "Conversion is 42% higher", "status": "needs-2nd",
        "load_bearing": True, "sources": ["A1", "X9"],  # X9 dangles, legally
        "independent_corroboration": 0,  # stale; must be recomputed
        "first_asserted": "2026-07-09", "actor": "agent:test",
        "notes": "single vendor study",
    },
]

DECISION_ROWS = [
    {
        "ts": "2026-07-09T11:00:00Z", "id": "D1", "question": "Scope?",
        "decision": "Vendor claims only", "why": "time-boxed",
        "alternatives_rejected": ["full market survey"], "actor": "human:test",
    },
]

QUESTION_EVENTS = [
    {"ts": "2026-07-09T11:05:00Z", "id": "Q1", "text": "Do platforms publish data?",
     "actor": "agent:test"},
    {"ts": "2026-07-09T11:06:00Z", "id": "Q2", "text": "Second source for the 42%?",
     "actor": "agent:test"},
    {"ts": "2026-07-10T08:00:00Z", "id": "Q1", "status": "answered",
     "actor": "human:test", "note": "Yes — quarterly transparency reports."},
]

SESSION_PSEUDO = """\
actor: agent:claude
model: m1
started: 2026-07-01T10:00:00Z

## Goal
sweep the corpus
"""


def make_v03(tmp_path: Path) -> Path:
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text(NOTEBOOK_TOML, encoding="utf-8")
    (root / "notebook.md").write_text("# Reporter's notebook — Demo\n", encoding="utf-8")
    write_jsonl(root / "sources" / "ledger.jsonl", SOURCE_ROWS)
    write_jsonl(root / "analysis" / "claims.jsonl", CLAIM_ROWS)
    write_jsonl(root / "log" / "decisions.jsonl", DECISION_ROWS)
    write_jsonl(root / "log" / "questions.jsonl", QUESTION_EVENTS)
    # append-only history that must survive byte-for-byte
    write_jsonl(root / "log" / "log.jsonl",
                [{"ts": "2026-07-09T09:00:00Z", "text": "captured A1", "actor": "agent:test"}])
    write_jsonl(root / "log" / "passed.jsonl",
                [{"ts": "2026-07-09T09:30:00Z", "text": "skipped X", "reason": "stale",
                  "actor": "agent:test"}])
    write_jsonl(root / "sources" / "_provenance.jsonl",
                [{"ts": "2026-07-09T10:00:00Z", "source_id": "A1", "sha256": "ab" * 32,
                  "local_path": "sources/raw/A1/page.html", "tool": "single-file",
                  "actor": "agent:test"}])
    raw = root / "sources" / "raw" / "A1"
    raw.mkdir(parents=True)
    (raw / "page.html").write_text("<html>study</html>", encoding="utf-8")
    write_jsonl(root / "derived" / "_derivations.jsonl", [{"inputs": ["A1"]}])
    sessions = root / "log" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "2026-07-01T1000-sweep.md").write_text(SESSION_PSEUDO, encoding="utf-8")
    return root


# -- the happy path ----------------------------------------------------------


def test_migrate_counts_and_notebook_toml_gone(tmp_path):
    root = make_v03(tmp_path)
    summary = migrate(root)
    assert summary == {"sources": 3, "claims": 1, "decisions": 1, "questions": 2,
                       "sessions": 1, "already_migrated": 0, **PROFILE_COUNTS}
    assert not (root / "notebook.toml").exists()
    assert is_notebook_root(root)


def test_migrate_gives_notebook_md_its_okf_type(tmp_path):
    # v0.3 notebook.md has no frontmatter; v0.4 requires `type` on every
    # non-reserved page (SPEC §3). The prose body survives byte-for-byte.
    root = make_v03(tmp_path)
    migrate(root)
    fm, body = pages.parse((root / "notebook.md").read_text(encoding="utf-8"))
    assert fm["type"] == "Notebook"
    assert fm["description"] == "Demo notebook"
    assert body.lstrip("\n") == "# Reporter's notebook — Demo\n"


def test_migrate_keeps_existing_notebook_md_frontmatter(tmp_path):
    root = make_v03(tmp_path)
    (root / "notebook.md").write_text(
        "---\ncustom: kept\n---\n\n# Prose\n", encoding="utf-8"
    )
    migrate(root)
    fm, body = pages.parse((root / "notebook.md").read_text(encoding="utf-8"))
    assert fm == {"type": "Notebook", "custom": "kept"}  # type added, foreign key kept
    assert body.lstrip("\n") == "# Prose\n"


def test_migrate_manifest_round_trips_policy_and_extras(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    m = load_manifest(root)
    assert m.slug == "demo"
    assert m.title == "Demo notebook"
    assert m.kind == "scout"
    assert m.status == "active"
    assert m.created == "2026-07-01"  # unquoted TOML date tolerated
    assert m.updated == today()  # migration is a mutation
    assert m.policy == {
        "visibility": "internal",
        "renders_public": False,
        "source_trail_public": True,
        "citation_rule": "public-terminus",
    }
    assert m.links == {"corpus": "corpus://nj-schools"}
    assert m.tools == {"web": "single-file 1.22"}
    assert m.extras["description"] == "hand-added prose the tooling must not eat"
    assert m.extras["beat"] == {"mission": "school funding"}
    assert m.extras["policy"] == {"custom_gate": "editor-signoff"}  # unknown tunable survives


def test_migrate_sources_become_reference_pages(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    assert not (root / "sources" / "ledger.jsonl").exists()
    page = pages.read_page(root / "references" / "vendor-study.md")
    assert page.fm["type"] == "Source"
    assert page.fm["id"] == "A1"
    assert page.fm["aliases"] == ["A1"]
    assert page.fm["title"] == "Vendor study"
    assert page.fm["resource"] == "https://example.com/study"  # url → SPEC §5.3 slot
    assert page.fm["date"] == "2025-11-01"
    assert page.fm["authors"] == ["V. Endor"]
    assert page.fm["publisher"] == "example.com"
    assert page.fm["local"] == "sources/raw/A1/page.html"
    assert page.fm["grade"] == "B"
    assert page.fm["independence"] == "original"
    assert page.fm["freshness"] == "fresh"
    assert page.fm["status"] == "captured"
    assert page.fm["kind"] == "web"  # unconsumed row fields survive
    assert page.fm["supports"] == ["C1"]
    assert "# Vendor study" in page.body
    assert "single vendor; treat with care" in page.body
    # collision gets -2; id resolution works through frontmatter
    assert pages.read_page(root / "references" / "vendor-study-2.md").fm["id"] == "A2"
    assert pages.find_by_id(root, "A1").slug == "vendor-study"


def test_migrate_untitled_source_uses_local_basename_and_defaults(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    page = pages.read_page(root / "references" / "f1-csv.md")
    assert page.fm["id"] == "F1"
    assert page.fm["title"] == "F1.csv"
    assert page.fm["grade"] == "?"  # capture is custody, not judgment
    assert page.fm["independence"] == "original"
    assert page.fm["freshness"] == "fresh"
    assert page.fm["status"] == "captured"
    assert "resource" not in page.fm  # no url on the row


def test_migrate_claims_get_citations_and_recomputed_corroboration(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    assert not (root / "analysis" / "claims.jsonl").exists()
    page = pages.read_page(root / "claims" / "conversion-is-42-higher.md")
    assert page.fm["type"] == "Claim"
    assert page.fm["id"] == "C1"
    assert page.fm["status"] == "needs-2nd"
    assert page.fm["load_bearing"] is True
    assert page.fm["sources"] == ["A1", "X9"]
    assert page.fm["supports"] == ["/references/vendor-study"]  # dangling X9 contributes nothing
    assert page.fm["independent_corroboration"] == 1  # recomputed: A1 judged B + original
    assert page.fm["first_asserted"] == "2026-07-09"
    assert page.fm["actor"] == "agent:test"
    assert "Conversion is 42% higher" in page.body
    assert "_single vendor study_" in page.body
    assert "# Citations" in page.body
    assert "[1] [Vendor study](../references/vendor-study.md)" in page.body
    assert "[2] X9" in page.body  # dangling citation stays visible


def test_migrate_decisions_become_pages(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    assert not (root / "log" / "decisions.jsonl").exists()
    page = pages.read_page(root / "decisions" / "vendor-claims-only.md")
    assert page.fm["type"] == "Decision"
    assert page.fm["id"] == "D1"
    assert page.fm["question"] == "Scope?"
    assert page.fm["alternatives_rejected"] == ["full market survey"]
    assert page.fm["timestamp"] == "2026-07-09T11:00:00Z"
    assert page.fm["actor"] == "human:test"
    for chunk in ("**Question.** Scope?", "**Decision.** Vendor claims only",
                  "**Why.** time-boxed", "**Rejected.** full market survey"):
        assert chunk in page.body


def test_migrate_folds_question_events(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    assert not (root / "log" / "questions.jsonl").exists()
    answered = pages.find_by_id(root, "Q1")
    assert answered.fm["status"] == "answered"  # last status wins
    assert answered.fm["timestamp"] == "2026-07-09T11:05:00Z"  # ask ts kept
    assert answered.fm["actor"] == "agent:test"
    assert answered.fm["answered"] == "2026-07-10T08:00:00Z"
    assert answered.fm["answered_by"] == "human:test"
    assert answered.body.lstrip("\n").startswith("Do platforms publish data?")  # ask text kept
    assert "## Answer\nYes — quarterly transparency reports." in answered.body
    still_open = pages.find_by_id(root, "Q2")
    assert still_open.fm["status"] == "open"
    assert "answered" not in still_open.fm
    assert "Second source for the 42%?" in still_open.body


def test_migrate_moves_sessions_with_frontmatter(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    assert not (root / "log" / "sessions").exists()  # emptied and removed
    page = pages.read_page(root / "sessions" / "2026-07-01T1000-sweep.md")
    assert page.fm["type"] == "Work Session"
    assert page.fm["actor"] == "agent:claude"  # pseudo-frontmatter parsed
    assert page.fm["model"] == "m1"
    assert page.fm["started"] == "2026-07-01T10:00:00Z"
    assert "## Goal\nsweep the corpus" in page.body


def test_migrate_session_with_real_frontmatter(tmp_path):
    root = make_v03(tmp_path)
    (root / "log" / "sessions" / "2026-07-02T0900-audit.md").write_text(
        "---\nactor: human:test\nstarted: 2026-07-02T09:00:00Z\n---\n\n## Goal\naudit\n",
        encoding="utf-8",
    )
    summary = migrate(root)
    assert summary["sessions"] == 2
    page = pages.read_page(root / "sessions" / "2026-07-02T0900-audit.md")
    assert page.fm["type"] == "Work Session"
    assert page.fm["actor"] == "human:test"
    assert "## Goal\naudit" in page.body


def test_migrate_leaves_event_history_untouched(tmp_path):
    root = make_v03(tmp_path)
    keep = ("log/log.jsonl", "log/passed.jsonl", "sources/_provenance.jsonl",
            "derived/_derivations.jsonl", "sources/raw/A1/page.html")
    before = {rel: (root / rel).read_bytes() for rel in keep}
    migrate(root)
    for rel in keep:
        assert (root / rel).read_bytes() == before[rel], rel


def test_migrated_ids_are_never_reused(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    ids = pages.all_ids(root)
    assert {"A1", "A2", "F1", "C1", "D1", "Q1", "Q2"} <= set(ids)
    assert next_id("A", ids) == "A3"
    assert next_id("C", ids) == "C2"
    assert next_id("Q", ids) == "Q3"


# -- refusals and resilience ---------------------------------------------------


def test_migrate_refuses_already_current_notebook(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    with pytest.raises(SystemExit, match="already at the current profile"):
        migrate(root)


def test_migrate_refuses_non_notebook(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit, match="not a flip notebook"):
        migrate(empty)


def test_migrate_missing_slug_is_actionable(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text('title = "no slug"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="slug"):
        migrate(root)


def test_migrate_bad_toml_is_actionable(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text("slug = [unclosed\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="TOML"):
        migrate(root)


def test_migrate_row_without_id_aborts_before_writing(tmp_path):
    root = make_v03(tmp_path)
    write_jsonl(root / "sources" / "ledger.jsonl", [{"title": "no id"}])
    with pytest.raises(SystemExit, match="no id"):
        migrate(root)
    # nothing was converted: still a v0.3 notebook, ledgers intact
    assert (root / "notebook.toml").exists()
    assert not (root / "index.md").exists()
    assert not (root / "references").exists()


def test_migrate_bad_ledger_line_is_actionable(tmp_path):
    root = make_v03(tmp_path)
    with open(root / "analysis" / "claims.jsonl", "a", encoding="utf-8") as f:
        f.write("{not json\n")
    with pytest.raises(SystemExit, match="claims.jsonl"):
        migrate(root)
    assert (root / "notebook.toml").exists()  # aborted clean


def test_migrate_empty_ledgers_still_migrates_manifest(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text('slug = "bare"\nkind = "ledger"\n', encoding="utf-8")
    summary = migrate(root)
    assert summary == {"sources": 0, "claims": 0, "decisions": 0, "questions": 0,
                       "sessions": 0, "already_migrated": 0, **PROFILE_COUNTS}
    assert is_notebook_root(root)
    assert load_manifest(root).slug == "bare"
    assert not (root / "notebook.toml").exists()


def test_migrate_resumes_after_partial_run(tmp_path):
    # simulate an interruption: sources already converted and their ledger
    # deleted, notebook.toml still present — the re-run finishes the rest
    root = make_v03(tmp_path)
    full = {"sources": 3, "claims": 1, "decisions": 1, "questions": 2,
            "sessions": 1, "already_migrated": 0, **PROFILE_COUNTS}
    first = migrate(root)
    assert first == full
    uid = load_manifest(root).uid  # minted once; a re-run must not re-mint it
    # rebuild a half-migrated state: restore notebook.toml and one ledger
    (root / "notebook.toml").write_text(NOTEBOOK_TOML, encoding="utf-8")
    write_jsonl(root / "log" / "decisions.jsonl",
                [{**DECISION_ROWS[0], "id": "D2", "decision": "Second pass"}])
    second = migrate(root)
    assert second == {"sources": 0, "claims": 0, "decisions": 1, "questions": 0,
                      "sessions": 0, "already_migrated": 0, "uid_added": 0,
                      "beat_link_rewritten": 0, "profile": FLIP_PROFILE_VERSION}
    assert not (root / "notebook.toml").exists()
    assert load_manifest(root).uid == uid  # identity survives the resume
    assert pages.find_by_id(root, "D2") is not None
    # the first run's pages are untouched
    assert pages.find_by_id(root, "D1") is not None


def test_migrate_resume_skips_rows_whose_pages_exist(tmp_path):
    # an interrupted run wrote pages but was killed before unlinking the
    # ledger: the re-run must not duplicate those pages (or hand their slugs
    # a -2 suffix and re-mint their ids) — it skips them as already migrated
    root = make_v03(tmp_path)
    migrate(root)
    # interruption state: notebook.toml back, full ledgers back — every row's
    # page already exists except a genuinely new decision
    (root / "notebook.toml").write_text(NOTEBOOK_TOML, encoding="utf-8")
    write_jsonl(root / "sources" / "ledger.jsonl", SOURCE_ROWS)
    write_jsonl(root / "analysis" / "claims.jsonl", CLAIM_ROWS)
    write_jsonl(root / "log" / "decisions.jsonl",
                DECISION_ROWS + [{**DECISION_ROWS[0], "id": "D2", "decision": "Second pass"}])
    write_jsonl(root / "log" / "questions.jsonl", QUESTION_EVENTS)

    summary = migrate(root)

    assert summary == {"sources": 0, "claims": 0, "decisions": 1, "questions": 0,
                       "sessions": 0, "already_migrated": 7, "uid_added": 0,
                       "beat_link_rewritten": 0, "profile": FLIP_PROFILE_VERSION}
    # no duplicated pages, no -2 slugs, no duplicate ids
    for dup in ("vendor-study-3.md", "conversion-is-42-higher-2.md",
                "vendor-claims-only-2.md"):
        assert not list(root.rglob(dup)), dup
    ids = pages.all_ids(root)
    assert len([i for i in ids if i == "C1"]) == 1
    assert len([i for i in ids if i == "D1"]) == 1
    assert pages.find_by_id(root, "D2") is not None
    assert not (root / "notebook.toml").exists()


# -- the 0.5 profile pass ------------------------------------------------------


def make_v04(tmp_path: Path, *, uid: str = "", links: dict | None = None,
             extra_fm: dict | None = None) -> Path:
    """A page-shaped notebook whose manifest still declares flip '0.4' —
    what a live 0.4 notebook looks like before its first 0.9 command."""
    root = tmp_path / "orchard-survey"
    root.mkdir()
    fm: dict = {
        "okf_version": "0.1", "flip": "0.4", "slug": "orchard-survey",
        "title": "Orchard survey", "kind": "scout", "status": "active",
        "created": "2026-07-01", "updated": "2026-07-01",
        "visibility": "internal", "renders_public": False,
        "source_trail_public": False, "citation_rule": "public-terminus",
    }
    if uid:
        fm["uid"] = uid
    if links:
        fm["links"] = links
    fm.update(extra_fm or {})
    pages.write_page(root / "index.md", fm, "# Orchard survey\n")
    return root


def test_profile_pass_adds_uid_and_stamps_version(tmp_path):
    root = make_v04(tmp_path)
    summary = migrate(root)
    assert summary == PROFILE_COUNTS
    m = load_manifest(root)
    assert UID_RE.match(m.uid)
    assert pages.read_page(root / "index.md").fm["flip"] == FLIP_PROFILE_VERSION
    assert m.updated == today()  # migration is a mutation


def test_profile_pass_never_remints_an_existing_uid(tmp_path):
    root = make_v04(tmp_path, uid="nb-7k3m9p2x")
    summary = migrate(root)
    assert summary == {"uid_added": 0, "beat_link_rewritten": 0,
                       "profile": FLIP_PROFILE_VERSION}
    assert load_manifest(root).uid == "nb-7k3m9p2x"


def test_profile_pass_rewrites_only_the_beat_link(tmp_path):
    root = make_v04(tmp_path, links={"beat": "county#TH2",
                                     "corpus": "corpus://field-notes#frag"})
    summary = migrate(root)
    assert summary["beat_link_rewritten"] == 1
    m = load_manifest(root)
    assert m.links["beat"] == "county:TH2"
    assert m.links["corpus"] == "corpus://field-notes#frag"  # foreign '#' kept


def test_profile_pass_leaves_canonical_beat_link_alone(tmp_path):
    root = make_v04(tmp_path, links={"beat": "county:TH2"})
    summary = migrate(root)
    assert summary["beat_link_rewritten"] == 0
    assert load_manifest(root).links["beat"] == "county:TH2"


def test_profile_pass_leaves_malformed_beat_link_alone(tmp_path):
    # nothing before the '#': not a rewritable "<slug>#<TH#>" — kept for
    # doctor to flag, while the rest of the upgrade still lands
    root = make_v04(tmp_path, links={"beat": "#TH2"})
    summary = migrate(root)
    assert summary == PROFILE_COUNTS  # uid minted, nothing rewritten
    assert load_manifest(root).links["beat"] == "#TH2"


def test_profile_pass_preserves_foreign_frontmatter(tmp_path):
    root = make_v04(tmp_path, extra_fm={"description": "hand-added prose",
                                        "gardening": {"season": "spring"}})
    migrate(root)
    fm = pages.read_page(root / "index.md").fm
    assert fm["description"] == "hand-added prose"
    assert fm["gardening"] == {"season": "spring"}


def test_migrate_restamps_declared_04_even_with_uid(tmp_path):
    # uid present and links canonical, but the manifest still says flip
    # '0.4' — not current: migrate restamps instead of refusing, and only
    # the second run is the refusal
    root = make_v04(tmp_path, uid="nb-7k3m9p2x", links={"beat": "county:TH2"})
    summary = migrate(root)
    assert summary == {"uid_added": 0, "beat_link_rewritten": 0,
                       "profile": FLIP_PROFILE_VERSION}
    assert pages.read_page(root / "index.md").fm["flip"] == FLIP_PROFILE_VERSION
    with pytest.raises(SystemExit, match="already at the current profile"):
        migrate(root)


def test_migrate_refuses_freshly_scaffolded_notebook(tmp_path):
    from flip.scaffold import create_notebook

    root = create_notebook(tmp_path / "fresh", "fresh", "scout")
    with pytest.raises(SystemExit, match="already at the current profile"):
        migrate(root)


def test_v03_chain_ends_at_current_profile(tmp_path):
    root = make_v03(tmp_path)
    migrate(root)
    fm = pages.read_page(root / "index.md").fm
    assert fm["flip"] == FLIP_PROFILE_VERSION
    assert UID_RE.match(fm["uid"])


def test_migrate_question_event_extras_fold_onto_the_page(tmp_path):
    # unconsumed fields on ask AND answer events must land in the page
    # frontmatter (later events win per key) — sources/claims/decisions
    # already preserve row leftovers; questions were silently dropping them
    root = make_v03(tmp_path)
    write_jsonl(root / "log" / "questions.jsonl", [
        {"ts": "2026-07-09T11:05:00Z", "id": "Q1", "text": "Do platforms publish data?",
         "actor": "agent:test", "priority": "high", "blocking": True},
        {"ts": "2026-07-10T08:00:00Z", "id": "Q1", "status": "answered",
         "actor": "human:test", "note": "Yes.", "confidence": 0.9, "priority": "low"},
    ])
    migrate(root)
    page = pages.find_by_id(root, "Q1")
    assert page.fm["blocking"] is True  # ask-event extra preserved
    assert page.fm["confidence"] == 0.9  # answer-event extra preserved
    assert page.fm["priority"] == "low"  # later event wins per key
    assert page.fm["status"] == "answered"
    assert page.fm["answered_by"] == "human:test"
