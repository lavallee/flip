"""Tests for flip.export: BagIt bags, CSL-JSON mapping, OKF stub."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from flip.export import export_bag, export_csl
from flip.util import sha256_file, today, write_jsonl

LEDGER = [
    {
        "id": "P1",
        "kind": "paper",
        "title": "A Paper",
        "authors": ["Ada Lovelace", "Alan Turing"],
        "date": "2025-11-23",
        "publisher": "Journal of X",
        "url": "https://example.org/p1",
        "local": "sources/raw/P1.pdf",
        "grade": "A",
        "independence": "original",
        "freshness": "fresh",
        "status": "captured",
        "supports": ["C1"],
    },
    {
        "id": "A1",
        "kind": "web",
        "title": "A Web Page",
        "date": "2025-11",
        "url": "https://example.org/a1",
        "local": "sources/raw/A1.html",
        "grade": "B",
        "independence": "republisher",
        "freshness": "dated",
        "status": "captured",
        "supports": [],
    },
    {
        "id": "F1",
        "kind": "dataset",
        "title": "Numbers",
        "date": "circa 2020",  # unparseable → no issued
        "local": "sources/raw/F1.csv",
        "status": "captured",
        "supports": [],
    },
    {
        "id": "T1",
        "kind": "talk",
        "title": "A Talk",
        "date": "2024",
        "local": "sources/raw/T1.txt",
        "status": "captured",
        "supports": [],
    },
    {
        "id": "A2",
        "kind": "article",  # captured web article → webpage, not document
        "title": "An Article",
        "local": "sources/raw/A2.html",
        "status": "captured",
        "supports": [],
    },
    {
        "id": "S1",
        "kind": "screenshot",  # unmapped kind → document
        "title": "A Screenshot",
        "local": "sources/raw/S1.png",
        "status": "captured",
        "supports": [],
    },
]


def make_notebook(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "notebook.toml").write_text(
        'slug = "demo"\ntitle = "Demo"\nkind = "scout"\nstatus = "active"\n'
        'created = "2026-07-09"\nupdated = "2026-07-10"\n',
        encoding="utf-8",
    )
    (root / "notebook.md").write_text("# demo\n\nworking memory\n", encoding="utf-8")
    (root / "sources" / "raw").mkdir(parents=True)
    (root / "sources" / "raw" / "A1.html").write_text("<html>hello</html>", encoding="utf-8")
    (root / "sources" / "text").mkdir()
    (root / "sources" / "text" / "A1.md").write_text("hello\n", encoding="utf-8")
    write_jsonl(root / "sources" / "ledger.jsonl", LEDGER)
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
        "notebook.toml",
        "notebook.md",
        "sources/ledger.jsonl",
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
    assert lines  # at least notebook.toml
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
    with pytest.raises(SystemExit, match="notebook.toml"):
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
    assert (dest / "data" / "notebook.toml").is_file()


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
    assert "note" not in items["F1"]  # no judgments recorded → no note

    assert items["T1"]["type"] == "speech"
    assert items["T1"]["issued"] == {"date-parts": [[2024]]}

    assert items["A2"]["type"] == "webpage"  # ledger kind "article" is a web capture
    assert items["S1"]["type"] == "document"  # unmapped kind falls back


def test_export_csl_file_kind_maps_to_dataset(tmp_path):
    root = make_notebook(tmp_path / "nb")
    write_jsonl(
        root / "sources" / "ledger.jsonl",
        [{"id": "F2", "kind": "file", "title": "Blob", "local": "sources/raw/F2.bin"}],
    )
    (item,) = export_csl(root)
    assert item["type"] == "dataset"


def test_export_csl_no_ledger_returns_empty(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text('slug = "bare"\nkind = "ledger"\n', encoding="utf-8")
    assert export_csl(root) == []


def test_export_csl_requires_notebook(tmp_path):
    with pytest.raises(SystemExit, match="notebook.toml"):
        export_csl(tmp_path)


def test_export_csl_bad_ledger_line_is_actionable(tmp_path):
    root = make_notebook(tmp_path / "nb")
    with open(root / "sources" / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write("{not json\n")
    with pytest.raises(SystemExit, match="ledger"):
        export_csl(root)


# -- export_okf: behavior lives in okf.py and is tested in tests/test_okf.py --
