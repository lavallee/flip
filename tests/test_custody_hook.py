"""The custody hook's whole value is that an operator leaves it on.

So the tests that matter most are the silence tests. A hook that fires outside
a notebook, or on every call, or on a source that WAS captured, gets turned
off — and a hook that is off enforces nothing. Over-reporting is the failure
mode being defended against here, not under-reporting.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "custody_hook.py"


def run(payload: dict, cache: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload), text=True, capture_output=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(cache), "XDG_CACHE_HOME": str(cache)},
    )
    return proc.returncode, proc.stdout.strip()


@pytest.fixture
def notebook(tmp_path):
    root = tmp_path / "nb"
    (root / "sources").mkdir(parents=True)
    (root / "references").mkdir()
    (root / "index.md").write_text(
        "---\nokf_version: '0.2'\nflip: '0.8'\nslug: nb\n---\n# nb\n", encoding="utf-8")
    (root / "sources" / "_provenance.jsonl").write_text("", encoding="utf-8")
    return root


def fetched(nb, url, session="s", cwd=None):
    return {"cwd": str(cwd or nb), "hook_event_name": "PostToolUse",
            "tool_name": "WebFetch", "session_id": session, "tool_input": {"url": url}}


# --- silence ---------------------------------------------------------------


def test_silent_outside_a_flip_notebook(tmp_path):
    """The most important test in the file. Most directories are not
    notebooks, and a research-discipline reminder fired in a codebase is
    noise that trains the reader to skip it."""
    plain = tmp_path / "somewhere"
    plain.mkdir()
    code, out = run({"cwd": str(plain), "hook_event_name": "PreToolUse",
                     "tool_name": "WebFetch", "session_id": "s"}, tmp_path / "c")
    assert code == 0 and out == ""


def test_silent_on_an_index_md_that_is_not_a_flip_manifest(tmp_path):
    """Plenty of directories have an index.md. The `flip:` key is the marker."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "index.md").write_text("---\ntitle: Home\n---\n# Home\n", encoding="utf-8")
    code, out = run({"cwd": str(d), "hook_event_name": "PreToolUse",
                     "tool_name": "WebFetch", "session_id": "s"}, tmp_path / "c")
    assert code == 0 and out == ""


def test_never_fires_on_websearch(notebook, tmp_path):
    """Discovery is capture-free by doctrine (SPEC §5): a search returns leads,
    and a lead is not evidence. Nagging on search is how this becomes noise."""
    code, out = run({"cwd": str(notebook), "hook_event_name": "PreToolUse",
                     "tool_name": "WebSearch", "session_id": "s"}, tmp_path / "c")
    assert code == 0 and out == ""


def test_pretooluse_notice_fires_once_per_session(notebook, tmp_path):
    cache = tmp_path / "c"
    payload = {"cwd": str(notebook), "hook_event_name": "PreToolUse",
               "tool_name": "WebFetch", "session_id": "s"}
    _, first = run(payload, cache)
    assert "flip add-source" in json.loads(first)["hookSpecificOutput"]["additionalContext"]
    assert run(payload, cache)[1] == ""
    assert run(payload, cache)[1] == ""


def test_stop_is_silent_when_nothing_was_fetched(notebook, tmp_path):
    code, out = run({"cwd": str(notebook), "hook_event_name": "Stop",
                     "session_id": "s"}, tmp_path / "c")
    assert code == 0 and out == ""


# --- the report ------------------------------------------------------------


def test_stop_reports_only_what_never_entered_custody(notebook, tmp_path):
    cache = tmp_path / "c"
    (notebook / "sources" / "_provenance.jsonl").write_text(
        json.dumps({"source_id": "P1", "url": "https://arxiv.org/abs/2606.15136",
                    "local_path": "sources/raw/P1.pdf"}) + "\n", encoding="utf-8")
    run(fetched(notebook, "https://arxiv.org/abs/2606.15136"), cache)
    run(fetched(notebook, "https://example.com/uncaptured-thing"), cache)

    _, out = run({"cwd": str(notebook), "hook_event_name": "Stop",
                  "session_id": "s"}, cache)
    reason = json.loads(out)["reason"]
    assert "example.com/uncaptured-thing" in reason
    assert "2606.15136" not in reason


def test_a_captured_paper_is_recognized_across_url_variants(notebook, tmp_path):
    """abs/, pdf/, html/ and an ar5iv mirror are one document and four URLs.
    Raw URL equality would report every one of them as a gap — which is the
    false positive that gets the hook disabled."""
    cache = tmp_path / "c"
    (notebook / "sources" / "_provenance.jsonl").write_text(
        json.dumps({"source_id": "P1", "url": "arXiv:2507.19969"}) + "\n", encoding="utf-8")
    for variant in ("https://arxiv.org/abs/2507.19969",
                    "https://arxiv.org/pdf/2507.19969",
                    "https://arxiv.org/html/2507.19969v2"):
        run(fetched(notebook, variant), cache)
    _, out = run({"cwd": str(notebook), "hook_event_name": "Stop",
                  "session_id": "s"}, cache)
    assert out == ""


def test_a_doi_recorded_without_bytes_still_counts_as_custody(notebook, tmp_path):
    """`--record` is the ladder's terminus, not a gap: a document out of reach
    but citable is a custody DECISION, and re-reporting it would punish the
    operator for doing the right thing."""
    cache = tmp_path / "c"
    (notebook / "references" / "gated-paper.md").write_text(
        "---\nid: P1\nresource: doi:10.1234/gated\nmethod: record-only\n---\n",
        encoding="utf-8")
    run(fetched(notebook, "https://doi.org/10.1234/gated"), cache)
    _, out = run({"cwd": str(notebook), "hook_event_name": "Stop",
                  "session_id": "s"}, cache)
    assert out == ""


def test_stop_reports_once_and_never_loops(notebook, tmp_path):
    """A Stop hook that blocks on every stop is an infinite loop wearing a
    reminder's clothes."""
    cache = tmp_path / "c"
    run(fetched(notebook, "https://example.com/x"), cache)
    stop = {"cwd": str(notebook), "hook_event_name": "Stop", "session_id": "s"}
    assert "example.com/x" in run(stop, cache)[1]
    assert run(stop, cache)[1] == ""
    assert run(stop, cache)[1] == ""


def test_sessions_do_not_leak_into_each_other(notebook, tmp_path):
    cache = tmp_path / "c"
    run(fetched(notebook, "https://example.com/one", session="a"), cache)
    assert run({"cwd": str(notebook), "hook_event_name": "Stop",
                "session_id": "b"}, cache)[1] == ""


def test_finds_the_notebook_from_a_subdirectory(notebook, tmp_path):
    """Work happens in drafts/ and research/, not at the root."""
    sub = notebook / "research" / "track-reports"
    sub.mkdir(parents=True)
    cache = tmp_path / "c"
    _, out = run({"cwd": str(sub), "hook_event_name": "PreToolUse",
                  "tool_name": "WebFetch", "session_id": "s"}, cache)
    assert "additionalContext" in out


# --- never break a session -------------------------------------------------


def test_malformed_payload_is_not_an_error(tmp_path):
    proc = subprocess.run([sys.executable, str(HOOK)], input="not json",
                          text=True, capture_output=True)
    assert proc.returncode == 0 and proc.stdout.strip() == ""


def test_unreadable_provenance_does_not_raise(notebook, tmp_path):
    cache = tmp_path / "c"
    run(fetched(notebook, "https://example.com/x"), cache)
    (notebook / "sources" / "_provenance.jsonl").write_bytes(b"\xff\xfe not text \x00")
    code, out = run({"cwd": str(notebook), "hook_event_name": "Stop",
                     "session_id": "s"}, cache)
    assert code == 0 and "example.com/x" in out
