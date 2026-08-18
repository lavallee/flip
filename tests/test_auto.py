"""Tests for flip.auto — the loop frontier a standing mission re-grounds on.

The frontier is a view, like beat triage: computed, never stored, and never a
place flip decides to run anything. What these tests pin is that two agents
reading the same corpus get the same next item, and that nothing the frontier
cannot read disappears from it quietly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flip import auto, beat, claims, commissions, forecast, ledgers
from flip import sources as sources_mod


@pytest.fixture(autouse=True)
def _actor(monkeypatch):
    monkeypatch.setenv("FLIP_ACTOR", "agent:test")


def make_beat(tmp_path: Path, **auto_block) -> Path:
    root = tmp_path / "dataviz"
    beat.create_beat(root, "dataviz", mission="Track a moving practice")
    if auto_block:
        b = beat.load_beat(root)
        b.extras["auto"] = auto_block
        beat.save_beat(root, b)
    return root


def graduate_notebook(root: Path, title: str, slug: str) -> Path:
    thread = beat.add_thread(root, title, "arc")
    beat.graduate(root, thread.fm["id"], slug, kind="research-review")
    return root / "notebooks" / slug


def _source(nb: Path, tmp_path: Path, name: str = "paper.txt"):
    payload = tmp_path / name
    payload.write_text("evidence\n", encoding="utf-8")
    return sources_mod.add_source(nb, str(payload), note="primary")


# --- the auto: block ----------------------------------------------------------


def test_a_beat_without_an_auto_block_still_has_a_frontier(tmp_path):
    # The default lane order is the policy when nobody wrote one.
    root = make_beat(tmp_path)
    nb = graduate_notebook(root, "practitioners", "practitioners")
    ledgers.add_question(nb, "does it hold?")
    data = auto.frontier(root)
    assert auto.load_auto(beat.load_beat(root)) is None
    assert data["selection"] == list(auto.LANES)
    assert [r["id"] for r in data["items"]] == ["Q1"]


def test_the_auto_block_is_read_back_whole(tmp_path):
    root = make_beat(
        tmp_path,
        selection=["due", "open-question"],
        stop="no unblocked item this pass",
        authority="capture and publish; never delete custody",
        materiality="a reader-relevant public change, not a status edit",
        surfaces=["the public site"],
        cadence="daily",
    )
    a = auto.load_auto(beat.load_beat(root))
    assert a.selection == ("due", "open-question")
    assert a.stop == "no unblocked item this pass"
    assert a.materiality.startswith("a reader-relevant")
    assert a.surfaces == ("the public site",)
    # and it rides into the view, because the agent reading the frontier is
    # the one that has to honour it
    data = auto.frontier(root)
    assert data["stop"] == a.stop
    assert data["authority"] == a.authority
    assert data["surfaces"] == ["the public site"]


def test_a_mistyped_lane_is_refused_with_the_vocabulary(tmp_path):
    # A lane flip cannot compute is a priority nobody applies — and a loop
    # running a policy nobody wrote is the one failure an autonomous pass
    # cannot notice from the inside.
    root = make_beat(tmp_path, selection=["due", "open-questions"])
    with pytest.raises(SystemExit, match="unknown selection lane"):
        auto.frontier(root)


def test_a_non_block_auto_key_is_refused(tmp_path):
    root = tmp_path / "dataviz"
    beat.create_beat(root, "dataviz")
    b = beat.load_beat(root)
    b.extras["auto"] = "run it daily"
    beat.save_beat(root, b)
    with pytest.raises(SystemExit, match="must be a block of keys"):
        auto.frontier(root)


def test_unknown_auto_keys_ride_along_rather_than_being_dropped(tmp_path):
    # Same never-drop rule as the manifests: a key flip doesn't know is the
    # operator's, not litter.
    root = make_beat(tmp_path, stop="nothing unblocked", budget="500k tokens")
    a = auto.load_auto(beat.load_beat(root))
    assert a.extras == {"budget": "500k tokens"}


# --- the frontier itself --------------------------------------------------------


def test_every_lane_reports_with_its_reason(tmp_path):
    root = make_beat(tmp_path)
    nb = graduate_notebook(root, "practitioners", "practitioners")
    beat.add_thread(root, "a thread nobody graduated", "vein")

    src = _source(nb, tmp_path)
    claims.add_claim(nb, "the drop is real", [src.fm["id"]], load_bearing=True)
    k = commissions.add_commission(nb, "survey the cohort", "the corpus", "one pass",
                                   "no re-capture")
    commissions.set_commission_status(nb, k.fm["id"], "dispatched")
    forecast.add_forecast(nb, "will it persist?", "2020-01-15", ["a survey"],
                          "no survey runs", 0.6, 0.5)
    ledgers.add_question(nb, "does it hold at scale?")
    parked = ledgers.add_question(nb, "who verified it?")
    ledgers.dormant_question(nb, parked.fm["id"], until="2020-01-01")  # long due

    data = auto.frontier(root)
    lanes = [r["lane"] for r in data["items"]]
    assert lanes == ["in-flight", "commissioned", "due", "due", "open-question", "thread"]
    by_id = {r["id"]: r for r in data["items"]}
    assert "bar unmet" in by_id["C1"]["why"]
    assert "dispatched" in by_id["K1"]["why"]
    assert "overdue" in by_id["FC1"]["why"]
    assert "came due" in by_id["Q2"]["why"]
    assert by_id["K1"]["text"] == "survey the cohort"  # the deliverable, not a blank


def test_the_selection_order_is_the_beat_s_to_choose(tmp_path):
    root = make_beat(tmp_path, selection=["open-question", "in-flight"])
    nb = graduate_notebook(root, "practitioners", "practitioners")
    src = _source(nb, tmp_path)
    claims.add_claim(nb, "the drop is real", [src.fm["id"]], load_bearing=True)
    ledgers.add_question(nb, "does it hold?")

    lanes = [r["lane"] for r in auto.frontier(root)["items"]]
    assert lanes == ["open-question", "in-flight"]
    # a lane left out of the selection is left out of the frontier
    assert "thread" not in lanes


def test_a_graduated_thread_leaves_the_thread_lane(tmp_path):
    # Its notebook's own items are on the roster now; listing the thread too
    # would rank the same work twice.
    root = make_beat(tmp_path)
    nb = graduate_notebook(root, "practitioners", "practitioners")
    ledgers.add_question(nb, "does it hold?")
    data = auto.frontier(root)
    assert [r["lane"] for r in data["items"]] == ["open-question"]


def test_the_order_is_deterministic_across_notebooks(tmp_path):
    root = make_beat(tmp_path)
    first = graduate_notebook(root, "alpha work", "alpha")
    second = graduate_notebook(root, "beta work", "beta")
    for nb in (second, first):  # deliberately not slug order
        ledgers.add_question(nb, "does it hold?")
        ledgers.add_question(nb, "who says so?")
    rows = [(r["notebook"], r["id"]) for r in auto.frontier(root)["items"]]
    assert rows == [("alpha", "Q1"), ("alpha", "Q2"), ("beta", "Q1"), ("beta", "Q2")]
    assert rows == [(r["notebook"], r["id"]) for r in auto.frontier(root)["items"]]


def test_limit_trims_the_list_but_never_the_count(tmp_path):
    root = make_beat(tmp_path)
    nb = graduate_notebook(root, "practitioners", "practitioners")
    for n in range(4):
        ledgers.add_question(nb, f"question {n}?")
    data = auto.frontier(root, limit=2)
    assert len(data["items"]) == 2
    assert data["total"] == 4  # what was left out is still visible


def test_an_empty_frontier_says_the_stop_condition_decides(tmp_path):
    # "Nothing to do" and "done" are different findings, and flip cannot tell
    # them apart — the mission's stop condition is what does.
    root = make_beat(tmp_path, stop="no unblocked item this pass")
    graduate_notebook(root, "practitioners", "practitioners")
    data = auto.frontier(root)
    assert data["items"] == []
    assert "stop condition" in auto.render(data)


def test_an_unreadable_notebook_is_reported_not_skipped(tmp_path):
    # A pass that silently skipped a notebook looks exactly like a pass that
    # found nothing in it.
    root = make_beat(tmp_path)
    good = graduate_notebook(root, "good work", "good")
    bad = graduate_notebook(root, "bad work", "bad")
    ledgers.add_question(good, "does it hold?")
    (bad / "index.md").write_text("---\nslug: bad\nkind: [not, a, string]\n---\n# bad\n",
                                  encoding="utf-8")
    data = auto.frontier(root)
    assert [r["notebook"] for r in data["items"]] == ["good"]
    assert data["unreadable"] and data["unreadable"][0]["notebook"] == "bad"
    assert "!" in auto.render(data)


def test_frontier_never_mutates_the_beat_or_its_notebooks(tmp_path):
    from flip.util import sha256_file

    root = make_beat(tmp_path, stop="nothing unblocked")
    nb = graduate_notebook(root, "practitioners", "practitioners")
    ledgers.add_question(nb, "does it hold?")
    _source(nb, tmp_path)

    def snapshot():
        return {p.relative_to(root): sha256_file(p) for p in root.rglob("*") if p.is_file()}

    before = snapshot()
    auto.frontier(root)
    auto.frontier(root, limit=1)
    assert snapshot() == before


def test_outside_a_beat_the_error_says_so(tmp_path):
    with pytest.raises(SystemExit, match="beat"):
        auto.frontier(tmp_path)
