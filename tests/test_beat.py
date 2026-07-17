"""Tests for flip.beat — the grouping layer above notebooks (SPEC §14).

Creation, root discovery either side of the beat/notebook nesting, thread
round-trips, TH# allocation, computed ranking, graduation end-to-end, the
show view, and the CLI wiring (including beat commands run from inside a
child notebook).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from flip import beat, pages, util
from flip.cli import main
from flip.util import read_jsonl


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Keep every test away from the real ~/.flip and the host's git identity."""
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "fliphome"))
    monkeypatch.setenv("FLIP_ACTOR", "human:test")


def invoke(args: list[str]):
    return CliRunner().invoke(main, args)


def make_beat(tmp_path: Path, slug: str = "county", mission: str = "Cover the county") -> Path:
    return beat.create_beat(tmp_path / slug, slug, mission=mission)


# ---------------------------------------------------------------- creation


def test_create_beat_writes_index_and_beat_md_only(tmp_path):
    root = make_beat(tmp_path)
    assert sorted(p.name for p in root.iterdir()) == ["beat.md", "index.md"]


def test_create_beat_manifest_shape(tmp_path):
    root = make_beat(tmp_path)
    fm = pages.read_page(root / "index.md").fm
    assert fm["okf_version"] == "0.1"
    assert fm["flip_beat"] == "0.1"
    assert fm["slug"] == "county"
    assert fm["mission"] == "Cover the county"
    assert fm["status"] == "active"
    assert fm["created"] == util.today() and fm["updated"] == util.today()
    assert fm["weights"] == {"payoff": 0.3, "access": 0.25, "urgency": 0.2,
                             "connection": 0.15, "uniqueness": 0.1}


def test_create_beat_md_prompts_and_mission(tmp_path):
    root = make_beat(tmp_path)
    page = pages.read_page(root / "beat.md")
    assert page.fm == {"type": "Beat", "description": "Cover the county"}
    assert "# Beat — county" in page.body
    assert "## Mission\n\nCover the county" in page.body
    assert "## Standing sources" in page.body
    assert "## What counts as covered" in page.body


def test_create_beat_without_mission_keeps_prompt_stub(tmp_path):
    root = beat.create_beat(tmp_path / "b", "b")
    body = pages.read_page(root / "beat.md").body
    assert "## Mission\n\n> " in body  # prompt, not prose
    assert "mission" not in pages.read_page(root / "index.md").fm


def test_create_beat_refuses_existing_beat_or_notebook_root(tmp_path):
    root = make_beat(tmp_path)
    with pytest.raises(SystemExit, match="already contains index.md"):
        beat.create_beat(root, "again")
    from flip.scaffold import create_notebook

    nb = create_notebook(tmp_path / "nb", "nb", "scout")
    with pytest.raises(SystemExit, match="already contains index.md"):
        beat.create_beat(nb, "again")


def test_create_beat_bad_slug_creates_nothing(tmp_path):
    with pytest.raises(SystemExit, match="invalid slug"):
        beat.create_beat(tmp_path / "x", "Bad Slug")
    assert not (tmp_path / "x").exists()


# ---------------------------------------------------------------- root discovery


def test_beat_root_is_not_a_notebook_root(tmp_path):
    # flip_beat: must never be mistaken for flip: — notebook discovery walks past
    root = make_beat(tmp_path)
    assert beat.is_beat_root(root)
    assert not util.is_notebook_root(root)
    assert util.find_notebook_root(root) is None


def test_notebook_root_is_not_a_beat_root(tmp_path):
    from flip.scaffold import create_notebook

    nb = create_notebook(tmp_path / "nb", "nb", "scout")
    assert util.is_notebook_root(nb)
    assert not beat.is_beat_root(nb)


def test_nested_notebook_resolves_both_layers(tmp_path):
    """From inside a child notebook, notebook commands find the notebook and
    beat commands walk PAST it to the beat (SPEC §14)."""
    root = make_beat(tmp_path)
    beat.add_thread(root, "angle", "arc")
    nb = beat.graduate(root, "TH1", "angle-scout")
    inside = nb / "references"
    inside.mkdir(exist_ok=True)
    assert util.find_notebook_root(inside) == nb
    assert beat.find_beat_root(inside) == root.resolve()
    # and from a beat subdirectory, there is no notebook root at all
    assert util.find_notebook_root(root / "threads") is None


def test_require_beat_root_outside_is_actionable(tmp_path):
    with pytest.raises(SystemExit, match="not inside a flip beat"):
        beat.require_beat_root(tmp_path)


# ---------------------------------------------------------------- manifest round trip


def test_load_save_beat_preserves_extras_and_foreign_typed_weights(tmp_path):
    root = make_beat(tmp_path)
    page = pages.read_page(root / "index.md")
    page.fm["cadence"] = "weekly"  # a key flip doesn't own
    pages.write_page(page.path, page.fm, page.body)
    b = beat.load_beat(root)
    assert b.extras["cadence"] == "weekly"
    beat.save_beat(root, b)
    assert pages.read_page(root / "index.md").fm["cadence"] == "weekly"
    # a foreign-typed weights value rides in extras instead of being dropped
    page = pages.read_page(root / "index.md")
    page.fm["weights"] = "heavy"
    pages.write_page(page.path, page.fm, page.body)
    b = beat.load_beat(root)
    assert b.weights == beat.DEFAULT_WEIGHTS
    assert b.extras["weights"] == "heavy"


def test_load_beat_missing_slug_is_actionable(tmp_path):
    (tmp_path / "index.md").write_text("---\nflip_beat: '0.1'\n---\n# x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="missing required key 'slug'"):
        beat.load_beat(tmp_path)


# ---------------------------------------------------------------- threads


def test_add_thread_page_shape(tmp_path):
    root = make_beat(tmp_path)
    page = beat.add_thread(root, "Bus contracts", "arc", note="tip came in",
                           scores={"payoff": 0.9})
    assert page.path == root / "threads" / "bus-contracts.md"
    assert page.fm["type"] == "Thread"
    assert page.fm["id"] == "TH1" and page.fm["aliases"] == ["TH1"]
    assert page.fm["kind"] == "arc" and page.fm["status"] == "open"
    assert page.fm["scores"] == {"payoff": 0.9}  # only the provided keys
    assert page.fm["actor"] == "human:test"
    assert page.body == "tip came in\n"
    # body falls back to the title; unscored threads carry no scores key
    page2 = beat.add_thread(root, "Board money", "vein")
    assert page2.body == "Board money\n"
    assert "scores" not in page2.fm


def test_add_thread_validates_kind_and_scores(tmp_path):
    root = make_beat(tmp_path)
    with pytest.raises(SystemExit, match="invalid kind 'saga'"):
        beat.add_thread(root, "x", "saga")
    with pytest.raises(SystemExit, match="unknown score 'payof'"):
        beat.add_thread(root, "x", "arc", scores={"payof": 0.9})
    with pytest.raises(SystemExit, match="out of range"):
        beat.add_thread(root, "x", "arc", scores={"payoff": 1.5})


def test_update_thread_round_trip_preserves_foreign_keys(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "Bus contracts", "arc", scores={"payoff": 0.9})
    page = pages.read_page(root / "threads" / "bus-contracts.md")
    page.fm["obsidian_color"] = "red"  # a foreign tool's key
    pages.write_page(page.path, page.fm, page.body)

    updated = beat.update_thread(root, "TH1", status="dormant", note="stalled",
                                 scores={"access": 0.2}, next_review="2027-01-01")
    assert updated.fm["obsidian_color"] == "red"
    assert updated.fm["status"] == "dormant"
    assert updated.fm["scores"] == {"payoff": 0.9, "access": 0.2}  # merged, not replaced
    assert updated.fm["next_review"] == "2027-01-01"
    assert f"## {util.today()}\n\nstalled" in updated.body
    assert updated.body.startswith("Bus contracts")  # original rationale survives


def test_update_thread_guards(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "x", "arc")
    with pytest.raises(SystemExit, match="nothing to update"):
        beat.update_thread(root, "TH1")
    with pytest.raises(SystemExit, match="invalid status 'paused'"):
        beat.update_thread(root, "TH1", status="paused")
    with pytest.raises(SystemExit, match="thread drop"):
        beat.update_thread(root, "TH1", status="dropped")
    with pytest.raises(SystemExit, match="bad next-review date"):
        beat.update_thread(root, "TH1", next_review="next week")
    with pytest.raises(SystemExit, match="no thread 'TH9'"):
        beat.update_thread(root, "TH9", status="open")


def test_drop_thread_records_reason_everywhere(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "Dead end", "arc")
    page = beat.drop_thread(root, "TH1", "records sealed until 2030")
    assert page.fm["status"] == "dropped"
    assert page.fm["dropped_reason"] == "records sealed until 2030"
    assert "Dropped: records sealed until 2030" in page.body
    events = read_jsonl(root / "coverage.jsonl")
    assert len(events) == 1
    assert events[0]["thread"] == "TH1"
    assert events[0]["note"] == "dropped: records sealed until 2030"
    assert events[0]["actor"] == "human:test"
    with pytest.raises(SystemExit, match="already dropped"):
        beat.drop_thread(root, "TH1", "again")


def test_th_ids_never_reused_after_page_deletion(tmp_path):
    root = make_beat(tmp_path)
    first = beat.add_thread(root, "one", "arc")
    assert first.id == "TH1"
    first.path.unlink()  # delete the page; the .flip/ids reservation remains
    assert beat.add_thread(root, "two", "arc").id == "TH2"
    assert "TH1" in pages.reserved_ids(root)


# ---------------------------------------------------------------- ranking


def test_rank_threads_defaults_missing_scores_to_half(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "unscored", "arc")
    ranked = beat.rank_threads(root)
    assert len(ranked) == 1
    assert ranked[0][0] == pytest.approx(0.5)  # 0.5 across all five dimensions


def test_rank_threads_weighted_sum_and_order(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "big", "arc", scores={"payoff": 0.9, "access": 0.6})
    beat.add_thread(root, "urgent", "vein", scores={"urgency": 0.9})
    ranked = beat.rank_threads(root)
    assert [p.id for _s, p in ranked] == ["TH1", "TH2"]
    # .3*.9 + .25*.6 + (.2+.15+.1)*.5 = .645; (.3+.25)*.5 + .2*.9 + (.15+.1)*.5 = .58
    assert ranked[0][0] == pytest.approx(0.645)
    assert ranked[1][0] == pytest.approx(0.58)


def test_rank_threads_excludes_settled_and_ties_break_on_id(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "a", "arc")
    beat.add_thread(root, "b", "arc")
    beat.add_thread(root, "c", "arc")
    beat.add_thread(root, "d", "arc")
    beat.update_thread(root, "TH3", status="dormant")
    beat.drop_thread(root, "TH4", "nothing there")
    ranked = beat.rank_threads(root)
    assert [p.id for _s, p in ranked] == ["TH1", "TH2"]  # equal scores: id order


def test_rank_threads_honors_manifest_weight_overrides(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "urgent", "vein", scores={"urgency": 1.0})
    b = beat.load_beat(root)
    b.weights = {"urgency": 1.0, "payoff": 0.0, "access": 0.0,
                 "connection": 0.0, "uniqueness": 0.0}
    beat.save_beat(root, b)
    assert beat.rank_threads(root)[0][0] == pytest.approx(1.0)


def test_rank_threads_unknown_weight_key_is_actionable(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "x", "arc")
    b = beat.load_beat(root)
    b.weights = {**beat.DEFAULT_WEIGHTS, "spice": 0.9}
    beat.save_beat(root, b)
    with pytest.raises(SystemExit, match="unknown weight 'spice'"):
        beat.rank_threads(root)


# ---------------------------------------------------------------- graduation


def test_graduate_end_to_end(tmp_path):
    from flip.manifest import load_manifest

    root = make_beat(tmp_path)
    beat.add_thread(root, "Bus contracts", "arc")
    nb = beat.graduate(root, "TH1", "bus-scout", kind="scout", title="Bus scout")

    assert nb == root / "notebooks" / "bus-scout"
    assert util.is_notebook_root(nb)
    m = load_manifest(nb)
    assert m.links == {"beat": "county:TH1"}  # child links back
    assert m.kind == "scout" and m.title == "Bus scout"

    thread = pages.find_by_id(root, "TH1")
    assert thread.fm["status"] == "active"
    assert thread.fm["notebook"] == "bus-scout"

    events = read_jsonl(root / "coverage.jsonl")
    assert events[-1]["thread"] == "TH1" and events[-1]["notebook"] == "bus-scout"

    # the beat's generated index lists the child
    body = pages.read_page(root / "index.md").body
    assert "* [Notebooks](notebooks/) - 1 child notebook" in body
    assert "[Bus scout](notebooks/bus-scout/) - scout · active" in body


def test_graduate_beat_link_uses_canonical_separator(tmp_path):
    # links.beat is written as "<beat-slug>:<TH#>" — the SPEC §9 ref grammar;
    # '#' is the deprecated form readers still accept until 0.10
    from flip.manifest import load_manifest

    root = make_beat(tmp_path)
    beat.add_thread(root, "Bus contracts", "arc")
    nb = beat.graduate(root, "TH1", "bus-scout")
    link = load_manifest(nb).links["beat"]
    assert "#" not in link
    assert util.parse_ref(link) == ("county", "TH1", False)  # not the deprecated form


def test_graduate_refusals(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "a", "arc")
    beat.add_thread(root, "b", "arc")
    beat.add_thread(root, "c", "arc")
    beat.graduate(root, "TH1", "a-scout")
    with pytest.raises(SystemExit, match="already graduated to notebook 'a-scout'"):
        beat.graduate(root, "TH1", "a-scout-2")
    with pytest.raises(SystemExit, match="slug 'a-scout' is taken"):
        beat.graduate(root, "TH2", "a-scout")
    beat.drop_thread(root, "TH2", "dead")
    with pytest.raises(SystemExit, match="TH2 is dropped"):
        beat.graduate(root, "TH2", "b-scout")
    with pytest.raises(SystemExit, match="no thread 'TH9'"):
        beat.graduate(root, "TH9", "c-scout")
    # a bad profile kind creates nothing under notebooks/
    with pytest.raises(SystemExit, match="unknown profile kind"):
        beat.graduate(root, "TH3", "c-scout", kind="no-such-kind")
    assert not (root / "notebooks" / "c-scout").exists()


# ---------------------------------------------------------------- generated views


def test_regenerate_threads_index_and_root_body(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "Bus contracts", "arc", scores={"payoff": 0.9, "access": 0.6})
    beat.drop_thread(root, "TH1", "dead")
    beat.add_thread(root, "Board money", "vein")
    listing = (root / "threads" / "index.md").read_text(encoding="utf-8")
    assert "* [Board money](board-money.md) - vein · open · score 0.50" in listing
    assert "* [Bus contracts](bus-contracts.md) - arc · dropped" in listing
    assert "score" not in listing.split("Bus contracts")[1].split("\n")[0]
    body = pages.read_page(root / "index.md").body
    assert "Cover the county" in body
    assert "* [Threads](threads/) - 2 threads, 1 open/active" in body


def test_beat_log_event_and_log_md(tmp_path):
    root = make_beat(tmp_path)
    row = beat.log_event(root, "swept the agendas")
    assert row["actor"] == "human:test"
    assert read_jsonl(root / "log" / "log.jsonl") == [row]
    log_md = (root / "log.md").read_text(encoding="utf-8")
    assert "# Update Log" in log_md and "swept the agendas" in log_md
    body = pages.read_page(root / "index.md").body
    assert "* [Update Log](log.md) - 1 logged event, newest first" in body


# ---------------------------------------------------------------- beat show


def make_busy_beat(tmp_path: Path) -> Path:
    root = make_beat(tmp_path)
    beat.add_thread(root, "Bus contracts", "arc", scores={"payoff": 0.9})
    beat.add_thread(root, "Board money", "vein")
    beat.add_thread(root, "Sleeper", "arc")
    beat.update_thread(root, "TH3", status="dormant", next_review="2020-01-01")
    beat.graduate(root, "TH1", "bus-scout", title="Bus scout")
    beat.log_event(root, "quarterly sweep")
    return root


def test_beat_show_text(tmp_path):
    root = make_busy_beat(tmp_path)
    out = beat.beat_show(root)
    assert out.splitlines()[0] == f"county · beat · active · {util.today()}"
    assert "mission: Cover the county" in out
    assert "THREADS (ranked)" in out
    assert "0.62 · TH1 · arc · active · Bus contracts · → bus-scout" in out
    assert "0.50 · TH2 · vein · open · Board money" in out
    assert "DORMANT PAST REVIEW" in out
    assert "TH3 · next_review 2020-01-01 · Sleeper" in out
    assert "bus-scout · scout · active · Bus scout" in out
    assert "quarterly sweep" in out


def test_beat_show_json_shape(tmp_path):
    root = make_busy_beat(tmp_path)
    data = beat.beat_show(root, as_data=True)
    assert data["slug"] == "county" and data["mission"] == "Cover the county"
    assert data["weights"]["payoff"] == pytest.approx(0.3)
    assert [t["id"] for t in data["threads"]] == ["TH1", "TH2"]
    assert data["threads"][0]["score"] == pytest.approx(0.62)
    assert data["threads"][0]["notebook"] == "bus-scout"
    assert [t["id"] for t in data["dormant_due"]] == ["TH3"]
    assert data["notebooks"][0]["slug"] == "bus-scout"
    assert data["recent_log"][-1]["text"] == "quarterly sweep"


def test_dormant_before_review_date_not_flagged(tmp_path):
    root = make_beat(tmp_path)
    beat.add_thread(root, "later", "arc")
    beat.update_thread(root, "TH1", status="dormant", next_review="2999-01-01")
    assert beat.beat_show(root, as_data=True)["dormant_due"] == []


# ---------------------------------------------------------------- CLI wiring


def test_cli_beat_new_and_thread_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = invoke(["beat", "new", "county", "--mission", "Cover the county"])
    assert result.exit_code == 0, result.output
    assert "created beat 'county'" in result.output

    monkeypatch.chdir(tmp_path / "county")
    result = invoke(["beat", "thread", "add", "Bus contracts", "--kind", "arc",
                     "--score", "payoff=0.9", "--score", "access=0.6"])
    assert result.exit_code == 0, result.output
    assert "TH1 · arc · open · Bus contracts" in result.output

    result = invoke(["beat", "thread", "update", "TH1", "--status", "dormant",
                     "--next-review", "2027-01-01"])
    assert result.exit_code == 0, result.output
    assert "TH1 · arc · dormant · next review 2027-01-01" in result.output

    result = invoke(["beat", "thread", "drop", "TH1", "--reason", "dead"])
    assert result.exit_code == 0, result.output
    assert "TH1 dropped · dead" in result.output

    result = invoke(["beat", "log", "swept"])
    assert result.exit_code == 0, result.output
    assert "logged" in result.output


def test_cli_bad_score_pair_is_actionable(tmp_path, monkeypatch):
    make_beat(tmp_path)
    monkeypatch.chdir(tmp_path / "county")
    result = invoke(["beat", "thread", "add", "x", "--kind", "arc", "--score", "payoff"])
    assert result.exit_code == 1
    assert "bad --score 'payoff'" in result.output


def test_cli_beat_commands_from_inside_child_notebook(tmp_path, monkeypatch):
    """The beat walk climbs past the notebook root: both layers work from
    inside notebooks/<slug>/ (SPEC §14)."""
    root = make_busy_beat(tmp_path)
    monkeypatch.chdir(root / "notebooks" / "bus-scout")

    result = invoke(["beat", "show"])
    assert result.exit_code == 0, result.output
    assert "county · beat · active" in result.output

    result = invoke(["beat", "thread", "add", "New angle", "--kind", "vein"])
    assert result.exit_code == 0, result.output
    assert (root / "threads" / "new-angle.md").is_file()  # landed in the BEAT

    # while notebook commands still resolve to the notebook itself
    result = invoke(["log", "notebook-level event"])
    assert result.exit_code == 0, result.output
    nb_log = read_jsonl(root / "notebooks" / "bus-scout" / "log" / "log.jsonl")
    assert [e["text"] for e in nb_log] == ["notebook-level event"]


def test_cli_beat_show_json(tmp_path, monkeypatch):
    root = make_busy_beat(tmp_path)
    monkeypatch.chdir(root)
    result = invoke(["beat", "show", "--json"])
    assert result.exit_code == 0, result.output
    import json

    data = json.loads(result.output)
    assert data["slug"] == "county"
    assert data["threads"][0]["id"] == "TH1"


def test_cli_beat_commands_outside_a_beat_fail_actionably(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for args in (["beat", "show"], ["beat", "log", "x"],
                 ["beat", "thread", "add", "x", "--kind", "arc"],
                 ["beat", "graduate", "TH1", "slug"]):
        result = invoke(args)
        assert result.exit_code == 1, args
        assert "not inside a flip beat" in result.output


def test_cli_graduate_then_notebook_flow(tmp_path, monkeypatch):
    root = make_beat(tmp_path)
    beat.add_thread(root, "Bus contracts", "arc")
    monkeypatch.chdir(root)
    result = invoke(["beat", "graduate", "TH1", "bus-scout", "--title", "Bus scout"])
    assert result.exit_code == 0, result.output
    assert "TH1 → scout notebook 'bus-scout'" in result.output
    monkeypatch.chdir(root / "notebooks" / "bus-scout")
    assert invoke(["show"]).exit_code == 0  # notebook hot view works in the child
