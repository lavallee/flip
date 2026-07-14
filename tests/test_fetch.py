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

import pytest

from flip import fetch, pages, sources

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
    assert env["strategy"] == "flip-fetch"
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
    assert ev["strategy"] == "flip-fetch"
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
