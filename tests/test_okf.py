"""OKF export tests — the policy filter over the bundle the notebook already is:
copy shape, visibility gate, source-trail stripping/enrichment, re-export,
announce marker block."""

from pathlib import Path

import pytest

from flip import pages
from flip.okf import MARKER_END, MARKER_START, STATE_FILE, export_okf
from flip.util import append_jsonl, sha256_file

SHA = "ab" * 32


def manifest_md(visibility: str, trail: bool) -> str:
    return (
        "---\n"
        'okf_version: "0.1"\n'
        'flip: "0.4"\n'
        "slug: demo\n"
        "title: Demo notebook\n"
        "kind: scout\n"
        "status: active\n"
        "created: 2026-07-01\n"
        "updated: 2026-07-10\n"
        f"visibility: {visibility}\n"
        "renders_public: false\n"
        f"source_trail_public: {'true' if trail else 'false'}\n"
        "citation_rule: public-terminus\n"
        "---\n"
        "# Demo notebook\n\n"
        "* [References](references/) - 2 captured sources\n"
    )


def make_notebook(root: Path, visibility: str = "public", trail: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.md").write_text(manifest_md(visibility, trail), encoding="utf-8")
    (root / "notebook.md").write_text(
        "---\ntype: Notebook\ndescription: Demo\n---\n\n# Reporter's notebook — Demo\n",
        encoding="utf-8",
    )
    (root / "log.md").write_text("# Update Log\n\n## 2026-07-09\n* captured A1\n",
                                 encoding="utf-8")
    pages.write_page(
        root / "references" / "vendor-study.md",
        {
            "type": "Source", "id": "A1", "aliases": ["A1"], "title": "Vendor study",
            "description": "single-vendor conversion study",
            "resource": "https://example.com/study", "date": "2025-11-01",
            "authors": ["V. Endor"], "publisher": "example.com",
            "local": "sources/raw/A1/page.html", "grade": "B",
            "independence": "original", "freshness": "fresh", "status": "captured",
            "obsidian_extra": "survives",  # foreign key must round-trip
        },
        "# Vendor study\n\nCapture notes worth keeping.\n",
    )
    pages.write_page(
        root / "references" / "enrollment-table.md",
        {
            "type": "Source", "id": "F1", "aliases": ["F1"], "title": "Enrollment table",
            "local": "sources/raw/F1.csv", "grade": "A", "independence": "original",
            "freshness": "fresh", "status": "captured",
        },
        "# Enrollment table\n",
    )
    (root / "references" / "index.md").write_text("# References\n", encoding="utf-8")
    (root / "references" / "_private-note.md").write_text("scratch\n", encoding="utf-8")
    pages.write_page(
        root / "claims" / "conversion-42.md",
        {
            "type": "Claim", "id": "C1", "aliases": ["C1"],
            "description": "Conversion is 42% higher", "status": "needs-2nd",
            "load_bearing": True, "sources": ["A1"],
            "supports": ["/references/vendor-study"], "independent_corroboration": 1,
            "first_asserted": "2026-07-09", "actor": "agent:test",
        },
        "Conversion is 42% higher\n\n# Citations\n"
        "[1] [Vendor study](../references/vendor-study.md)\n",
    )
    pages.write_page(
        root / "decisions" / "vendor-claims-only.md",
        {"type": "Decision", "id": "D1", "aliases": ["D1"],
         "description": "Vendor claims only", "question": "Scope?",
         "timestamp": "2026-07-09T11:00:00Z", "actor": "human:test"},
        "**Question.** Scope?\n\n**Decision.** Vendor claims only\n\n**Why.** time-boxed\n",
    )
    pages.write_page(
        root / "questions" / "platform-data.md",
        {"type": "Question", "id": "Q1", "aliases": ["Q1"], "description": "Platform data?",
         "status": "open", "timestamp": "2026-07-09T11:05:00Z", "actor": "agent:test"},
        "Platform data?\n",
    )
    pages.write_page(
        root / "sessions" / "2026-07-09T1000-sweep.md",
        {"type": "Work Session", "actor": "agent:test", "started": "2026-07-09T10:00:00Z"},
        "## Goal\nsweep\n",
    )
    pages.write_page(
        root / "analysis" / "findings.md",
        {"type": "Finding", "description": "what survived"},
        "# Findings\n",
    )
    raw = root / "sources" / "raw" / "A1"
    raw.mkdir(parents=True)
    (raw / "page.html").write_text("<html>study</html>", encoding="utf-8")
    (root / "sources" / "text").mkdir()
    (root / "sources" / "text" / "A1.md").write_text("study text\n", encoding="utf-8")
    append_jsonl(
        root / "sources" / "_provenance.jsonl",
        {"ts": "2026-07-09T10:00:00Z", "source_id": "A1", "url": "https://example.com/study",
         "local_path": "sources/raw/A1/page.html", "sha256": SHA, "bytes": 100,
         "tool": "single-file", "actor": "agent:test"},
    )
    append_jsonl(root / "log" / "log.jsonl",
                 {"ts": "2026-07-09T09:00:00Z", "text": "captured A1", "actor": "agent:test"})
    append_jsonl(root / "log" / "passed.jsonl",
                 {"ts": "2026-07-09T09:30:00Z", "text": "skipped X", "reason": "stale",
                  "actor": "agent:test"})
    # content that must NEVER ship
    (root / "derived").mkdir()
    (root / "derived" / "_derivations.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "derived" / "table.csv").write_text("a,b\n", encoding="utf-8")
    (root / "drafts" / "v0").mkdir(parents=True)
    (root / "drafts" / "v0" / "draft.md").write_text("draft\n", encoding="utf-8")
    (root / "renders" / "site").mkdir(parents=True)
    (root / "renders" / "site" / "index.html").write_text("<html/>", encoding="utf-8")
    (root / ".flip" / "profiles").mkdir(parents=True)
    (root / ".flip" / "profiles" / "scout.toml").write_text('id = "scout"\n', encoding="utf-8")
    (root / ".flip" / "ids").write_text("A1\nF1\nC1\nD1\nQ1\n", encoding="utf-8")
    (root / "_scratch.md").write_text("private\n", encoding="utf-8")
    return root


# -- policy gate -----------------------------------------------------------


def test_policy_gate_refuses_non_public(tmp_path):
    nb = make_notebook(tmp_path / "nb", visibility="internal")
    with pytest.raises(SystemExit, match="visibility"):
        export_okf(nb, tmp_path / "bundle")
    # include_private overrides
    dest = export_okf(nb, tmp_path / "bundle", include_private=True)
    assert (dest / "index.md").is_file()


def test_requires_notebook_root(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit, match="index.md"):
        export_okf(empty, tmp_path / "bundle")


# -- copy shape ------------------------------------------------------------


def test_bundle_is_a_filtered_copy(tmp_path):
    nb = make_notebook(tmp_path / "nb", trail=False)
    dest = export_okf(nb, tmp_path / "bundle")

    # the knowledge surface ships, byte-identical where policy allows
    for rel in (
        "notebook.md",
        "claims/conversion-42.md", "decisions/vendor-claims-only.md",
        "questions/platform-data.md", "sessions/2026-07-09T1000-sweep.md",
        "analysis/findings.md",
    ):
        assert (dest / rel).is_file(), rel
        assert (dest / rel).read_bytes() == (nb / rel).read_bytes(), rel
    # custody, history (including its generated log.md rendering), drafts,
    # renders, tooling (.flip/ids reservation file), and _private files do not
    for rel in (
        "sources", "log", "log.md", "derived", "drafts", "renders", ".flip",
        ".flip/ids", "_scratch.md", "references/_private-note.md",
    ):
        assert not (dest / rel).exists(), rel
    # the root listing ships, minus the Update Log entry for the withheld log
    index_text = (dest / "index.md").read_text(encoding="utf-8")
    assert index_text.startswith("---\n")
    assert "[References](references/)" in index_text
    assert "log.md" not in index_text
    assert (dest / STATE_FILE).is_file()


def test_full_trail_ships_log_md(tmp_path):
    nb = make_notebook(tmp_path / "nb", trail=True)
    dest = export_okf(nb, tmp_path / "bundle")
    assert (dest / "log.md").read_bytes() == (nb / "log.md").read_bytes()
    assert "[Update Log](log.md)" in (dest / "index.md").read_text(encoding="utf-8")


def test_nested_exports_never_ship(tmp_path):
    # an OKF bundle (with .last-export.json) and a BagIt bag (with bagit.txt)
    # nested inside the notebook hold raw custody bytes; a later stripped
    # export must prune both wholesale (they are copies, not notebook content)
    from flip.export import export_bag

    nb = make_notebook(tmp_path / "nb", trail=False)
    export_okf(nb, nb / "prior-bundle", include_private=True)  # full trail inside
    export_bag(nb, nb / "prior-bag")
    assert (nb / "prior-bundle" / "sources" / "_provenance.jsonl").is_file()
    assert (nb / "prior-bag" / "data" / "sources" / "raw" / "A1" / "page.html").is_file()

    dest = export_okf(nb, tmp_path / "bundle")

    assert not (dest / "prior-bundle").exists()
    assert not (dest / "prior-bag").exists()
    # no raw capture bytes, fixity hashes, or capture URLs anywhere in the tree
    for secret in (SHA, "<html>study</html>", "https://example.com/study"):
        leaked = [
            p for p in dest.rglob("*")
            if p.is_file() and secret in p.read_text(encoding="utf-8", errors="ignore")
        ]
        assert leaked == [], secret


def test_export_never_mutates_the_notebook(tmp_path):
    # generated views (index.md bodies, log.md) are excluded: regenerating
    # them before export is sanctioned (SPEC §10); everything else is not
    nb = make_notebook(tmp_path / "nb", trail=False)

    def snapshot():
        return {
            p.relative_to(nb): sha256_file(p)
            for p in nb.rglob("*")
            if p.is_file() and p.name not in ("index.md", "log.md")
        }

    before = snapshot()
    export_okf(nb, tmp_path / "bundle")
    assert snapshot() == before


# -- source trail withheld ---------------------------------------------------


def test_source_trail_stripped_when_not_public(tmp_path):
    nb = make_notebook(tmp_path / "nb", trail=False)
    dest = export_okf(nb, tmp_path / "bundle")
    page = pages.read_page(dest / "references" / "vendor-study.md")
    for key in ("local", "resource", "url", "date", "authors", "publisher",
                "title", "description"):
        assert key not in page.fm, key
    # the judgment still ships, as do identity and foreign keys
    assert page.fm["grade"] == "B"
    assert page.fm["independence"] == "original"
    assert page.fm["freshness"] == "fresh"
    assert page.fm["status"] == "captured"
    assert page.fm["id"] == "A1"
    assert page.fm["aliases"] == ["A1"]
    assert page.fm["obsidian_extra"] == "survives"
    text = (dest / "references" / "vendor-study.md").read_text(encoding="utf-8")
    assert "https://example.com/study" not in text
    assert "Capture notes worth keeping" not in text  # body replaced by the stub
    assert "# A1" in text  # the stub is headed by the id, not the title
    assert "withheld by notebook policy" in text
    assert SHA not in text


def test_stripped_export_withholds_titles_and_notes_tree_wide(tmp_path):
    # capture notes travel via `description`, private basenames via `title`
    # (on the page AND in the copied references/index.md listing): neither
    # may appear anywhere in a stripped export
    nb = make_notebook(tmp_path / "nb", trail=False)
    dest = export_okf(nb, tmp_path / "bundle")
    for secret in (
        "single-vendor conversion study",  # A1's capture note (description)
        "Capture notes worth keeping",  # A1's page body
        "Enrollment table",  # F1's title — the captured file's name
        "Vendor study",  # A1's title on the page and in the listing
    ):
        leaked = [
            p.relative_to(dest).as_posix()
            for p in dest.rglob("*")
            if p.is_file() and secret in p.read_text(encoding="utf-8", errors="ignore")
        ]
        # the claim's # Citations label is claim-author prose copied verbatim,
        # not capture metadata — reference pages and listings must be clean
        assert [p for p in leaked if not p.startswith("claims/")] == [], secret


def test_stripped_export_regenerates_references_index(tmp_path):
    nb = make_notebook(tmp_path / "nb", trail=False)
    dest = export_okf(nb, tmp_path / "bundle")
    listing = (dest / "references" / "index.md").read_text(encoding="utf-8")
    assert listing.splitlines()[0] == "# References"
    assert "* [F1](enrollment-table.md) - grade A" in listing
    assert "* [A1](vendor-study.md) - grade B" in listing
    assert "Vendor study" not in listing  # id as label, not the title
    assert "single-vendor conversion study" not in listing  # no capture note


# -- source trail shipped ----------------------------------------------------


def test_full_trail_ships_custody_and_fixity(tmp_path):
    nb = make_notebook(tmp_path / "nb", trail=True)
    dest = export_okf(nb, tmp_path / "bundle")
    # sources/ and log/ ship wholesale, ledgers included
    assert (dest / "sources" / "raw" / "A1" / "page.html").is_file()
    assert (dest / "sources" / "text" / "A1.md").is_file()
    assert (dest / "sources" / "_provenance.jsonl").read_bytes() == (
        nb / "sources" / "_provenance.jsonl"
    ).read_bytes()
    assert (dest / "log" / "log.jsonl").is_file()
    assert (dest / "log" / "passed.jsonl").is_file()
    # the reference page keeps its trail and gains fixity from provenance
    page = pages.read_page(dest / "references" / "vendor-study.md")
    assert page.fm["resource"] == "https://example.com/study"
    assert page.fm["local"] == "sources/raw/A1/page.html"
    assert page.fm["sha256"] == SHA
    assert page.fm["retrieved_at"] == "2026-07-09T10:00:00Z"
    assert page.fm["captured_with"] == "single-file"
    assert page.fm["obsidian_extra"] == "survives"
    assert "Capture notes worth keeping." in page.body
    # a source with no provenance event copies byte-identical
    assert (dest / "references" / "enrollment-table.md").read_bytes() == (
        nb / "references" / "enrollment-table.md"
    ).read_bytes()


def test_full_trail_fixity_matches_the_local_file(tmp_path):
    # a multi-file capture logs one provenance event per file; the page's
    # sha256 must describe the file `local` points at, not whichever event
    # happens to be last in the ledger
    nb = make_notebook(tmp_path / "nb", trail=True)
    other_sha = "cd" * 32
    (nb / "sources" / "raw" / "A1" / "z-extra.json").write_text("{}", encoding="utf-8")
    append_jsonl(
        nb / "sources" / "_provenance.jsonl",
        {"ts": "2026-07-09T10:00:01Z", "source_id": "A1",
         "url": "https://example.com/study",
         "local_path": "sources/raw/A1/z-extra.json", "sha256": other_sha,
         "bytes": 2, "tool": "single-file", "actor": "agent:test"},
    )
    dest = export_okf(nb, tmp_path / "bundle")
    page = pages.read_page(dest / "references" / "vendor-study.md")
    assert page.fm["local"] == "sources/raw/A1/page.html"
    assert page.fm["sha256"] == SHA  # the page.html event, not the latest one


def test_full_trail_fixity_falls_back_to_latest_event(tmp_path):
    # no event matches `local` (e.g. a recapture moved the file): latest wins
    nb = make_notebook(tmp_path / "nb", trail=True)
    page_path = nb / "references" / "vendor-study.md"
    page = pages.read_page(page_path)
    page.fm["local"] = "sources/raw/A1/renamed.html"
    pages.write_page(page_path, page.fm, page.body)
    (nb / "sources" / "raw" / "A1" / "renamed.html").write_text("x", encoding="utf-8")
    dest = export_okf(nb, tmp_path / "bundle")
    assert pages.read_page(dest / "references" / "vendor-study.md").fm["sha256"] == SHA


def test_include_private_implies_full_trail(tmp_path):
    nb = make_notebook(tmp_path / "nb", visibility="private", trail=False)
    dest = export_okf(nb, tmp_path / "bundle", include_private=True)
    assert (dest / "sources" / "_provenance.jsonl").is_file()
    assert pages.read_page(dest / "references" / "vendor-study.md").fm["sha256"] == SHA


def test_full_trail_export_is_deterministic(tmp_path):
    nb = make_notebook(tmp_path / "nb", trail=True)
    first = export_okf(nb, tmp_path / "bundle")
    page1 = (first / "references" / "vendor-study.md").read_bytes()
    second = export_okf(nb, tmp_path / "bundle")
    assert (second / "references" / "vendor-study.md").read_bytes() == page1


# -- re-export ---------------------------------------------------------------


def test_reexport_regenerates_and_drops_orphans(tmp_path):
    nb = make_notebook(tmp_path / "nb")
    dest = export_okf(nb, tmp_path / "bundle")
    assert (dest / "claims" / "conversion-42.md").is_file()
    # remove the claim from the notebook; re-export must drop its page
    # (the regenerated claims/index.md listing may remain, without the entry)
    (nb / "claims" / "conversion-42.md").unlink()
    dest2 = export_okf(nb, tmp_path / "bundle")
    assert dest2 == dest
    assert not (dest / "claims" / "conversion-42.md").exists()
    if (dest / "claims" / "index.md").exists():
        listing = (dest / "claims" / "index.md").read_text(encoding="utf-8")
        assert "conversion-42" not in listing
    # a random pre-existing dir refuses to be clobbered
    other = tmp_path / "other"
    other.mkdir()
    (other / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="not a previous flip OKF export"):
        export_okf(nb, other)
    assert (other / "keep.txt").is_file()


def test_state_file_names_the_notebook(tmp_path):
    import json

    nb = make_notebook(tmp_path / "nb")
    dest = export_okf(nb, tmp_path / "bundle")
    state = json.loads((dest / STATE_FILE).read_text(encoding="utf-8"))
    assert state["notebook"] == "demo"
    assert state["tool"].startswith("flip ")
    assert state["generated_at"]


# -- announce ----------------------------------------------------------------


def test_announce_appends_and_replaces_marker_block(tmp_path):
    nb = make_notebook(tmp_path / "nb")
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# My repo\n\nexisting text\n", encoding="utf-8")
    export_okf(nb, tmp_path / "bundle", announce=agents)
    text = agents.read_text(encoding="utf-8")
    assert text.count(MARKER_START) == 1 and "existing text" in text
    assert "bundle/index.md" in text
    # idempotent: announcing again replaces, not duplicates
    export_okf(nb, tmp_path / "bundle", announce=agents)
    text = agents.read_text(encoding="utf-8")
    assert text.count(MARKER_START) == 1 and text.count(MARKER_END) == 1
