"""Tests for flip.export: BagIt bags, CSL-JSON mapping from source pages."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from flip import pages
from flip.export import export_bag, export_csl
from flip.util import sha256_file, today

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: demo
title: Demo
kind: scout
status: active
created: 2026-07-09
updated: 2026-07-10
---
# Demo
"""

# One frontmatter dict per source page (SPEC §5.3); filename = slug.
SOURCE_PAGES = {
    "a-paper": {
        "type": "Source", "id": "P1", "aliases": ["P1"], "title": "A Paper",
        "authors": ["Ada Lovelace", "Alan Turing"], "date": "2025-11-23",
        "publisher": "Journal of X", "resource": "https://example.org/p1",
        "local": "sources/raw/P1.pdf", "grade": "A", "independence": "original",
        "freshness": "fresh", "status": "captured", "kind": "paper",
    },
    "a-web-page": {
        "type": "Source", "id": "A1", "aliases": ["A1"], "title": "A Web Page",
        "date": "2025-11", "resource": "https://example.org/a1",
        "local": "sources/raw/A1.html", "grade": "B", "independence": "republisher",
        "freshness": "dated", "status": "captured", "kind": "web",
    },
    "numbers": {
        # grade "?" is custody, not judgment — must contribute no note;
        # "circa 2020" is unparseable — no issued
        "type": "Source", "id": "F1", "aliases": ["F1"], "title": "Numbers",
        "date": "circa 2020", "local": "sources/raw/F1.csv", "grade": "?",
        "status": "captured", "kind": "dataset",
    },
    "a-talk": {
        "type": "Source", "id": "T1", "aliases": ["T1"], "title": "A Talk",
        "date": "2024", "local": "sources/raw/T1.txt", "status": "captured",
        "kind": "talk",
    },
    "an-article": {
        # kind "article" is a captured web article → webpage, not document
        "type": "Source", "id": "A2", "aliases": ["A2"], "title": "An Article",
        "local": "sources/raw/A2.html", "status": "captured", "kind": "article",
    },
    "a-screenshot": {
        # unmapped kind and S-prefixed id → document
        "type": "Source", "id": "S1", "aliases": ["S1"], "title": "A Screenshot",
        "local": "sources/raw/S1.png", "status": "captured", "kind": "screenshot",
    },
}


def make_notebook(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    (root / "notebook.md").write_text(
        "---\ntype: Notebook\ndescription: Demo\n---\n\n# demo\n\nworking memory\n",
        encoding="utf-8",
    )
    for slug, fm in SOURCE_PAGES.items():
        pages.write_page(root / "references" / f"{slug}.md", dict(fm), f"# {fm['title']}\n")
    (root / "sources" / "raw").mkdir(parents=True)
    (root / "sources" / "raw" / "A1.html").write_text("<html>hello</html>", encoding="utf-8")
    (root / "sources" / "text").mkdir()
    (root / "sources" / "text" / "A1.md").write_text("hello\n", encoding="utf-8")
    # content that must NOT reach a bag payload
    for junk in (".git", ".venv", ".flip", "renders", "__pycache__"):
        (root / junk).mkdir()
        (root / junk / "junk.txt").write_text("no\n", encoding="utf-8")
    (root / "sources" / "__pycache__").mkdir()
    (root / "sources" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    return root


def bag_payload_files(dest: Path) -> list[Path]:
    data = dest / "data"
    return sorted(
        Path(dirpath, name).relative_to(data)
        for dirpath, _dirs, files in os.walk(data)
        for name in files
    )


# -- export_bag ----------------------------------------------------------


def test_export_bag_structure_and_exclusions(tmp_path):
    root = make_notebook(tmp_path / "nb")
    dest = export_bag(root, tmp_path / "bag")

    assert dest == tmp_path / "bag"
    assert (dest / "bagit.txt").read_text(encoding="utf-8") == (
        "BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n"
    )
    rels = {p.as_posix() for p in bag_payload_files(dest)}
    assert rels == {
        "index.md",
        "notebook.md",
        *(f"references/{slug}.md" for slug in SOURCE_PAGES),
        "sources/raw/A1.html",
        "sources/text/A1.md",
    }
    # excluded dirs never copied, even nested ones
    for junk in (".git", ".venv", ".flip", "renders", "__pycache__"):
        assert not (dest / "data" / junk).exists()
    assert not (dest / "data" / "sources" / "__pycache__").exists()


def test_export_bag_checksums_verify(tmp_path):
    root = make_notebook(tmp_path / "nb")
    dest = export_bag(root, tmp_path / "bag")

    lines = (dest / "manifest-sha256.txt").read_text(encoding="utf-8").splitlines()
    assert lines  # at least index.md
    listed = set()
    for line in lines:
        digest, rel = line.split("  ", 1)  # two-space separator per BagIt
        assert rel.startswith("data/")
        payload = dest / rel
        assert payload.is_file()
        assert sha256_file(payload) == digest
        # payload bytes match the notebook original
        assert payload.read_bytes() == (root / rel.removeprefix("data/")).read_bytes()
        listed.add(rel.removeprefix("data/"))
    # every payload file is listed, and nothing else
    assert listed == {p.as_posix() for p in bag_payload_files(dest)}


def test_export_bag_info_oxum_and_date(tmp_path):
    root = make_notebook(tmp_path / "nb")
    dest = export_bag(root, tmp_path / "bag")

    info = dict(
        line.split(": ", 1)
        for line in (dest / "bag-info.txt").read_text(encoding="utf-8").splitlines()
    )
    assert info["Bagging-Date"] == today()
    files = bag_payload_files(dest)
    total = sum((dest / "data" / p).stat().st_size for p in files)
    assert info["Payload-Oxum"] == f"{total}.{len(files)}"


def test_export_bag_refuses_existing_dest(tmp_path):
    root = make_notebook(tmp_path / "nb")
    dest = tmp_path / "bag"
    dest.mkdir()
    with pytest.raises(SystemExit, match="already exists"):
        export_bag(root, dest)


def test_export_bag_requires_notebook(tmp_path):
    not_a_notebook = tmp_path / "empty"
    not_a_notebook.mkdir()
    with pytest.raises(SystemExit, match="not a flip notebook"):
        export_bag(not_a_notebook, tmp_path / "bag")


def test_export_bag_materializes_dir_symlink_content(tmp_path):
    # drafts/current -> v1 must appear in the bag as a full copy under the
    # link's name — the current-draft pointer survives cold storage.
    root = make_notebook(tmp_path / "nb")
    v1 = root / "drafts" / "v1"
    v1.mkdir(parents=True)
    (v1 / "draft.md").write_text("the draft\n", encoding="utf-8")
    (root / "drafts" / "current").symlink_to("v1", target_is_directory=True)

    dest = export_bag(root, tmp_path / "bag")

    current_copy = dest / "data" / "drafts" / "current" / "draft.md"
    assert current_copy.is_file() and not current_copy.is_symlink()
    assert current_copy.read_text(encoding="utf-8") == "the draft\n"
    # the target version is present too (deliberate duplication)
    assert (dest / "data" / "drafts" / "v1" / "draft.md").is_file()
    manifest = (dest / "manifest-sha256.txt").read_text(encoding="utf-8")
    assert "data/drafts/current/draft.md" in manifest


def test_export_bag_resolves_file_symlink_content(tmp_path):
    root = make_notebook(tmp_path / "nb")
    (root / "HANDOFF.md").write_text("handoff\n", encoding="utf-8")
    (root / "latest.md").symlink_to("HANDOFF.md")

    dest = export_bag(root, tmp_path / "bag")

    copied = dest / "data" / "latest.md"
    assert copied.is_file() and not copied.is_symlink()
    assert copied.read_text(encoding="utf-8") == "handoff\n"


def test_export_bag_skips_dangling_symlink_with_warning(tmp_path, capsys):
    root = make_notebook(tmp_path / "nb")
    (root / "gone.md").symlink_to("no-such-target.md")

    dest = export_bag(root, tmp_path / "bag")

    assert not (dest / "data" / "gone.md").exists()
    err = capsys.readouterr().err
    assert "dangling symlink" in err and "gone.md" in err
    # the bag is otherwise complete and consistent
    assert (dest / "data" / "index.md").is_file()


def test_export_bag_failure_removes_partial_bag(tmp_path, monkeypatch):
    import flip.export as export_mod

    root = make_notebook(tmp_path / "nb")
    calls = {"n": 0}
    real_copy2 = export_mod.shutil.copy2

    def flaky_copy2(src, dst, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("disk full (simulated)")
        return real_copy2(src, dst, **kw)

    monkeypatch.setattr(export_mod.shutil, "copy2", flaky_copy2)
    dest = tmp_path / "bag"
    with pytest.raises(SystemExit) as ei:
        export_bag(root, dest)
    assert "disk full" in str(ei.value)
    assert str(dest) in str(ei.value)
    assert not dest.exists()  # partial bag removed; retry starts clean


def test_export_bag_does_not_mutate_notebook(tmp_path):
    root = make_notebook(tmp_path / "nb")
    before = {
        p.relative_to(root): sha256_file(p) for p in root.rglob("*") if p.is_file()
    }
    export_bag(root, tmp_path / "bag")
    after = {
        p.relative_to(root): sha256_file(p) for p in root.rglob("*") if p.is_file()
    }
    assert before == after


# -- export_csl ----------------------------------------------------------


def test_export_csl_maps_fields(tmp_path):
    root = make_notebook(tmp_path / "nb")
    items = {i["id"]: i for i in export_csl(root)}

    p1 = items["P1"]
    assert p1["type"] == "article-journal"
    assert p1["title"] == "A Paper"
    assert p1["author"] == [{"literal": "Ada Lovelace"}, {"literal": "Alan Turing"}]
    assert p1["issued"] == {"date-parts": [[2025, 11, 23]]}
    assert p1["URL"] == "https://example.org/p1"
    assert p1["publisher"] == "Journal of X"
    assert p1["note"] == "grade: A; independence: original; freshness: fresh"

    a1 = items["A1"]
    assert a1["type"] == "webpage"
    assert a1["issued"] == {"date-parts": [[2025, 11]]}  # partial date kept
    assert a1["note"] == "grade: B; independence: republisher; freshness: dated"

    assert items["F1"]["type"] == "dataset"
    assert "issued" not in items["F1"]  # unparseable date omitted
    assert "author" not in items["F1"]  # no authors → no author key
    assert "note" not in items["F1"]  # grade "?" is custody, not judgment

    assert items["T1"]["type"] == "speech"
    assert items["T1"]["issued"] == {"date-parts": [[2024]]}

    assert items["A2"]["type"] == "webpage"  # kind "article" is a web capture
    assert items["S1"]["type"] == "document"  # unmapped kind falls back


def test_export_csl_items_in_id_order(tmp_path):
    root = make_notebook(tmp_path / "nb")
    assert [i["id"] for i in export_csl(root)] == ["A1", "A2", "F1", "P1", "S1", "T1"]


def test_export_csl_kind_falls_back_to_id_prefix(tmp_path):
    # a foreign-authored page with no `kind` key still types via its id prefix
    root = make_notebook(tmp_path / "nb")
    pages.write_page(
        root / "references" / "prefix-only.md",
        {"type": "Source", "id": "P9", "aliases": ["P9"], "title": "Prefixless"},
        "# Prefixless\n",
    )
    pages.write_page(
        root / "references" / "odd-id.md",
        {"type": "Source", "id": "X1", "aliases": ["X1"], "title": "Odd"},
        "# Odd\n",
    )
    items = {i["id"]: i for i in export_csl(root)}
    assert items["P9"]["type"] == "article-journal"
    assert items["X1"]["type"] == "document"


def test_export_csl_scalar_authors_is_one_literal(tmp_path):
    # a hand-edited `authors: Jane Doe` is one author, not eight
    # one-character CSL literals
    root = make_notebook(tmp_path / "nb")
    pages.write_page(
        root / "references" / "solo.md",
        {"type": "Source", "id": "A8", "aliases": ["A8"], "title": "Solo",
         "authors": "Jane Doe", "kind": "web"},
        "# Solo\n",
    )
    items = {i["id"]: i for i in export_csl(root)}
    assert items["A8"]["author"] == [{"literal": "Jane Doe"}]


def test_export_bag_excludes_dot_dirs_and_ids_file(tmp_path):
    # .flip (including the .flip/ids reservation file) never reaches a bag
    root = make_notebook(tmp_path / "nb")
    (root / ".flip" / "ids").write_text("F1\n", encoding="utf-8")
    dest = export_bag(root, tmp_path / "bag")
    assert not (dest / "data" / ".flip").exists()
    manifest = (dest / "manifest-sha256.txt").read_text(encoding="utf-8")
    assert ".flip" not in manifest


def test_export_csl_url_key_also_accepted(tmp_path):
    # migrated/foreign pages may carry `url` instead of SPEC §5.3's `resource`
    root = make_notebook(tmp_path / "nb")
    pages.write_page(
        root / "references" / "urlful.md",
        {"type": "Source", "id": "A9", "aliases": ["A9"], "title": "Urlful",
         "url": "https://example.org/a9", "kind": "web"},
        "# Urlful\n",
    )
    items = {i["id"]: i for i in export_csl(root)}
    assert items["A9"]["URL"] == "https://example.org/a9"


def test_export_csl_no_references_returns_empty(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    assert export_csl(root) == []


def test_export_csl_requires_notebook(tmp_path):
    with pytest.raises(SystemExit, match="not a flip notebook"):
        export_csl(tmp_path)


def test_export_csl_bad_page_is_actionable(tmp_path):
    root = make_notebook(tmp_path / "nb")
    (root / "references" / "broken.md").write_text(
        '---\ntype: Source\nid: "unclosed\n---\n# broken\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="broken.md"):
        export_csl(root)
