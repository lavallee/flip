"""flip-fetch — an optional, zero-dependency web fetcher bundled with flip.

A standalone console script, **not** part of flip's library call path (which
stays network-free per SPEC §15). Point a `[fetchers]` lane at it for
out-of-the-box URL capture with no external tool installed:

    [fetchers]
    web = "flip-fetch {url} {dest}"

It fetches `{url}` with the Python standard library, writes the bytes into
`{dest}`, and emits a `flip` return envelope (title, canonical URL, retrieved-at,
mime, strategy) so the source page is well-formed. It is deliberately minimal —
a plain GET with a User-Agent. For JavaScript-rendered pages, paywalls, cookie
auth, or archival fallbacks, configure a purpose-built fetcher instead.
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_UA = "flip-fetch (+https://github.com/lavallee/flip)"
_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_MIME_EXT = {
    "text/html": ".html", "application/pdf": ".pdf", "application/json": ".json",
    "text/plain": ".txt", "application/xml": ".xml", "text/xml": ".xml",
}


def _title(body: bytes, mime: str | None) -> str | None:
    """Best-effort <title> for HTML; None for other types or when absent."""
    if not mime or "html" not in mime:
        return None
    m = _TITLE_RE.search(body)
    if not m:
        return None
    text = html.unescape(m.group(1).decode("utf-8", "replace"))
    text = " ".join(text.split())
    return text[:200] or None


def fetch(url: str, dest: str | Path, timeout: float = 30) -> int:
    """GET `url` into `dest/` + a flip.json envelope. Returns a process exit code."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit user capture
            body = resp.read()
            final_url = resp.geturl()
            mime = resp.headers.get_content_type() if resp.headers else None
    except HTTPError as e:
        sys.stderr.write(f"flip-fetch: HTTP {e.code} {e.reason} for {url}\n")
        return 1
    except (URLError, OSError, ValueError) as e:
        sys.stderr.write(f"flip-fetch: {url}: {e}\n")
        return 1

    (dest / f"capture{_MIME_EXT.get(mime or '', '.bin')}").write_bytes(body)
    envelope = {
        "title": _title(body, mime),
        "canonical_url": final_url,
        "mime": mime,
        "strategy": "flip-fetch",
        "status": "success",
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    envelope = {k: v for k, v in envelope.items() if v}
    (dest / "flip.json").write_text(json.dumps({"flip": envelope}), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        sys.stderr.write(
            "usage: flip-fetch URL DEST\n"
            "  a minimal stdlib web fetcher for flip's [fetchers] web lane:\n"
            '  web = "flip-fetch {url} {dest}"\n'
        )
        return 2
    return fetch(argv[0], argv[1])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
