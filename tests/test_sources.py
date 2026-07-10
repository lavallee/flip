"""Tests for flip.sources: classification, capture, provenance, grading."""

import stat
import tomllib

import pytest

from flip import sources
from flip.util import append_jsonl, read_jsonl, sha256_file, write_jsonl


def make_notebook(tmp_path):
    root = tmp_path / "nb"
    root.mkdir()
    (root / "notebook.toml").write_text(
        'slug = "test-nb"\nkind = "scout"\nstatus = "active"\n'
        'created = "2026-01-01"\nupdated = "2026-01-01"\n',
        encoding="utf-8",
    )
    return root


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

    row = sources.add_source(root, str(src), note="grabbed for test")

    assert row["id"] == "F1"
    assert row["kind"] == "file"
    assert row["local"] == "sources/raw/F1.pdf"
    assert row["grade"] == "?"
    assert row["independence"] == "original"
    assert row["freshness"] == "fresh"
    assert row["status"] == "captured"
    assert row["supports"] == []
    assert row["notes"] == "grabbed for test"
    assert "url" not in row  # local copies carry origin in provenance only

    copied = root / "sources" / "raw" / "F1.pdf"
    assert copied.read_bytes() == payload
    assert read_jsonl(root / "sources" / "ledger.jsonl") == [row]

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

    manifest = tomllib.loads((root / "notebook.toml").read_text(encoding="utf-8"))
    assert manifest["updated"] != "2026-01-01"


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
    with pytest.raises(SystemExit) as ei:
        sources.add_source(tmp_path / "not-a-notebook", "https://example.com")
    assert "notebook.toml" in str(ei.value)


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

    row = sources.add_source(root, "https://example.com/story")

    assert row["id"] == "A1"
    assert row["kind"] == "web"
    assert row["url"] == "https://example.com/story"
    assert row["local"] == "sources/raw/A1/page.html"  # the largest captured file
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

    row = sources.add_source(root, "doi:10.1234/widgets.5")

    assert row["id"] == "P1"
    assert row["kind"] == "paper"
    assert row["url"] == "doi:10.1234/widgets.5"
    captured = root / "sources" / "raw" / "P1" / "paper.txt"
    assert captured.read_text(encoding="utf-8") == "10.1234/widgets.5"


def test_config_routed_builtin_copy_and_prefixes(tmp_path, monkeypatch):
    root = make_notebook(tmp_path)
    make_flip_home(tmp_path, monkeypatch, {"talk": "builtin:copy", "screenshot": "builtin:copy"})
    f = tmp_path / "keynote.txt"
    f.write_text("transcript", encoding="utf-8")

    talk = sources.add_source(root, str(f), kind="talk")
    other = sources.add_source(root, str(f), kind="screenshot")

    assert talk["id"] == "T1"  # talk -> T
    assert other["id"] == "S1"  # unmapped kinds -> S
    assert talk["local"] == "sources/raw/T1.txt"
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
    assert not (root / "sources" / "ledger.jsonl").exists()


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


def test_ids_scan_ledger_and_provenance_never_reused(tmp_path):
    root = make_notebook(tmp_path)
    # F2 lives only in the ledger; F5 only in provenance (its row was retracted).
    write_jsonl(root / "sources" / "ledger.jsonl", [{"id": "F2", "kind": "file"}])
    append_jsonl(root / "sources" / "_provenance.jsonl", {"source_id": "F5"})
    f = tmp_path / "data.csv"
    f.write_text("a,b\n", encoding="utf-8")

    row = sources.add_source(root, str(f))

    assert row["id"] == "F6"
    ids = [r["id"] for r in read_jsonl(root / "sources" / "ledger.jsonl")]
    assert ids == ["F2", "F6"]


def test_ids_increment_per_prefix(tmp_path):
    root = make_notebook(tmp_path)
    f = tmp_path / "one.txt"
    f.write_text("x", encoding="utf-8")
    assert sources.add_source(root, str(f))["id"] == "F1"
    assert sources.add_source(root, str(f))["id"] == "F2"


def test_file_dataset_document_kinds_get_f_prefix_not_d(tmp_path, monkeypatch):
    # SPEC §3: D is reserved for decisions; files/datasets/documents are F#.
    root = make_notebook(tmp_path)
    make_flip_home(tmp_path, monkeypatch, {"dataset": "builtin:copy", "document": "builtin:copy"})
    f = tmp_path / "table.csv"
    f.write_text("a,b\n", encoding="utf-8")
    assert sources.add_source(root, str(f), kind="file")["id"] == "F1"
    assert sources.add_source(root, str(f), kind="dataset")["id"] == "F2"
    assert sources.add_source(root, str(f), kind="document")["id"] == "F3"
    assert not any(r["id"].startswith("D") for r in read_jsonl(root / "sources" / "ledger.jsonl"))


# --- grade_source ---------------------------------------------------------


def _captured_source(tmp_path):
    root = make_notebook(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")
    row = sources.add_source(root, str(f))
    return root, row["id"]


def test_grade_source_updates_row_in_place(tmp_path):
    root, sid = _captured_source(tmp_path)
    row = sources.grade_source(
        root, sid, grade="B", independence="republisher", freshness="dated", notes="vendor blog"
    )
    assert row["grade"] == "B"
    assert row["independence"] == "republisher"
    assert row["freshness"] == "dated"
    assert row["notes"] == "vendor blog"
    assert row["status"] == "captured"  # untouched fields survive
    assert read_jsonl(root / "sources" / "ledger.jsonl") == [row]


def test_grade_source_partial_update(tmp_path):
    root, sid = _captured_source(tmp_path)
    row = sources.grade_source(root, sid, grade="A")
    assert row["grade"] == "A"
    assert row["independence"] == "original"
    assert row["freshness"] == "fresh"


def test_grade_source_invalid_values(tmp_path):
    root, sid = _captured_source(tmp_path)
    with pytest.raises(SystemExit, match="invalid grade"):
        sources.grade_source(root, sid, grade="Z")
    with pytest.raises(SystemExit, match="invalid independence"):
        sources.grade_source(root, sid, independence="biased")
    with pytest.raises(SystemExit, match="invalid freshness"):
        sources.grade_source(root, sid, freshness="stale")
    # invalid input must not dirty the ledger
    assert read_jsonl(root / "sources" / "ledger.jsonl")[0]["grade"] == "?"


def test_grade_source_unknown_id(tmp_path):
    root, _ = _captured_source(tmp_path)
    with pytest.raises(SystemExit) as ei:
        sources.grade_source(root, "P99", grade="A")
    msg = str(ei.value)
    assert "unknown source id 'P99'" in msg
    assert "F1" in msg  # names the ids it does have


def test_grade_source_empty_ledger(tmp_path):
    root = make_notebook(tmp_path)
    with pytest.raises(SystemExit) as ei:
        sources.grade_source(root, "A1", grade="B")
    assert "unknown source id" in str(ei.value)


# --- list_sources ----------------------------------------------------------


def test_list_sources_returns_ledger_rows_in_order(tmp_path):
    root = make_notebook(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")
    r1 = sources.add_source(root, str(f))
    r2 = sources.add_source(root, str(f))
    assert sources.list_sources(root) == [r1, r2]


def test_list_sources_empty_and_non_notebook(tmp_path):
    root = make_notebook(tmp_path)
    assert sources.list_sources(root) == []
    with pytest.raises(SystemExit, match="not inside a flip notebook"):
        sources.list_sources(tmp_path / "nowhere")


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
