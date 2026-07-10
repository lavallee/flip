"""Tests for flip.sources: classification, capture, provenance, entity pages,
grading (round-trip rule), and id allocation over pages + provenance."""

import stat

import pytest

from flip import pages, sources
from flip.manifest import load_manifest
from flip.util import append_jsonl, read_jsonl, sha256_file

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: test-nb
kind: scout
status: active
created: 2026-01-01
updated: 2026-01-01
---
# test-nb
"""


def make_notebook(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    # resolve so Page.path comparisons hold when tmp_path crosses a symlink
    return root.resolve()


def make_fetcher(tmp_path, body):
    """Write an executable /bin/sh script; $1.. are the templated args."""
    script = tmp_path / "fakefetch"
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def make_flip_home(tmp_path, monkeypatch, fetchers=None):
    """Point FLIP_HOME at a tmp dir; write config.toml [fetchers] if given."""
    home = tmp_path / "fliphome"
    home.mkdir(exist_ok=True)
    if fetchers is not None:
        lines = ["[fetchers]"] + [f'{k} = "{v}"' for k, v in fetchers.items()]
        (home / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setenv("FLIP_HOME", str(home))
    return home


# --- classification -------------------------------------------------------


def test_classify_existing_path_is_file(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"x")
    assert sources._classify(str(f)) == "file"


def test_classify_urls_are_web():
    assert sources._classify("https://example.com/a") == "web"
    assert sources._classify("http://example.com/a") == "web"


def test_classify_dois_and_arxiv_are_paper():
    assert sources._classify("10.1234/abc.def-5") == "paper"
    assert sources._classify("doi:10.1234/abc") == "paper"
    assert sources._classify("2106.01234") == "paper"
    assert sources._classify("arXiv:2106.01234v2") == "paper"


def test_classify_unknown_is_actionable_error():
    with pytest.raises(SystemExit) as ei:
        sources._classify("some random words")
    assert "kind" in str(ei.value)


# --- builtin copy ---------------------------------------------------------


def test_builtin_copy_end_to_end(tmp_path):
    root = make_notebook(tmp_path)
    src = tmp_path / "report.pdf"
    payload = b"%PDF fake content"
    src.write_bytes(payload)

    page = sources.add_source(root, str(src), note="grabbed for test")

    fm = page.fm
    assert fm["type"] == "Source"
    assert fm["id"] == "F1"
    assert fm["aliases"] == ["F1"]
    assert fm["title"] == "report.pdf"
    assert fm["description"] == "grabbed for test"
    assert fm["local"] == "sources/raw/F1.pdf"
    assert fm["grade"] == "?"
    assert fm["independence"] == "original"
    assert fm["freshness"] == "fresh"
    assert fm["status"] == "captured"
    assert fm["actor"]
    assert "resource" not in fm  # local copies carry origin in provenance only

    # the page is the canonical record: on disk, human slug, heading + note body
    # (parse keeps the blank separator line after the frontmatter, hence lstrip)
    assert page.path == root / "references" / "report-pdf.md"
    on_disk = pages.read_page(page.path)
    assert on_disk.fm == fm
    assert on_disk.body.lstrip("\n").startswith("# report.pdf")
    assert "grabbed for test" in on_disk.body

    copied = root / "sources" / "raw" / "F1.pdf"
    assert copied.read_bytes() == payload

    events = read_jsonl(root / "sources" / "_provenance.jsonl")
    assert len(events) == 1
    ev = events[0]
    assert ev["source_id"] == "F1"
    assert ev["local_path"] == "sources/raw/F1.pdf"
    assert ev["sha256"] == sha256_file(copied)
    assert ev["bytes"] == len(payload)
    assert ev["tool"] == "builtin:copy"
    assert ev["strategy"] == "copy"
    assert ev["url"].startswith("file://")
    assert ev["actor"]
    assert ev["ts"].endswith("Z")
    assert ev["note"] == "grabbed for test"
    assert "tool_version" not in ev

    assert load_manifest(root).updated != "2026-01-01"


def test_copy_missing_file_errors(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as ei:
        sources.add_source(root, str(tmp_path / "nope.pdf"), kind="file")
    assert "no such file" in str(ei.value)


def test_copy_directory_target_errors(tmp_path):
    root = make_notebook(tmp_path)
    d = tmp_path / "somedir"
    d.mkdir()
    with pytest.raises(SystemExit) as ei:
        sources.add_source(root, str(d), kind="file")
    assert "directory" in str(ei.value)


def test_add_source_outside_notebook_errors(tmp_path):
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        sources.add_source(tmp_path / "not-a-notebook", "https://example.com")


# --- fetcher routing ------------------------------------------------------


def test_fetcher_end_to_end(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    script = make_fetcher(
        tmp_path,
        'if [ "$1" = "--version" ]; then echo "fakefetch 1.0 (test)"; exit 0; fi\n'
        'printf "big page content fetched from %s" "$1" > "$2/page.html"\n'
        'printf "{}" > "$2/meta.json"\n',
    )
    make_flip_home(tmp_path, monkeypatch, {"web": f"{script} {{url}} {{dest}}"})

    page = sources.add_source(root, "https://example.com/story")

    fm = page.fm
    assert fm["id"] == "A1"
    assert fm["title"] == "example.com/story"  # URL host+path names the page
    assert fm["description"] == "web source"
    assert fm["resource"] == "https://example.com/story"
    assert fm["local"] == "sources/raw/A1/page.html"  # the largest captured file
    assert page.path == root / "references" / "example-com-story.md"
    assert page.path.is_file()
    assert (root / "sources" / "raw" / "A1" / "meta.json").is_file()

    events = read_jsonl(root / "sources" / "_provenance.jsonl")
    assert {e["local_path"] for e in events} == {
        "sources/raw/A1/page.html",
        "sources/raw/A1/meta.json",
    }
    for e in events:
        assert e["source_id"] == "A1"
        assert e["url"] == "https://example.com/story"
        assert e["tool"] == str(script)
        assert e["tool_version"] == "fakefetch 1.0 (test)"
        assert e["strategy"] == "config"
        assert e["sha256"] == sha256_file(root / e["local_path"])
        assert e["bytes"] == (root / e["local_path"]).stat().st_size


def test_paper_fetcher_gets_bare_doi_via_id_placeholder(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    script = make_fetcher(tmp_path, 'printf "%s" "$1" > "$2/paper.txt"\n')
    make_flip_home(tmp_path, monkeypatch, {"paper": f"{script} {{id}} {{dest}}"})

    page = sources.add_source(root, "doi:10.1234/widgets.5")

    assert page.fm["id"] == "P1"
    assert page.fm["resource"] == "doi:10.1234/widgets.5"
    assert page.fm["title"] == "doi:10.1234/widgets.5"
    assert page.path.name == "doi-10-1234-widgets-5.md"
    captured = root / "sources" / "raw" / "P1" / "paper.txt"
    assert captured.read_text(encoding="utf-8") == "10.1234/widgets.5"


def test_config_routed_builtin_copy_and_prefixes(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    make_flip_home(tmp_path, monkeypatch, {"talk": "builtin:copy", "screenshot": "builtin:copy"})
    f = tmp_path / "keynote.txt"
    f.write_text("transcript", encoding="utf-8")

    talk = sources.add_source(root, str(f), kind="talk")
    other = sources.add_source(root, str(f), kind="screenshot")

    assert talk.fm["id"] == "T1"  # talk -> T
    assert other.fm["id"] == "S1"  # unmapped kinds -> S
    assert talk.fm["local"] == "sources/raw/T1.txt"
    assert talk.fm["description"] == "talk source"
    assert other.fm["description"] == "screenshot source"
    events = read_jsonl(root / "sources" / "_provenance.jsonl")
    assert all(e["tool"] == "builtin:copy" and e["strategy"] == "copy" for e in events)


def test_missing_config_names_file_and_stanza(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    home = make_flip_home(tmp_path, monkeypatch, fetchers=None)  # no config.toml
    with pytest.raises(SystemExit) as ei:
        sources.add_source(root, "https://example.com/x")
    msg = str(ei.value)
    assert str(home / "config.toml") in msg
    assert "[fetchers]" in msg
    assert not (root / "sources").exists()  # nothing written on failure
    assert not (root / "references").exists()


def test_missing_fetcher_kind_names_file_and_stanza(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    home = make_flip_home(tmp_path, monkeypatch, {"web": "somefetch {url} {dest}"})
    with pytest.raises(SystemExit) as ei:
        sources.add_source(root, "whatever", kind="media")
    msg = str(ei.value)
    assert "media" in msg
    assert str(home / "config.toml") in msg
    assert "[fetchers]" in msg


def test_fetcher_nonzero_exit_errors(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    script = make_fetcher(tmp_path, 'echo "boom: fetch blocked" >&2\nexit 3\n')
    make_flip_home(tmp_path, monkeypatch, {"web": f"{script} {{url}} {{dest}}"})
    with pytest.raises(SystemExit) as ei:
        sources.add_source(root, "https://example.com/x")
    msg = str(ei.value)
    assert "exit 3" in msg
    assert "boom" in msg
    assert not (root / "sources" / "_provenance.jsonl").exists()
    assert not (root / "references").exists()  # no page opened on failure


def test_fetcher_producing_no_files_errors(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    script = make_fetcher(tmp_path, "exit 0\n")
    make_flip_home(tmp_path, monkeypatch, {"web": f"{script} {{url}} {{dest}}"})
    with pytest.raises(SystemExit) as ei:
        sources.add_source(root, "https://example.com/x")
    assert "wrote nothing" in str(ei.value)


def test_fetcher_command_not_found_errors(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    make_flip_home(tmp_path, monkeypatch, {"web": "/nonexistent/fetcher-xyz {url} {dest}"})
    with pytest.raises(SystemExit) as ei:
        sources.add_source(root, "https://example.com/x")
    assert "not found" in str(ei.value)


# --- id allocation --------------------------------------------------------


def test_ids_scan_pages_and_provenance_never_reused(tmp_path):
    root = make_notebook(tmp_path)
    # F2 lives only as a page; F5 only in provenance (its page was deleted).
    pages.write_page(
        root / "references" / "old-capture.md",
        {"type": "Source", "id": "F2", "aliases": ["F2"]},
        "# old capture\n",
    )
    append_jsonl(root / "sources" / "_provenance.jsonl", {"source_id": "F5"})
    f = tmp_path / "data.csv"
    f.write_text("a,b\n", encoding="utf-8")

    page = sources.add_source(root, str(f))

    assert page.fm["id"] == "F6"
    ids = sorted(p.id for p in sources.source_pages(root))
    assert ids == ["F2", "F6"]


def test_ids_increment_per_prefix(tmp_path):
    root = make_notebook(tmp_path)
    f = tmp_path / "one.txt"
    f.write_text("x", encoding="utf-8")
    assert sources.add_source(root, str(f)).fm["id"] == "F1"
    assert sources.add_source(root, str(f)).fm["id"] == "F2"


def test_file_dataset_document_kinds_get_f_prefix_not_d(tmp_path, monkeypatch):
    # SPEC §9: D is reserved for decisions; files/datasets/documents are F#.
    root = make_notebook(tmp_path)
    make_flip_home(tmp_path, monkeypatch, {"dataset": "builtin:copy", "document": "builtin:copy"})
    f = tmp_path / "table.csv"
    f.write_text("a,b\n", encoding="utf-8")
    assert sources.add_source(root, str(f), kind="file").fm["id"] == "F1"
    assert sources.add_source(root, str(f), kind="dataset").fm["id"] == "F2"
    assert sources.add_source(root, str(f), kind="document").fm["id"] == "F3"
    assert not any(p.id.startswith("D") for p in sources.source_pages(root))


# --- slugs ------------------------------------------------------------------


def test_slug_collision_gets_numeric_suffix(tmp_path):
    root = make_notebook(tmp_path)
    a = tmp_path / "one" / "report.pdf"
    b = tmp_path / "two" / "report.pdf"
    for f in (a, b):
        f.parent.mkdir()
        f.write_bytes(b"x")

    first = sources.add_source(root, str(a))
    second = sources.add_source(root, str(b))  # same title -> -2 suffix

    assert first.path.name == "report-pdf.md"
    assert second.path.name == "report-pdf-2.md"
    assert first.fm["id"] == "F1" and second.fm["id"] == "F2"
    assert pages.read_page(second.path).fm["id"] == "F2"


# --- grade_source ---------------------------------------------------------


def _captured_source(tmp_path):
    root = make_notebook(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")
    page = sources.add_source(root, str(f))
    return root, page


def test_grade_source_updates_page_in_place(tmp_path):
    root, page = _captured_source(tmp_path)
    graded = sources.grade_source(
        root, page.id, grade="B", independence="republisher", freshness="dated",
        notes="vendor blog",
    )
    assert graded.fm["grade"] == "B"
    assert graded.fm["independence"] == "republisher"
    assert graded.fm["freshness"] == "dated"
    assert graded.fm["notes"] == "vendor blog"
    assert graded.fm["status"] == "captured"  # untouched keys survive
    assert graded.path == page.path  # same page, no new file
    assert pages.read_page(page.path).fm == graded.fm


def test_grade_source_partial_update(tmp_path):
    root, page = _captured_source(tmp_path)
    graded = sources.grade_source(root, page.id, grade="A")
    assert graded.fm["grade"] == "A"
    assert graded.fm["independence"] == "original"
    assert graded.fm["freshness"] == "fresh"


def test_add_source_reserves_its_id(tmp_path):
    root, page = _captured_source(tmp_path)
    assert page.id == "F1"
    reserved = (root / ".flip" / "ids").read_text(encoding="utf-8").splitlines()
    assert reserved == ["F1"]


def test_grade_source_normalizes_foreign_tz_to_utc(tmp_path):
    # an editor can legally write a tz-aware timestamp; a read-modify-write
    # must convert it to the same UTC instant, not relabel the wall clock as Z
    root, page = _captured_source(tmp_path)
    text = page.path.read_text(encoding="utf-8")
    text = text.replace(
        "type: Source\n", "type: Source\nretrieved: 2026-07-09T14:30:00+02:00\n", 1
    )
    page.path.write_text(text, encoding="utf-8")

    graded = sources.grade_source(root, page.id, grade="B")

    assert graded.fm["retrieved"] == "2026-07-09T12:30:00Z"  # instant preserved
    on_disk = page.path.read_text(encoding="utf-8")
    assert "12:30:00" in on_disk
    assert "14:30:00" not in on_disk  # the wall clock was not relabeled Z


def test_grade_source_round_trips_foreign_frontmatter_and_body(tmp_path):
    # An Obsidian-authored page: extra frontmatter keys and prose must survive
    # a grading pass byte-for-value (SPEC §6.6).
    root, page = _captured_source(tmp_path)
    edited = pages.read_page(page.path)
    edited.fm["starred"] = True
    edited.fm["cssclasses"] = ["wide"]
    pages.write_page(page.path, edited.fm, edited.body + "\nPull-quote I care about.\n")

    graded = sources.grade_source(root, page.id, grade="B", notes="read in full")

    on_disk = pages.read_page(page.path)
    assert on_disk.fm["starred"] is True
    assert on_disk.fm["cssclasses"] == ["wide"]
    assert on_disk.fm["grade"] == "B"
    assert on_disk.fm["notes"] == "read in full"
    assert "Pull-quote I care about." in on_disk.body
    assert graded.fm == on_disk.fm


def test_grade_source_rewrites_are_byte_stable(tmp_path):
    # read-modify-write must not accrete whitespace (SPEC §12): grading twice
    # with the same values leaves the file byte-identical.
    root, page = _captured_source(tmp_path)
    sources.grade_source(root, page.id, grade="B")
    first = page.path.read_text(encoding="utf-8")
    sources.grade_source(root, page.id, grade="B")
    assert page.path.read_text(encoding="utf-8") == first


def test_grade_source_invalid_values(tmp_path):
    root, page = _captured_source(tmp_path)
    with pytest.raises(SystemExit, match="invalid grade"):
        sources.grade_source(root, page.id, grade="Z")
    with pytest.raises(SystemExit, match="invalid independence"):
        sources.grade_source(root, page.id, independence="biased")
    with pytest.raises(SystemExit, match="invalid freshness"):
        sources.grade_source(root, page.id, freshness="stale")
    # invalid input must not dirty the page
    assert pages.read_page(page.path).fm["grade"] == "?"


def test_grade_source_unknown_id(tmp_path):
    root, _page = _captured_source(tmp_path)
    with pytest.raises(SystemExit) as ei:
        sources.grade_source(root, "P99", grade="A")
    msg = str(ei.value)
    assert "unknown source id 'P99'" in msg
    assert "F1" in msg  # names the ids it does have


def test_grade_source_no_sources_yet(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as ei:
        sources.grade_source(root, "A1", grade="B")
    assert "unknown source id" in str(ei.value)


# --- list_sources / source_pages -------------------------------------------


def test_list_sources_returns_fm_dicts_with_slug_and_path(tmp_path):
    root = make_notebook(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")
    p1 = sources.add_source(root, str(f))
    p2 = sources.add_source(root, str(f))

    rows = sources.list_sources(root)

    assert [r["id"] for r in rows] == ["F1", "F2"]
    assert rows[0]["slug"] == p1.slug
    assert rows[0]["path"] == "references/doc-txt.md"
    assert rows[1]["path"] == "references/doc-txt-2.md"
    assert rows[0]["grade"] == "?"
    assert p2.slug == "doc-txt-2"


def test_list_sources_orders_by_id_number(tmp_path):
    root = make_notebook(tmp_path)
    for sid, slug in (("F10", "zzz"), ("F2", "aaa")):
        pages.write_page(
            root / "references" / f"{slug}.md",
            {"type": "Source", "id": sid, "aliases": [sid]},
            f"# {slug}\n",
        )
    assert [r["id"] for r in sources.list_sources(root)] == ["F2", "F10"]


def test_list_sources_empty_and_non_notebook(tmp_path):
    root = make_notebook(tmp_path)
    assert sources.list_sources(root) == []
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        sources.list_sources(tmp_path / "nowhere")


def test_source_pages_returns_pages(tmp_path):
    root, page = _captured_source(tmp_path)
    got = sources.source_pages(root)
    assert [p.id for p in got] == [page.id]
    assert isinstance(got[0], pages.Page)


# --- fetcher template tokenization ------------------------------------------


def test_tokenize_template_posix_mode_handles_quotes():
    assert sources._tokenize_template('fetch "{url}" --out {dest}') == [
        "fetch", "{url}", "--out", "{dest}",
    ]


def test_tokenize_template_windows_mode_keeps_backslash_paths(monkeypatch):
    template = r'C:\Tools\fetch.exe {url} --out {dest}'
    # posix mode would eat the backslashes ...
    monkeypatch.setattr(sources.os, "name", "posix")
    assert sources._tokenize_template(template)[0] == "C:Toolsfetch.exe"
    # ... nt mode must keep them
    monkeypatch.setattr(sources.os, "name", "nt")
    assert sources._tokenize_template(template)[0] == r"C:\Tools\fetch.exe"
