"""OKF export tests — bundle shape, conformance basics, policy gates, announce."""

from pathlib import Path

import pytest

from flip.okf import MARKER_END, MARKER_START, export_okf
from flip.util import append_jsonl, write_jsonl


def make_notebook(root: Path, visibility: str = "public", trail: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "notebook.toml").write_text(
        f'slug = "demo"\ntitle = "Demo notebook"\nkind = "scout"\nstatus = "active"\n'
        f'created = "2026-07-01"\nupdated = "2026-07-10"\n\n'
        f'[policy]\nvisibility = "{visibility}"\n'
        f"source_trail_public = {'true' if trail else 'false'}\n",
        encoding="utf-8",
    )
    (root / "notebook.md").write_text("# Reporter's notebook — Demo\n", encoding="utf-8")
    write_jsonl(
        root / "sources" / "ledger.jsonl",
        [
            {
                "id": "A1", "kind": "web", "title": "Vendor study",
                "url": "https://example.com/study", "local": "sources/raw/A1/page.html",
                "grade": "B", "independence": "original", "freshness": "fresh",
                "status": "captured", "supports": ["C1"], "date": "2025-11-01",
            },
            {
                "id": "F1", "kind": "file", "title": "Enrollment table",
                "local": "sources/raw/F1.csv", "grade": "A",
                "independence": "original", "freshness": "fresh",
                "status": "captured", "supports": [],
            },
        ],
    )
    append_jsonl(
        root / "sources" / "_provenance.jsonl",
        {"ts": "2026-07-09T10:00:00Z", "source_id": "A1", "url": "https://example.com/study",
         "local_path": "sources/raw/A1/page.html", "sha256": "ab" * 32, "bytes": 100,
         "tool": "single-file", "actor": "agent:test"},
    )
    write_jsonl(
        root / "analysis" / "claims.jsonl",
        [{"id": "C1", "text": "Conversion is 42% higher", "status": "needs-2nd",
          "load_bearing": True, "sources": ["A1"], "independent_corroboration": 1,
          "first_asserted": "2026-07-09", "actor": "agent:test"}],
    )
    append_jsonl(
        root / "log" / "decisions.jsonl",
        {"ts": "2026-07-09T11:00:00Z", "id": "D1", "question": "Scope?",
         "decision": "Vendor claims only", "why": "time-boxed",
         "alternatives_rejected": ["full market survey"], "actor": "human:test"},
    )
    append_jsonl(root / "log" / "log.jsonl",
                 {"ts": "2026-07-08T09:00:00Z", "text": "started", "actor": "human:test"})
    append_jsonl(root / "log" / "log.jsonl",
                 {"ts": "2026-07-09T09:00:00Z", "text": "captured A1", "actor": "agent:test"})
    return root


def frontmatter_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name} lacks frontmatter"
    return text.split("---\n", 2)[1]


def test_bundle_shape_and_conformance(tmp_path):
    nb = make_notebook(tmp_path / "nb")
    dest = export_okf(nb, tmp_path / "bundle")
    # every non-reserved .md is a concept with a type
    for md in dest.rglob("*.md"):
        if md.name in ("index.md", "log.md"):
            continue
        assert "type:" in frontmatter_of(md), md
    # root index carries the version + identity slot
    fm = frontmatter_of(dest / "index.md")
    assert 'okf_version: "0.1"' in fm
    assert "notebook: demo" in fm
    assert "generated_by:" in fm
    # sections listed in the * [Title](url) - description shape
    body = (dest / "index.md").read_text(encoding="utf-8")
    assert "* [References](references/) - " in body
    assert "* [Claims](claims/) - " in body
    assert "* [Decisions](decisions/) - " in body
    assert (dest / ".last-export.json").is_file()


def test_reference_custody_frontmatter(tmp_path):
    nb = make_notebook(tmp_path / "nb")
    dest = export_okf(nb, tmp_path / "bundle")
    fm = frontmatter_of(dest / "references" / "A1.md")
    assert "type: Source" in fm
    assert "sha256:" in fm and "ab" * 32 in fm
    assert "grade: B" in fm
    assert 'resource: "https://example.com/study"' in fm  # quoted: URL contains ':'


def test_claim_citations_link_references(tmp_path):
    nb = make_notebook(tmp_path / "nb")
    dest = export_okf(nb, tmp_path / "bundle")
    page = (dest / "claims" / "C1.md").read_text(encoding="utf-8")
    assert "# Citations" in page
    assert "[1] [Vendor study](/references/A1.md)" in page
    fm = frontmatter_of(dest / "claims" / "C1.md")
    assert "supports: [/references/A1]" in fm
    assert "load_bearing: true" in fm


def test_log_md_newest_first(tmp_path):
    nb = make_notebook(tmp_path / "nb")
    dest = export_okf(nb, tmp_path / "bundle")
    log = (dest / "log.md").read_text(encoding="utf-8")
    assert log.index("## 2026-07-09") < log.index("## 2026-07-08")
    assert "* **Update**: captured A1" in log


def test_policy_gate_refuses_internal(tmp_path):
    nb = make_notebook(tmp_path / "nb", visibility="internal")
    with pytest.raises(SystemExit, match="visibility"):
        export_okf(nb, tmp_path / "bundle")
    # include_private overrides
    dest = export_okf(nb, tmp_path / "bundle", include_private=True)
    assert (dest / "index.md").is_file()


def test_source_trail_stripped_when_not_public(tmp_path):
    nb = make_notebook(tmp_path / "nb", visibility="public", trail=False)
    dest = export_okf(nb, tmp_path / "bundle")
    page = (dest / "references" / "A1.md").read_text(encoding="utf-8")
    assert "sha256" not in page
    assert "https://example.com/study" not in page
    assert "grade: B" in page  # the judgment still ships
    assert "withheld by notebook policy" in page


def test_reexport_regenerates_and_drops_orphans(tmp_path):
    nb = make_notebook(tmp_path / "nb")
    dest = export_okf(nb, tmp_path / "bundle")
    # remove the claim from the notebook; re-export must drop its page
    write_jsonl(nb / "analysis" / "claims.jsonl", [])
    dest2 = export_okf(nb, tmp_path / "bundle")
    assert dest2 == dest
    assert not (dest / "claims").exists()
    # a random pre-existing dir refuses to be clobbered
    other = tmp_path / "other"
    other.mkdir()
    (other / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit, match="not a previous flip OKF export"):
        export_okf(nb, other)


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
