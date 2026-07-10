"""Tests for flip.registry: flip_home resolution, scanning, index rewrite."""

from __future__ import annotations

from pathlib import Path

from flip.registry import INDEX, build_index, flip_home, read_index
from flip.util import read_jsonl


def write_manifest(d: Path, slug: str, kind: str = "scout", status: str = "active") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(
        "---\n"
        'okf_version: "0.1"\n'
        'flip: "0.4"\n'
        f"slug: {slug}\n"
        f"title: Title of {slug}\n"
        f"kind: {kind}\n"
        f"status: {status}\n"
        "created: 2026-07-09\n"
        "updated: 2026-07-10\n"
        "---\n"
        f"# Title of {slug}\n",
        encoding="utf-8",
    )
    return d


def set_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "fliphome"
    monkeypatch.setenv("FLIP_HOME", str(home))
    return home


# -- flip_home -----------------------------------------------------------


def test_flip_home_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "custom"))
    assert flip_home() == tmp_path / "custom"


def test_flip_home_defaults_to_dot_flip(monkeypatch, tmp_path):
    monkeypatch.delenv("FLIP_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert flip_home() == tmp_path / ".flip"


# -- build_index ---------------------------------------------------------


def test_build_index_finds_notebooks_and_writes_index(monkeypatch, tmp_path):
    home = set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    write_manifest(root / "nb1", "nb-one")
    write_manifest(root / "deep" / "nested" / "nb2", "nb-two", kind="ledger", status="done")

    rows = build_index([root])

    assert {r["slug"] for r in rows} == {"nb-one", "nb-two"}
    by_slug = {r["slug"]: r for r in rows}
    one = by_slug["nb-one"]
    assert one["path"] == str((root / "nb1").resolve())
    assert Path(one["path"]).is_absolute()
    assert one["kind"] == "scout"
    assert one["status"] == "active"
    assert one["updated"] == "2026-07-10"
    assert one["title"] == "Title of nb-one"
    assert by_slug["nb-two"]["kind"] == "ledger"
    # index.jsonl on disk matches the returned rows
    assert read_jsonl(home / INDEX) == rows


def test_build_index_prunes_ignored_dirs(monkeypatch, tmp_path):
    set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    write_manifest(root / "kept", "kept")
    for junk in (".git", ".venv", "node_modules", "__pycache__", "renders"):
        write_manifest(root / junk / "hidden", f"hidden-{junk}")

    rows = build_index([root])
    assert [r["slug"] for r in rows] == ["kept"]


def test_build_index_skips_export_bags(monkeypatch, tmp_path):
    # An export bag holds a data/ COPY of a notebook; indexing it would list
    # the same research twice. Any directory containing bagit.txt is pruned.
    set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    write_manifest(root / "nb", "the-notebook")
    bag = root / "nb-bag"
    write_manifest(bag / "data", "the-notebook")  # the bag's payload copy
    (bag / "bagit.txt").write_text(
        "BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n", encoding="utf-8"
    )

    rows = build_index([root])

    assert [r["path"] for r in rows] == [str((root / "nb").resolve())]


def test_build_index_skips_okf_exports(monkeypatch, tmp_path):
    # Since v0.4 an OKF export copies the bundle wholesale, flip frontmatter
    # included; its .last-export.json marker keeps it out of the registry.
    set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    write_manifest(root / "nb", "the-notebook")
    bundle = write_manifest(root / "nb-okf", "the-notebook")  # the exported copy
    (bundle / ".last-export.json").write_text("{}\n", encoding="utf-8")

    rows = build_index([root])

    assert [r["path"] for r in rows] == [str((root / "nb").resolve())]


def test_build_index_ignores_non_flip_index_md(monkeypatch, tmp_path):
    set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    nb = write_manifest(root / "nb", "real")
    # a plain OKF bundle: okf_version but no flip key — not a flip notebook
    okf = root / "plain-okf"
    okf.mkdir(parents=True)
    (okf / "index.md").write_text(
        '---\nokf_version: "0.1"\nslug: not-flip\n---\n# plain bundle\n', encoding="utf-8"
    )
    # a generated sub-index without frontmatter — never a root
    (nb / "references").mkdir()
    (nb / "references" / "index.md").write_text("# References\n", encoding="utf-8")

    rows = build_index([root])

    assert [r["slug"] for r in rows] == ["real"]


def test_build_index_warns_on_bad_manifest(monkeypatch, tmp_path, capsys):
    set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    write_manifest(root / "good", "good")
    bad = root / "bad"
    bad.mkdir(parents=True)
    (bad / "index.md").write_text(
        '---\nflip: "0.4"\nslug: "unclosed\n---\n# broken\n', encoding="utf-8"
    )
    noslug = root / "noslug"
    noslug.mkdir(parents=True)
    (noslug / "index.md").write_text(
        '---\nflip: "0.4"\ntitle: no slug here\n---\n# no slug\n', encoding="utf-8"
    )

    rows = build_index([root])

    warn_rows = [r for r in rows if "error" in r]
    assert {r["path"] for r in warn_rows} == {str(bad.resolve()), str(noslug.resolve())}
    for r in warn_rows:
        assert r["error"]  # non-empty reason
        assert set(r) == {"path", "error"}
    assert [r["slug"] for r in rows if "slug" in r] == ["good"]
    assert "WARN" in capsys.readouterr().err


def test_build_index_is_full_rewrite(monkeypatch, tmp_path):
    home = set_home(monkeypatch, tmp_path)
    root_a = write_manifest(tmp_path / "a" / "nb", "from-a")
    root_b = write_manifest(tmp_path / "b" / "nb", "from-b")

    build_index([root_a.parent])
    rows = build_index([root_b.parent])

    assert [r["slug"] for r in rows] == ["from-b"]
    assert [r["slug"] for r in read_jsonl(home / INDEX)] == ["from-b"]


def test_build_index_tolerates_unquoted_yaml_date(monkeypatch, tmp_path):
    # YAML parses a bare `updated: 2026-07-10` as a date object; the row must
    # still be a JSON-serializable ISO string.
    set_home(monkeypatch, tmp_path)
    nb = tmp_path / "nb"
    nb.mkdir()
    (nb / "index.md").write_text(
        '---\nflip: "0.4"\nslug: datey\nkind: scout\nstatus: active\nupdated: 2026-07-10\n---\n',
        encoding="utf-8",
    )
    rows = build_index([tmp_path])
    assert rows[0]["slug"] == "datey"
    assert rows[0]["updated"] == "2026-07-10"  # coerced, json-serializable


def test_build_index_missing_root_and_duplicates(monkeypatch, tmp_path):
    set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    write_manifest(root / "nb", "only-once")

    rows = build_index([tmp_path / "does-not-exist", root, root])
    assert [r["slug"] for r in rows] == ["only-once"]


def test_build_index_multiple_roots(monkeypatch, tmp_path):
    set_home(monkeypatch, tmp_path)
    r1 = write_manifest(tmp_path / "r1" / "nb", "one")
    r2 = write_manifest(tmp_path / "r2" / "nb", "two")
    rows = build_index([r1.parent, r2.parent])
    assert {r["slug"] for r in rows} == {"one", "two"}


# -- read_index ----------------------------------------------------------


def test_read_index_empty_when_never_built(monkeypatch, tmp_path):
    set_home(monkeypatch, tmp_path)
    assert read_index() == []


def test_read_index_roundtrip(monkeypatch, tmp_path):
    set_home(monkeypatch, tmp_path)
    root = tmp_path / "projects"
    write_manifest(root / "nb", "round-trip")
    rows = build_index([root])
    assert read_index() == rows
