"""`flip source recheck` — the refresh receipt (SPEC §5.4).

A stub fetcher writes whatever /tmp payload the test points it at, so
unchanged/changed/gone are exercised against real capture machinery:
custody is never overwritten, the ledger gains a recheck event, the page
gains last_checked, and drift flags drive the source-drift /
drifted-evidence doctor warns.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from flip import claims, pages, scaffold, sources
from flip.doctor import run_doctor


PAYLOAD_FETCHER = (
    f'[fetchers]\nweb = "{sys.executable} -c '
    f"'import shutil,sys,os; shutil.copy(os.environ[\\\"RECHECK_PAYLOAD\\\"], "
    f"sys.argv[2] + \\\"/capture.txt\\\")' {{url}} {{dest}}\"\n"
)

FAILING_FETCHER = (
    f'[fetchers]\nweb = "{sys.executable} -c \'import sys; sys.exit(3)\' {{url}} {{dest}}"\n'
)


@pytest.fixture()
def notebook(tmp_path, monkeypatch):
    home = tmp_path / "fliphome"
    home.mkdir()
    (home / "config.toml").write_text(PAYLOAD_FETCHER, encoding="utf-8")
    monkeypatch.setenv("FLIP_HOME", str(home))
    payload = tmp_path / "payload.txt"
    payload.write_text("original bytes\n", encoding="utf-8")
    monkeypatch.setenv("RECHECK_PAYLOAD", str(payload))
    root = scaffold.create_notebook(tmp_path / "nb", "nb", "scout", title="t")
    page = sources.add_source(root, "https://example.test/doc")
    return root, page, payload, home


def _events(root: Path) -> list[dict]:
    text = (root / "sources" / "_provenance.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_unchanged_stamps_last_checked_and_clears_nothing(notebook):
    root, page, payload, _ = notebook
    out = sources.recheck_source(root, page.id)
    assert out["result"] == "unchanged"
    fm = pages.read_page(page.path).fm
    assert fm["last_checked"] and "drifted" not in fm
    ev = _events(root)[-1]
    assert ev["event"] == "recheck" and ev["result"] == "unchanged"
    assert ev["sha256_now"] == ev["sha256_captured"]


def test_changed_sets_drift_and_custody_survives(notebook):
    root, page, payload, _ = notebook
    before = (root / "sources" / "raw" / page.id / "capture.txt").read_bytes()
    payload.write_text("the world moved on\n", encoding="utf-8")
    out = sources.recheck_source(root, page.id)
    assert out["result"] == "changed"
    fm = pages.read_page(page.path).fm
    assert fm["drifted"] == "changed"
    # custody: the captured bytes are untouched
    assert (root / "sources" / "raw" / page.id / "capture.txt").read_bytes() == before
    ev = _events(root)[-1]
    assert ev["result"] == "changed" and ev["sha256_now"] != ev["sha256_captured"]


def test_gone_when_fetch_fails(notebook, tmp_path, monkeypatch):
    root, page, _, home = notebook
    (home / "config.toml").write_text(FAILING_FETCHER, encoding="utf-8")
    out = sources.recheck_source(root, page.id)
    assert out["result"] == "gone"
    fm = pages.read_page(page.path).fm
    assert fm["drifted"] == "gone"
    ev = _events(root)[-1]
    assert ev["result"] == "gone" and "error" in ev and "sha256_now" not in ev


def test_recheck_after_drift_resolves_clears_flag(notebook):
    root, page, payload, _ = notebook
    payload.write_text("the world moved on\n", encoding="utf-8")
    sources.recheck_source(root, page.id)
    payload.write_text("original bytes\n", encoding="utf-8")
    out = sources.recheck_source(root, page.id)
    assert out["result"] == "unchanged"
    assert "drifted" not in pages.read_page(page.path).fm


def test_local_file_source_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "h"))
    root = scaffold.create_notebook(tmp_path / "nb2", "nb2", "scout", title="t")
    f = tmp_path / "data.csv"
    f.write_text("x\n", encoding="utf-8")
    page = sources.add_source(root, str(f))
    with pytest.raises(SystemExit) as exc:
        sources.recheck_source(root, page.id)
    assert "no URL coordinate" in str(exc.value)


def test_doctor_warns_on_drift_and_load_bearing_claims(notebook):
    root, page, payload, _ = notebook
    sources.grade_source(root, page.id, independence="independent",
                         basis="official-record")
    claims.add_claim(root, "the claim", [page.id], load_bearing=True)
    payload.write_text("moved\n", encoding="utf-8")
    sources.recheck_source(root, page.id)
    codes = {f.code for f in run_doctor(root)}
    assert "source-drift" in codes and "drifted-evidence" in codes
