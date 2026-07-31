"""Tests for flip.fetch — the bundled zero-dependency flip-fetch web helper.

A local HTTP server exercises the real GET path (no outbound network), and one
end-to-end case drives it through `add_source` so the envelope harvest chain is
proven with the actual shipped fetcher.
"""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError

import pytest

from flip import fetch, pages, sources


@pytest.fixture(autouse=True)
def _isolate_pacing(tmp_path, monkeypatch):
    """Every fetch test gets its own FLIP_HOME and no cooldown.

    Two reasons: the per-host clock is a real file and must never be written to
    the developer's own ~/.flip during a test run, and a shared clock would make
    the retry tests order-dependent. The pacing tests re-enable it explicitly.
    """
    monkeypatch.setenv("FLIP_HOME", str(tmp_path / "flip-home"))
    monkeypatch.setattr(fetch, "_MIN_HOST_INTERVAL", 0)
    yield

HTML = b"<html><head><title>Hello &amp; Bye</title></head><body>hi there</body></html>"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/missing":
            self.send_error(404, "gone")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML)

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def base_url():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


def test_fetch_writes_capture_and_envelope(tmp_path, base_url):
    dest = tmp_path / "raw"
    assert fetch.fetch(base_url + "/page", dest) == 0
    assert (dest / "capture.html").read_bytes() == HTML
    env = json.loads((dest / "flip.json").read_text())["flip"]
    assert env["title"] == "Hello & Bye"  # <title> extracted and unescaped
    assert env["mime"] == "text/html"
    # the METHOD, not the tool name: `tool`/`tool_version` record the actor
    assert env["strategy"] == "http-get"
    assert env["canonical_url"].startswith("http://127.0.0.1")
    assert env["retrieved_at"].endswith("Z")


def test_fetch_http_error_returns_1(tmp_path, base_url):
    assert fetch.fetch(base_url + "/missing", tmp_path / "d") == 1


def test_fetch_unreachable_host_returns_1(tmp_path):
    assert fetch.fetch("http://127.0.0.1:1/nope", tmp_path / "d", timeout=2) == 1


def test_title_none_for_non_html():
    assert fetch._title(b"{}", "application/json") is None
    assert fetch._title(b"<title>x</title>", None) is None


def test_main_usage_error(capsys):
    assert fetch.main([]) == 2
    assert "usage: flip-fetch" in capsys.readouterr().err


def test_add_source_through_bundled_fetch(tmp_path, base_url, monkeypatch):
    # the whole chain: [fetchers] web = flip-fetch → add_source harvests the
    # envelope (title/mime onto the page, strategy into provenance).
    root = tmp_path / "nb"
    root.mkdir()
    (root / "index.md").write_text(
        '---\nokf_version: "0.1"\nflip: "0.4"\nslug: nb\nkind: scout\n'
        "status: active\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n# nb\n",
        encoding="utf-8",
    )
    root = root.resolve()
    home = tmp_path / "home"
    home.mkdir()
    # invoke the fetcher as a module so the test never depends on PATH
    (home / "config.toml").write_text(
        f'[fetchers]\nweb = "{sys.executable} -m flip.fetch {{url}} {{dest}}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FLIP_HOME", str(home))

    page = sources.add_source(root, base_url + "/story")

    assert page.fm["title"] == "Hello & Bye"
    assert page.fm["local"].endswith("capture.html")
    ev = [json.loads(line) for line in
          (root / "sources" / "_provenance.jsonl").read_text().splitlines()][0]
    assert ev["strategy"] == "http-get"  # method, not actor (SPEC §5.1)
    assert ev["mime"] == "text/html"
    on_disk = pages.read_page(page.path)
    assert on_disk.fm["title"] == "Hello & Bye"


def test_flip_fetch_module_runs_as_main(tmp_path, base_url):
    # `python -m flip.fetch URL DEST` is the invocation config points at
    dest = tmp_path / "d"
    rc = subprocess.run(
        [sys.executable, "-m", "flip.fetch", base_url + "/p", str(dest)],
        capture_output=True,
    ).returncode
    assert rc == 0
    assert (dest / "capture.html").is_file()


# --- the capture ladder, rungs 1-2 ----------------------------------------------


def test_user_agent_presents_as_a_browser():
    # Stance (SPEC §5.1): a UA is a compatibility hint, not an access control,
    # and blanket UA blocking is aimed at bulk scrapers — a reader capturing a
    # page to cite it is bycatch. Measured: the self-identifying string earned
    # a 403 from x.com that a browser UA answered with 165KB.
    assert fetch._UA.startswith("Mozilla/5.0 (")
    assert "flip" not in fetch._UA.lower()


def test_the_ledger_records_what_we_presented_as(tmp_path, monkeypatch):
    # The condition that makes the UA choice defensible rather than evasive:
    # provenance never lies about the technique.
    monkeypatch.setattr(fetch, "urlopen", _Flaky(None, fails=0))
    fetch.fetch("https://example.com", tmp_path / "d", sleep=lambda _: None)
    env = json.loads((tmp_path / "d" / "flip.json").read_text())["flip"]
    assert env["user_agent"] == fetch._UA


def test_user_agent_is_overridable(monkeypatch):
    monkeypatch.setenv("FLIP_FETCH_UA", "my-deployment/1.0")
    import importlib

    reloaded = importlib.reload(fetch)
    try:
        assert reloaded._UA == "my-deployment/1.0"
    finally:
        monkeypatch.delenv("FLIP_FETCH_UA")
        importlib.reload(fetch)


class _Flaky:
    """urlopen stand-in: fails `fails` times with `exc`, then succeeds."""

    def __init__(self, exc, fails):
        self.exc, self.fails, self.calls = exc, fails, 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        if self.exc is not None and self.calls <= self.fails:
            raise self.exc
        return _Resp()


class _Resp:
    headers = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"<title>ok</title><p>" + b"x" * 4000

    def geturl(self):
        return "https://example.com/final"


def _http_error(code, retry_after=None):
    import email.message

    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return HTTPError("https://example.com", code, "boom", headers, None)


def test_transient_status_is_retried_then_succeeds(tmp_path, monkeypatch):
    # The behaviour this exists to change: one 429 is not a reason to stop.
    flaky = _Flaky(_http_error(429), fails=2)
    monkeypatch.setattr(fetch, "urlopen", flaky)
    slept = []
    assert fetch.fetch("https://example.com", tmp_path / "d", sleep=slept.append) == 0
    assert flaky.calls == 3
    assert slept == [1.5, 3.0]  # backoff doubles
    env = json.loads((tmp_path / "d" / "flip.json").read_text())["flip"]
    assert env["attempts"] == 3  # the retry work is on the record
    assert env["strategy"] == "http-get"


def test_retry_honours_the_servers_retry_after(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "urlopen", _Flaky(_http_error(503, retry_after=7), fails=1))
    slept = []
    assert fetch.fetch("https://example.com", tmp_path / "d", sleep=slept.append) == 0
    assert slept == [7.0]  # the server's number beats our curve


def test_retry_after_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "urlopen", _Flaky(_http_error(429, retry_after=9999), fails=1))
    slept = []
    fetch.fetch("https://example.com", tmp_path / "d", sleep=slept.append)
    assert slept == [float(fetch._RETRY_AFTER_CAP)]


def test_a_decision_about_us_is_not_retried(tmp_path, monkeypatch):
    # 403/404 mean "no", not "later" — retrying unchanged is noise, and the
    # error points at the next rung instead.
    flaky = _Flaky(_http_error(403), fails=99)
    monkeypatch.setattr(fetch, "urlopen", flaky)
    slept = []
    assert fetch.fetch("https://example.com", tmp_path / "d", sleep=slept.append) == 1
    assert flaky.calls == 1 and slept == []


def test_exhausted_retries_give_up_and_point_up_the_ladder(tmp_path, monkeypatch, capsys):
    flaky = _Flaky(_http_error(503), fails=99)
    monkeypatch.setattr(fetch, "urlopen", flaky)
    assert fetch.fetch("https://example.com", tmp_path / "d", sleep=lambda _: None) == 1
    assert flaky.calls == fetch._MAX_ATTEMPTS
    assert "archive replay" in capsys.readouterr().err


def test_refused_and_unresolvable_are_not_transient():
    import socket as _socket

    assert fetch._is_transient(URLError(TimeoutError("slow"))) is True
    assert fetch._is_transient(TimeoutError("slow")) is True
    assert fetch._is_transient(URLError(ConnectionRefusedError("nope"))) is False
    assert fetch._is_transient(URLError(_socket.gaierror("no such host"))) is False


def test_unreachable_host_is_not_retried(tmp_path):
    # nothing is listening; persistence aimed at the wrong failure is just a
    # slower way to give up (and it used to make this test take 10s)
    slept = []
    assert fetch.fetch("http://127.0.0.1:1/nope", tmp_path / "d", timeout=2,
                       sleep=slept.append) == 1
    assert slept == []


# --- human-scale pacing: the behaviour that earns the UA choice -----------------


def test_per_host_cooldown_applies_across_invocations(tmp_path, monkeypatch):
    # An agent looping `flip add-source` must still read like a person. The
    # clock lives on disk precisely because each fetch is a separate process.
    monkeypatch.setattr(fetch, "_MIN_HOST_INTERVAL", 5.0)
    slept = []
    assert fetch._pace("https://example.com/a", sleep=slept.append) == 0.0  # first: free
    waited = fetch._pace("https://example.com/b", sleep=slept.append)
    assert 0 < waited <= 5.0 and slept and slept[-1] == waited


def test_cooldown_is_per_host_not_global(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_MIN_HOST_INTERVAL", 5.0)
    assert fetch._pace("https://a.example/x", sleep=lambda _: None) == 0.0
    assert fetch._pace("https://b.example/y", sleep=lambda _: None) == 0.0  # different host


def test_pacing_fails_open_on_an_unusable_state_file(tmp_path, monkeypatch):
    # Politeness is real but it is not a lock: losing it must never cost the
    # user their source.
    monkeypatch.setattr(fetch, "_MIN_HOST_INTERVAL", 5.0)
    state = fetch._state_path()
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{ not json", encoding="utf-8")
    assert fetch._pace("https://example.com/a", sleep=lambda _: None) == 0.0


def test_pacing_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_MIN_HOST_INTERVAL", 0)
    for _ in range(3):
        assert fetch._pace("https://example.com/a", sleep=lambda _: None) == 0.0
