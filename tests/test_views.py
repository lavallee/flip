"""Tests for flip.views — computed hot/claims/stale views and the generated
at-rest projections (regenerate: log.md, dir index.md files, root index body)
per SPEC §10."""

import json
from pathlib import Path

import pytest

from flip import ledgers, pages, views
from flip.views import claims_view, hot_view, regenerate, stale_view

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: test
kind: {kind}
status: active
created: 2026-07-01
updated: 2026-07-09
{extra}---
# test
"""


def make_notebook(tmp_path: Path, kind: str = "scout", extra: str = "") -> Path:
    root = tmp_path / "nb"
    root.mkdir(exist_ok=True)
    (root / "index.md").write_text(MANIFEST_MD.format(kind=kind, extra=extra), encoding="utf-8")
    return root.resolve()


def write_jsonl(root: Path, rel: str, rows: list[dict]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def question_page(root: Path, qid: str, text: str, status: str | None = "open") -> None:
    fm: dict = {"type": "Question", "id": qid, "aliases": [qid], "description": text}
    if status is not None:
        fm["status"] = status
    fm["timestamp"] = "2026-07-09T10:00:00Z"
    fm["actor"] = "human:test"
    pages.write_page(root / "questions" / f"{pages.slugify(text)}.md", fm, text + "\n")


def claim_page(
    root: Path,
    cid: str,
    text: str,
    status: str,
    load_bearing: bool = False,
    sources: list[str] | None = None,
    corroboration: int = 0,
) -> None:
    fm = {
        "type": "Claim",
        "id": cid,
        "aliases": [cid],
        "description": text,
        "status": status,
        "load_bearing": load_bearing,
        "sources": sources or [],
        "independent_corroboration": corroboration,
        "first_asserted": "2026-07-09",
        "actor": "human:test",
    }
    pages.write_page(root / "claims" / f"{pages.slugify(text)}.md", fm, text + "\n")


def source_page(
    root: Path,
    sid: str,
    title: str,
    freshness: str = "fresh",
    date: str | None = None,
    description: str = "",
) -> None:
    fm: dict = {"type": "Source", "id": sid, "aliases": [sid], "title": title}
    if description:
        fm["description"] = description
    if date:
        fm["date"] = date
    fm.update({"grade": "?", "independence": "original", "freshness": freshness})
    pages.write_page(root / "references" / f"{pages.slugify(title)}.md", fm, f"# {title}\n")


# --- hot_view ---------------------------------------------------------------


def test_hot_view_empty_notebook_is_just_the_manifest_line(tmp_path):
    root = make_notebook(tmp_path)
    text = hot_view(root)
    assert text == "test · scout · active · 2026-07-09"
    assert "OPEN QUESTIONS" not in text
    assert "RECENT LOG" not in text


def test_hot_view_shows_open_questions_and_hides_answered(tmp_path):
    root = make_notebook(tmp_path)
    question_page(root, "Q1", "who pays?", status="open")
    question_page(root, "Q2", "when?", status="answered")
    text = hot_view(root)
    assert "OPEN QUESTIONS" in text
    assert "Q1 · who pays?" in text
    assert "Q2" not in text


def test_hot_view_question_without_status_counts_as_open(tmp_path):
    root = make_notebook(tmp_path)
    question_page(root, "Q1", "unjudged?", status=None)
    assert "Q1" in hot_view(root)


def test_hot_view_claims_needing_work_load_bearing_first(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", "minor", "asserted", load_bearing=False)
    claim_page(root, "C2", "key", "needs-2nd", load_bearing=True, sources=["A1"], corroboration=1)
    claim_page(root, "C3", "done", "verified", load_bearing=True, sources=["A1"], corroboration=2)
    text = hot_view(root)
    assert "CLAIMS NEEDING WORK" in text
    assert "C3" not in text  # verified is not "needing work"
    assert text.index("C2") < text.index("C1")  # load-bearing first
    assert "[load-bearing]" in text


def test_hot_view_recent_log_is_last_eight(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "log/log.jsonl",
        [{"ts": f"t{i}", "text": f"event-{i}", "actor": "a"} for i in range(1, 11)],
    )
    text = hot_view(root)
    assert "event-10" in text
    assert "event-3" in text
    assert "event-2" not in text
    assert "event-1\n" not in text and "event-1 " not in text


def test_hot_view_latest_session_is_newest_by_name(tmp_path):
    root = make_notebook(tmp_path)
    sessions = root / "sessions"
    sessions.mkdir()
    (sessions / "2026-07-01T1000-old.md").write_text("old", encoding="utf-8")
    (sessions / "2026-07-09T0900-new.md").write_text("new", encoding="utf-8")
    (sessions / "index.md").write_text("# Sessions\n", encoding="utf-8")  # generated: skipped
    text = hot_view(root)
    assert "LATEST SESSION" in text
    assert "sessions/2026-07-09T0900-new.md" in text
    assert "old.md" not in text


def test_hot_view_dated_sources_count(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", "judged dated", freshness="dated")
    source_page(root, "A2", "recent", freshness="fresh", date="2026-06-01")
    assert "DATED SOURCES: 1" in hot_view(root)


def test_hot_view_as_data(tmp_path):
    root = make_notebook(tmp_path)
    question_page(root, "Q1", "x?")
    data = hot_view(root, as_data=True)
    assert data["slug"] == "test"
    assert data["kind"] == "scout"
    assert data["open_questions"][0]["id"] == "Q1"
    assert data["open_questions"][0]["text"] == "x?"
    assert data["claims_needing_work"] == []
    assert data["recent_log"] == []
    assert data["latest_session"] is None
    assert data["dated_sources"] == 0


def test_hot_view_missing_manifest_exits(tmp_path):
    with pytest.raises(SystemExit):
        hot_view(tmp_path)  # no index.md here


def test_hot_view_unknown_kind_falls_back_to_defaults(tmp_path):
    root = make_notebook(tmp_path, kind="no-such-profile")
    assert "no-such-profile" in hot_view(root)


def test_hot_view_bad_log_jsonl_exits_actionably(tmp_path):
    root = make_notebook(tmp_path)
    path = root / "log" / "log.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        hot_view(root)
    assert "log.jsonl" in str(e.value)


# --- claims_view ------------------------------------------------------------


def test_claims_view_groups_by_status_in_enum_order(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", "a", "verified", load_bearing=True, sources=["A1", "A2"],
               corroboration=2)
    claim_page(root, "C2", "b", "asserted")
    text = claims_view(root)
    assert text.index("ASSERTED") < text.index("VERIFIED")
    assert "C1 · [load-bearing] · a · sources: A1, A2 · corroboration: 2" in text
    assert "C2 · b · sources: none · corroboration: 0" in text


def test_claims_view_truncates_long_text_to_80(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", "z" * 200, "asserted")
    text = claims_view(root)
    assert "z" * 79 + "…" in text
    assert "z" * 100 not in text


def test_claims_view_empty(tmp_path):
    root = make_notebook(tmp_path)
    assert "no claims recorded" in claims_view(root)
    data = claims_view(root, as_data=True)
    assert data == {"total": 0, "by_status": {}}


def test_claims_view_unknown_status_still_listed(tmp_path):
    root = make_notebook(tmp_path)
    claim_page(root, "C1", "odd", "bogus")
    text = claims_view(root)
    assert "BOGUS" in text
    assert "C1" in text


def test_claims_view_skips_corrupt_pages(tmp_path):
    # Views must survive one broken page (doctor is where it gets reported).
    root = make_notebook(tmp_path)
    claim_page(root, "C1", "solid", "asserted")
    (root / "claims" / "broken.md").write_text("---\nid: [unclosed\n---\nbody\n", encoding="utf-8")
    text = claims_view(root)
    assert "C1" in text
    assert "broken" not in text


# --- stale_view -------------------------------------------------------------


def test_stale_view_flags_dated_and_old_sources(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", "judged dated", freshness="dated", date="2026-06-01")
    source_page(root, "A2", "old by date", freshness="fresh", date="2020-01-01")
    source_page(root, "A3", "recent", freshness="fresh", date="2026-06-01")
    text = stale_view(root)
    assert "DATED SOURCES" in text
    assert "A1" in text
    assert "A2" in text
    assert "A3" not in text


def test_stale_view_lists_open_questions_and_stuck_claims(tmp_path):
    root = make_notebook(tmp_path)
    question_page(root, "Q1", "open one")
    claim_page(root, "C1", "stuck", "asserted", load_bearing=True)
    claim_page(root, "C2", "fine", "verified", load_bearing=True, sources=["A1"], corroboration=2)
    text = stale_view(root)
    assert "OPEN QUESTIONS" in text and "Q1" in text
    assert "STUCK CLAIMS" in text and "C1" in text
    assert "C2" not in text


def test_stale_view_nothing_stale(tmp_path):
    root = make_notebook(tmp_path)
    assert stale_view(root) == "nothing stale"


def test_stale_view_as_data(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", "judged dated", freshness="dated")
    data = stale_view(root, as_data=True)
    assert [r["id"] for r in data["dated_sources"]] == ["A1"]
    assert data["open_questions"] == []
    assert data["stuck_claims"] == []


def test_stale_view_source_without_date_or_freshness_not_flagged(tmp_path):
    root = make_notebook(tmp_path)
    pages.write_page(
        root / "references" / "bare.md",
        {"type": "Source", "id": "A1", "aliases": ["A1"], "title": "bare"},
        "# bare\n",
    )
    assert stale_view(root) == "nothing stale"


# --- regenerate: log.md -------------------------------------------------------


def test_regenerate_writes_log_md_newest_first(tmp_path):
    root = make_notebook(tmp_path)
    write_jsonl(
        root,
        "log/log.jsonl",
        [
            {"ts": "2026-07-08T10:00:00Z", "text": "first", "actor": "human:al"},
            {"ts": "2026-07-09T09:00:00Z", "text": "second", "actor": "agent:claude"},
            {"ts": "2026-07-09T11:00:00Z", "text": "third", "actor": "agent:claude"},
        ],
    )
    regenerate(root)
    text = (root / "log.md").read_text(encoding="utf-8")
    assert text.startswith("# Update Log\n")
    assert text.index("## 2026-07-09") < text.index("## 2026-07-08")  # days newest first
    assert text.index("third") < text.index("second")  # newest first within a day
    assert "* **Update**: first _(human:al)_" in text
    assert "* **Update**: third _(agent:claude)_" in text


def test_regenerate_writes_no_log_md_without_events(tmp_path):
    root = make_notebook(tmp_path)
    regenerate(root)
    assert not (root / "log.md").exists()


def test_regenerate_tolerates_corrupt_log_jsonl(tmp_path):
    root = make_notebook(tmp_path)
    path = root / "log" / "log.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{broken\n", encoding="utf-8")
    regenerate(root)  # must not raise; doctor pinpoints the bad line
    assert not (root / "log.md").exists()


# --- regenerate: entity-directory listings -------------------------------------


def test_regenerate_writes_entity_dir_indexes(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", "LeCun keynote", description="primary transcript")
    pages.write_page(  # no title: the listing label falls back to the id
        root / "references" / "untitled.md",
        {"type": "Source", "id": "A2", "aliases": ["A2"]},
        "# untitled\n",
    )
    regenerate(root)
    text = (root / "references" / "index.md").read_text(encoding="utf-8")
    assert text.startswith("# References\n")
    assert "* [LeCun keynote](lecun-keynote.md) - primary transcript" in text
    assert "* [A2](untitled.md)" in text
    assert not (root / "claims" / "index.md").exists()  # dir absent: skipped


def test_regenerate_drops_listing_when_last_page_is_deleted(tmp_path):
    # Empty structure is worse than absent structure (SPEC §1.10): once the
    # last entity page goes, the stale generated listing goes with it.
    root = make_notebook(tmp_path)
    claim_page(root, "C1", "only one", "asserted")
    regenerate(root)
    assert (root / "claims" / "index.md").is_file()
    (root / "claims" / pages.slugify("only one")).with_suffix(".md").unlink()
    regenerate(root)
    assert not (root / "claims" / "index.md").exists()
    assert "[Claims]" not in pages.read_page(root / "index.md").body  # bullet gone too


def test_regenerate_never_deletes_an_authored_index(tmp_path):
    # An index.md carrying frontmatter is not flip's generated listing —
    # non-conformant (doctor flags it), but never destroyed.
    root = make_notebook(tmp_path)
    (root / "claims").mkdir()
    authored = root / "claims" / "index.md"
    authored.write_text("---\ntype: Note\n---\nhands off\n", encoding="utf-8")
    regenerate(root)
    assert "hands off" in authored.read_text(encoding="utf-8")


# --- regenerate: root index.md body --------------------------------------------


def test_regenerate_root_body_lists_sections_with_counts(tmp_path):
    root = make_notebook(tmp_path, extra="obsidian_tag: keepme\n")
    source_page(root, "A1", "one")
    source_page(root, "A2", "two")
    question_page(root, "Q1", "open one", status="open")
    question_page(root, "Q2", "closed one", status="answered")
    write_jsonl(root, "log/log.jsonl", [{"ts": "2026-07-09T09:00:00Z", "text": "x", "actor": "a"}])
    regenerate(root)
    page = pages.read_page(root / "index.md")
    body = page.body.lstrip("\n")
    assert body.startswith("# test\n")
    assert "* [References](references/) - 2 captured sources with custody and grading" in body
    assert "* [Questions](questions/) - 2 questions, 1 open" in body
    assert "* [Update Log](log.md) - 1 logged event, newest first" in body
    assert "[Claims]" not in body  # dir absent: no bullet
    # manifest frontmatter untouched, unknown keys preserved (SPEC §6.6)
    assert page.fm["slug"] == "test"
    assert page.fm["obsidian_tag"] == "keepme"


def test_regenerate_is_deterministic_and_byte_stable(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", "one")
    write_jsonl(root, "log/log.jsonl", [{"ts": "2026-07-09T09:00:00Z", "text": "x", "actor": "a"}])
    regenerate(root)
    snapshot = {
        rel: (root / rel).read_text(encoding="utf-8")
        for rel in ("index.md", "references/index.md", "log.md")
    }
    regenerate(root)
    for rel, before in snapshot.items():
        assert (root / rel).read_text(encoding="utf-8") == before, rel


def test_regenerate_outside_notebook_exits(tmp_path):
    with pytest.raises(SystemExit):
        regenerate(tmp_path)  # no index.md: nothing gets written


def test_regenerate_hand_edits_to_generated_views_do_not_survive(tmp_path):
    root = make_notebook(tmp_path)
    source_page(root, "A1", "one")
    regenerate(root)
    (root / "references" / "index.md").write_text("hand edit\n", encoding="utf-8")
    regenerate(root)
    assert "hand edit" not in (root / "references" / "index.md").read_text(encoding="utf-8")


# --- wiring: mutations refresh the generated views ------------------------------


def test_log_event_regenerates_log_md_and_root_body(tmp_path):
    root = make_notebook(tmp_path)
    ledgers.log_event(root, "captured the filings")
    assert "captured the filings" in (root / "log.md").read_text(encoding="utf-8")
    assert "[Update Log](log.md)" in pages.read_page(root / "index.md").body


def test_add_question_regenerates_dir_index(tmp_path):
    root = make_notebook(tmp_path)
    page = ledgers.add_question(root, "who pays for the audit?")
    text = (root / "questions" / "index.md").read_text(encoding="utf-8")
    assert f"({page.slug}.md)" in text
    assert "[Questions](questions/)" in pages.read_page(root / "index.md").body


def test_regenerate_exists_for_core_module_hooks():
    # sources/claims call views.regenerate via a defensive getattr; make sure
    # the hook they look for is the public callable this module exports.
    assert callable(getattr(views, "regenerate"))
