"""Tests for flip.export: BagIt bags, CSL-JSON mapping from source pages, and
the flip-render/1 JSON projection (Lane F)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from flip import pages
from flip.export import RENDER_CONTRACT, export_bag, export_csl, export_json
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


def test_export_bag_payload_carries_uid_and_origin(tmp_path):
    # uid/origin live in the root index.md frontmatter, so the bag payload
    # carries them for free — lineage survives cold storage (SPEC §17)
    root = tmp_path / "nb"
    root.mkdir()
    (root / "index.md").write_text(
        "---\n"
        'okf_version: "0.1"\n'
        'flip: "0.5"\n'
        "slug: orchard-survey\n"
        "uid: nb-7k3m9p2x\n"
        "title: Orchard survey\n"
        "kind: scout\n"
        "status: active\n"
        "origin: /shared/orchard-survey (imported 2026-07-01)\n"
        "---\n"
        "# Orchard survey\n",
        encoding="utf-8",
    )
    dest = export_bag(root, tmp_path / "bag")
    fm = pages.read_page(dest / "data" / "index.md").fm
    assert fm["uid"] == "nb-7k3m9p2x"
    assert fm["origin"] == "/shared/orchard-survey (imported 2026-07-01)"
    # byte-identical copy: the bag never rewrites the manifest
    assert (dest / "data" / "index.md").read_bytes() == (root / "index.md").read_bytes()


def test_export_bag_excludes_workspace_toml(tmp_path):
    # handles are importer-owned petnames: the workspace table (like the whole
    # of .flip/) never ships inside a bundle
    root = make_notebook(tmp_path / "nb")
    (root / ".flip" / "workspace.toml").write_text(
        '[workspace]\nversion = "0.1"\n\n[notebooks]\nrecipes = "recipes"\n',
        encoding="utf-8",
    )
    dest = export_bag(root, tmp_path / "bag")
    assert not (dest / "data" / ".flip").exists()
    manifest = (dest / "manifest-sha256.txt").read_text(encoding="utf-8")
    assert "workspace.toml" not in manifest


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


# -- export_json (flip-render/1) -----------------------------------------------


def make_render_notebook(root: Path, visibility="public", trail_public=False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.md").write_text(
        "---\n"
        'okf_version: "0.1"\n'
        'flip: "0.6"\n'
        "slug: demo\n"
        "uid: nb-abcd0000\n"
        "title: Demo\n"
        "kind: research-review\n"
        "status: active\n"
        "created: 2026-07-01\n"
        "updated: 2026-07-02\n"
        f"visibility: {visibility}\n"
        f"source_trail_public: {'true' if trail_public else 'false'}\n"
        "---\n# Demo\n",
        encoding="utf-8",
    )
    pages.write_page(
        root / "references" / "a1.md",
        {"type": "Source", "id": "A1", "aliases": ["A1"], "title": "Secret Filing",
         "resource": "https://example.org/a1", "local": "sources/raw/A1.html",
         "grade": "A", "independence": "independent", "freshness": "fresh", "kind": "web"},
        "# Secret Filing\n",
    )
    prov = root / "sources" / "_provenance.jsonl"
    prov.parent.mkdir(parents=True, exist_ok=True)
    prov.write_text(
        json.dumps({"source_id": "A1", "local_path": "sources/raw/A1.html",
                    "sha256": "deadbeef", "ts": "2026-07-01T10:00:00Z", "tool": "flip-fetch"})
        + "\n",
        encoding="utf-8",
    )
    pages.write_page(
        root / "claims" / "c1.md",
        {"type": "Claim", "id": "C1", "aliases": ["C1"], "description": "key claim",
         "status": "verified", "load_bearing": True, "sources": ["A1"],
         "independent_corroboration": 1,
         "verified": [{"method": "adversarial", "by": "agent:x", "at": "2026-07-02T00:00:00Z"}]},
        "key claim\n",
    )
    pages.write_page(
        root / "questions" / "q1.md",
        {"type": "Question", "id": "Q1", "aliases": ["Q1"], "description": "who pays now?",
         "status": "open",
         "formulations": [{"text": "who pays?", "date": "2026-07-01", "actor": "human:t"}]},
        "who pays now?\n",
    )
    pages.write_page(
        root / "decisions" / "d1.md",
        {"type": "Decision", "id": "D1", "aliases": ["D1"], "description": "start with Essex",
         "question": "which county first?", "alternatives_rejected": ["start with Bergen"]},
        "body\n",
    )
    pages.write_page(
        root / "sessions" / "2026-07-01T1000-scan.md",
        {"type": "Work Session", "generated": {"by": "agent:x", "at": "2026-07-01T10:00:00Z"},
         "model": "m",
         "started": "2026-07-01T10:00:00Z", "ended": "2026-07-01T11:00:00Z"},
        "## Goal\nscan the landscape\n\n## Prompt\n",
    )
    log = root / "log" / "log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps({"ts": "2026-07-01T10:00:00Z", "text": "started", "actor": "agent:x"}) + "\n",
        encoding="utf-8",
    )
    return root


def test_export_json_refuses_non_public(tmp_path):
    root = make_render_notebook(tmp_path / "nb", visibility="internal")
    with pytest.raises(SystemExit, match="visibility is 'internal'"):
        export_json(root)


def test_export_json_include_private_overrides_visibility(tmp_path):
    root = make_render_notebook(tmp_path / "nb", visibility="internal")
    data = export_json(root, include_private=True)
    assert data["contract"] == RENDER_CONTRACT
    assert data["source_trail_public"] is True  # include_private ⇒ full trail


def test_export_json_notebook_identity_and_contract(tmp_path):
    data = export_json(make_render_notebook(tmp_path / "nb"))
    assert data["contract"] == "flip-render/1"
    assert "generated" in data
    assert data["notebook"] == {
        "uid": "nb-abcd0000", "slug": "demo", "title": "Demo",
        "kind": "research-review", "status": "active",
        "created": "2026-07-01", "updated": "2026-07-02", "visibility": "public",
    }


def test_export_json_projects_claims_questions_with_history(tmp_path):
    data = export_json(make_render_notebook(tmp_path / "nb", trail_public=True))
    claim = data["claims"][0]
    assert claim["id"] == "C1" and claim["text"] == "key claim"
    assert claim["load_bearing"] is True and claim["sources"] == ["A1"]
    assert claim["corroboration"] == 1  # recomputed: A1 is grade-A original
    assert claim["verifications"][0]["method"] == "adversarial"
    q = data["questions"][0]
    assert q["id"] == "Q1" and q["formulations"][0]["text"] == "who pays?"
    d = data["decisions"][0]
    assert d["id"] == "D1" and d["alternatives_rejected"] == ["start with Bergen"]
    s = data["sessions"][0]
    assert s["actor"] == "agent:x" and s["goal"] == "scan the landscape"
    assert s["ended"] == "2026-07-01T11:00:00Z"


def test_export_json_full_trail_carries_custody(tmp_path):
    root = make_render_notebook(tmp_path / "nb", trail_public=True)
    data = export_json(root)
    assert data["source_trail_public"] is True
    src = data["sources"][0]
    assert src["id"] == "A1"
    assert src["title"] == "Secret Filing"
    assert src["canonical_url"] == "https://example.org/a1"
    assert src["sha256"] == "deadbeef"
    assert src["captured_at"] == "2026-07-01T10:00:00Z"
    # the work log ships with the full trail
    assert [e["text"] for e in data["log_tail"]] == ["started"]


def test_export_json_stripped_trail_withholds_custody(tmp_path):
    # public notebook, source_trail_public: false — judgment ships, custody does not
    root = make_render_notebook(tmp_path / "nb", trail_public=False)
    data = export_json(root)
    assert data["source_trail_public"] is False
    src = data["sources"][0]
    assert src["grade"] == "A" and src["independence"] == "independent"
    assert src["freshness"] == "fresh" and src["kind"] == "web"
    for withheld in ("title", "canonical_url", "sha256", "captured_at"):
        assert withheld not in src, withheld
    # derived-from-withheld: the work log is withheld too (0.4 lesson)
    assert data["log_tail"] == []
    # but claims/questions — the notebook's judgments — still ship
    assert data["claims"][0]["id"] == "C1"
    assert data["questions"][0]["id"] == "Q1"


def test_export_json_stripped_trail_stubs_title_derived_source_slug(tmp_path):
    # A source slug is generated from its title: withholding the title while
    # shipping the slug would leak it (the 0.4 derived-from-withheld lesson).
    root = make_render_notebook(tmp_path / "nb", trail_public=False)
    pages.write_page(
        root / "references" / "secret-merger-memo.md",
        {"type": "Source", "id": "A2", "aliases": ["A2"],
         "title": "Secret merger memo", "grade": "B",
         "independence": "derivative", "freshness": "dated", "kind": "web"},
        "# Secret merger memo\n",
    )
    data = export_json(root)
    a2 = next(s for s in data["sources"] if s["id"] == "A2")
    assert a2["slug"] == "A2"  # stubbed to the id
    assert "secret-merger-memo" not in json.dumps(data)
    # with the full trail, the real slug ships
    make_render_notebook(tmp_path / "nb", trail_public=True)
    full = export_json(root)
    a2 = next(s for s in full["sources"] if s["id"] == "A2")
    assert a2["slug"] == "secret-merger-memo"


def test_export_json_stripped_trail_withholds_sessions(tmp_path):
    # session pages are the work log in entity form — goals and goal-derived
    # filename slugs are custody, withheld exactly like log_tail
    root = make_render_notebook(tmp_path / "nb", trail_public=False)
    assert export_json(root)["sessions"] == []
    make_render_notebook(tmp_path / "nb", trail_public=True)
    sessions = export_json(root)["sessions"]
    assert sessions and sessions[0]["goal"] == "scan the landscape"


def test_export_json_is_deterministic(tmp_path):
    root = make_render_notebook(tmp_path / "nb", trail_public=True)
    a = export_json(root)
    b = export_json(root)
    a.pop("generated"), b.pop("generated")  # the one intentionally-varying field
    assert json.dumps(a, sort_keys=False) == json.dumps(b, sort_keys=False)


def test_export_json_requires_notebook(tmp_path):
    with pytest.raises(SystemExit, match="not a flip notebook"):
        export_json(tmp_path)
