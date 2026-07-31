"""flip-fetch — an optional, zero-dependency web fetcher bundled with flip.

A standalone console script, **not** part of flip's library call path (which
stays network-free per SPEC §15). Point a `[fetchers]` lane at it for
out-of-the-box URL capture with no external tool installed:

    [fetchers]
    web = "flip-fetch {url} {dest}"

It fetches `{url}` with the Python standard library, writes the bytes into
`{dest}`, and emits a `flip` return envelope (title, canonical URL, retrieved-at,
mime, strategy) so the source page is well-formed.

It climbs the first two rungs of the capture ladder (SPEC §5.1) and no further:
an identified GET, and backoff-retry on the statuses that mean "later, not
never". For JavaScript-rendered pages, paywalls, cookie auth, or archival
fallbacks, configure a purpose-built fetcher for the higher rungs.

**On the User-Agent.** flip-fetch identifies itself. Measured against live
sites, the old bare `flip-fetch (+url)` string was itself causing failures —
x.com answered it 403 and returned 165KB to a `Mozilla/5.0 (compatible; …)`
form of the same honest identification. So the default identifies flip inside
a compatibility-shaped string. Some WAFs block *any* self-identified agent
whatever it says; the answer to those is the archive rung, not pretending to
be a browser. `FLIP_FETCH_UA` overrides for operators who have decided
otherwise for their own deployment.
"""

from __future__ import annotations

import html
import json
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__

_UA = os.environ.get("FLIP_FETCH_UA") or (
    f"Mozilla/5.0 (compatible; flip-fetch/{__version__}; "
    "+https://github.com/lavallee/flip)"
)

# Statuses that mean "later, not never" — the rung-2 retry set. A 403/404 is a
# decision about us and retrying it unchanged is just noise; these are load,
# maintenance, and gateway conditions that commonly clear on their own.
_RETRY_STATUS = frozenset({429, 502, 503, 504})
_MAX_ATTEMPTS = 4
_BACKOFF_BASE = 1.5   # seconds; doubles per attempt
_RETRY_AFTER_CAP = 30  # honor the server's number, but never stall a capture
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


def _is_transient(exc: Exception) -> bool:
    """Is this network error worth another attempt?

    A timeout is — and measurably often it's a WAF stalling an unfamiliar
    client rather than a dead host. A refused connection or a name that
    doesn't resolve is NOT: nothing is listening and nothing will be. Retrying
    those is the mirror of the bug this ladder exists to fix — persistence
    aimed at the wrong failure is just a slower way to give up.
    """
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, TimeoutError):
            return True
        if isinstance(exc, (ConnectionRefusedError, socket.gaierror)):
            return False
        exc = getattr(exc, "reason", None) if isinstance(exc, URLError) else None
    return False


def _retry_after(exc: HTTPError, default: float) -> float:
    """The server's own Retry-After in seconds, capped. A server that tells us
    when to come back has given us better information than our backoff curve."""
    raw = exc.headers.get("Retry-After") if exc.headers else None
    try:
        return min(float(str(raw).strip()), _RETRY_AFTER_CAP)
    except (TypeError, ValueError):
        return default


def _get(url: str, timeout: float, sleep=time.sleep) -> tuple[bytes, str, str | None, int]:
    """Rungs 1-2: an identified GET, retried with backoff on transient statuses.

    Returns (body, final_url, mime, attempts). Raises the last error when the
    ladder's first two rungs are exhausted — the caller records that as a
    finding, because "we tried and it refused" is evidence and "we gave up on
    the first 429" is not.
    """
    delay = _BACKOFF_BASE
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
        try:
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit user capture
                mime = resp.headers.get_content_type() if resp.headers else None
                return resp.read(), resp.geturl(), mime, attempt
        except HTTPError as e:
            if e.code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS:
                raise
            wait = _retry_after(e, delay)
            sys.stderr.write(
                f"flip-fetch: HTTP {e.code} for {url} — retrying in {wait:g}s "
                f"(attempt {attempt}/{_MAX_ATTEMPTS})\n"
            )
        except (TimeoutError, URLError, OSError) as e:
            if attempt == _MAX_ATTEMPTS or not _is_transient(e):
                raise
            wait = delay
            sys.stderr.write(
                f"flip-fetch: {type(e).__name__} for {url} — retrying in {wait:g}s "
                f"(attempt {attempt}/{_MAX_ATTEMPTS})\n"
            )
        sleep(wait)
        delay *= 2
    raise AssertionError("unreachable")  # pragma: no cover


def fetch(url: str, dest: str | Path, timeout: float = 30, sleep=time.sleep) -> int:
    """GET `url` into `dest/` + a flip.json envelope. Returns a process exit code.

    `sleep` is injectable so the retry rung can be tested without wall time."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        body, final_url, mime, attempts = _get(url, timeout, sleep=sleep)
    except HTTPError as e:
        sys.stderr.write(
            f"flip-fetch: HTTP {e.code} {e.reason} for {url}\n"
            "  the live URL refused us; the ladder continues above this rung — "
            "try an archive replay, a publisher API, or a rendering fetcher "
            "(SPEC §5.1 capture methods)\n"
        )
        return 1
    except (URLError, OSError, ValueError) as e:
        sys.stderr.write(f"flip-fetch: {url}: {e}\n")
        return 1

    (dest / f"capture{_MIME_EXT.get(mime or '', '.bin')}").write_bytes(body)
    envelope = {
        "title": _title(body, mime),
        "canonical_url": final_url,
        "mime": mime,
        # The METHOD, not this tool's name: `tool`/`tool_version` in the
        # provenance row already record the actor (SPEC §5.1).
        "strategy": "http-get",
        "status": "success",
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if attempts > 1:
        envelope["attempts"] = attempts  # the retry rung did work; say so
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
