"""Tests for scaffold.create_notebook (flip new)."""

from __future__ import annotations

import pytest

from flip import pages
from flip.manifest import DEFAULT_POLICY, load_manifest
from flip.profiles import SECTIONS, load_profile
from flip.scaffold import create_notebook
from flip.util import is_notebook_root, today


def body_title(body: str) -> str:
    return body.lstrip("\n").splitlines()[0]


def test_creates_root_index_and_notebook_md_only(tmp_path):
    dest = tmp_path / "nb"
    result = create_notebook(dest, "nj-schools", "scout")
    assert result == dest
    assert sorted(p.name for p in dest.iterdir()) == ["index.md", "notebook.md"]
    assert is_notebook_root(dest)  # root discovery sniffs the new manifest


def test_manifest_fields_round_trip(tmp_path):
    dest = create_notebook(tmp_path / "nb", "nj-schools", "scout", title="NJ schools")
    m = load_manifest(dest)
    assert m.slug == "nj-schools"
    assert m.title == "NJ schools"
    assert m.kind == "scout"
    assert m.status == "active"
    assert m.created == today()
    assert m.updated == today()
    # scout forces no policy, so this is exactly the default policy
    assert m.policy == DEFAULT_POLICY


def test_notebook_md_has_notebook_type_frontmatter(tmp_path):
    # OKF conformance: every non-reserved .md carries frontmatter with a type
    dest = create_notebook(tmp_path / "nb", "nj-schools", "scout", title="NJ schools")
    page = pages.read_page(dest / "notebook.md")
    assert page.fm["type"] == "Notebook"
    assert page.fm["description"] == "NJ schools"


def test_notebook_md_title_and_section_stubs(tmp_path):
    dest = create_notebook(tmp_path / "nb", "nj-schools", "scout", title="NJ schools")
    body = pages.read_page(dest / "notebook.md").body
    assert body.lstrip("\n").startswith("# Reporter's notebook — NJ schools\n")
    profile = load_profile("scout")
    headings = [line for line in body.splitlines() if line.startswith("## ")]
    assert headings == [f"## {SECTIONS[s]['heading']}" for s in profile.sections]
    for s in profile.sections:
        assert f"## {SECTIONS[s]['heading']}\n\n> {SECTIONS[s]['prompt']}\n" in body


def test_title_falls_back_to_slug(tmp_path):
    dest = create_notebook(tmp_path / "nb", "nj-schools", "scout")
    page = pages.read_page(dest / "notebook.md")
    assert page.fm["description"] == "nj-schools"
    assert body_title(page.body) == "# Reporter's notebook — nj-schools"


def test_forced_policy_overlays_default(tmp_path):
    dest = create_notebook(tmp_path / "nb", "acme", "engagement")
    m = load_manifest(dest)
    assert m.policy["visibility"] == "client-confidential"
    assert m.policy["citation_rule"] == "public-terminus"
    assert m.policy["renders_public"] is False  # default survives the overlay


def test_visibility_arg_wins_over_forced_policy(tmp_path):
    dest = create_notebook(tmp_path / "nb", "acme", "engagement", visibility="private")
    assert load_manifest(dest).policy["visibility"] == "private"


def test_visibility_arg_applied_for_plain_profile(tmp_path):
    dest = create_notebook(tmp_path / "nb", "nj-schools", "scout", visibility="public")
    assert load_manifest(dest).policy["visibility"] == "public"


def test_creates_parent_directories(tmp_path):
    dest = tmp_path / "deep" / "nested" / "nb"
    create_notebook(dest, "nj-schools", "scout")
    assert (dest / "index.md").is_file()


def test_existing_notebook_root_refused(tmp_path):
    dest = tmp_path / "nb"
    create_notebook(dest, "nj-schools", "scout")
    before = (dest / "index.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="index.md"):
        create_notebook(dest, "other", "ledger")
    # nothing clobbered
    assert (dest / "index.md").read_text(encoding="utf-8") == before


def test_bad_slug_rejected_without_creating_dest(tmp_path):
    dest = tmp_path / "nb"
    for bad in ('quo"te', "new\nline", "Has Spaces", "-dash-first", ""):
        with pytest.raises(SystemExit, match="invalid slug"):
            create_notebook(dest, bad, "scout")
    assert not dest.exists()


def test_newline_title_produces_parseable_manifest(tmp_path):
    dest = create_notebook(tmp_path / "nb", "ok-slug", "scout", title="line one\nline two")
    assert load_manifest(dest).title == "line one\nline two"


def test_unknown_kind_errors_without_creating_dest(tmp_path):
    dest = tmp_path / "nb"
    with pytest.raises(SystemExit, match="unknown profile kind 'nope'"):
        create_notebook(dest, "nj-schools", "nope")
    assert not dest.exists()


def test_bad_visibility_errors_without_creating_dest(tmp_path):
    dest = tmp_path / "nb"
    with pytest.raises(SystemExit, match="invalid visibility 'secret'"):
        create_notebook(dest, "nj-schools", "scout", visibility="secret")
    assert not dest.exists()


def test_every_shipped_profile_scaffolds(tmp_path):
    for kind in ("ledger", "scout", "research-review", "engagement", "data-investigation"):
        dest = create_notebook(tmp_path / kind, kind, kind)
        m = load_manifest(dest)
        assert m.kind == kind
        page = pages.read_page(dest / "notebook.md")
        assert page.fm["type"] == "Notebook"
        assert body_title(page.body).startswith("# Reporter's notebook — ")
        assert sorted(p.name for p in dest.iterdir()) == ["index.md", "notebook.md"]


def test_notebook_local_profile_override_not_consulted(tmp_path):
    # a notebook-local profile only applies with a notebook_root, which
    # create_notebook does not have (the notebook doesn't exist yet) — so the
    # shipped profile is used even if a stray .flip/profiles exists elsewhere.
    dest = create_notebook(tmp_path / "nb", "s", "scout")
    profile = load_profile("scout")
    body = pages.read_page(dest / "notebook.md").body
    assert len([ln for ln in body.splitlines() if ln.startswith("## ")]) == len(profile.sections)
