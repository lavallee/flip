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
a GET, and backoff-retry on the statuses that mean "later, not never". For
JavaScript-rendered pages, paywalls, cookie auth, or archival fallbacks,
configure a purpose-built fetcher for the higher rungs.

**On the User-Agent, and the conduct it implies (SPEC §5.1).** flip-fetch
presents a browser User-Agent by default. The reasoning, because this is a
choice and not an accident:

A UA string is a self-declared compatibility hint, not an access control —
Chrome still says "Mozilla/5.0" because the string has been negotiated fiction
since 1994. Blanket UA blocking is a blunt platform default aimed at bulk
scrapers, and a person capturing a page they are about to read and cite is
bycatch in that fight, not its target. Measured: the old self-identifying
string earned a 403 from x.com that a browser UA answered with 165KB of the
document the user asked for.

What makes that defensible is the rest of the behaviour, which is enforced
here rather than merely claimed:

- **One URL, no crawl.** flip-fetch follows no links and has no recursion. It
  structurally cannot strip-mine; it fetches the thing you named.
- **Human-scale pacing.** A per-host cooldown (`_MIN_HOST_INTERVAL`) applies
  across invocations, so an agent looping `add-source` still behaves like a
  reader rather than a crawler.
- **The ledger records what we presented as.** `user_agent` goes into the
  capture row. Provenance never lies about the technique — that is the whole
  point of the notebook, and it is what separates this from evasion.

Out of bounds, and not implemented here: defeating authentication or paywalls,
solving human-presence challenges, rotating addresses to evade a block, and
volume that imposes real cost. Those are access controls or are someone else's
bill; a UA heuristic is neither. Custody is also not republication — capturing
a page for citation says nothing about the right to redistribute its bytes.

`FLIP_FETCH_UA` and `FLIP_FETCH_MIN_INTERVAL` override both defaults.
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
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_UA = os.environ.get("FLIP_FETCH_UA") or (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

# Human-scale pacing, enforced across invocations so an agent looping
# `flip add-source` still reads like a person rather than a crawler. This is
# the behaviour that earns the UA choice above; it is not decoration.
_MIN_HOST_INTERVAL = float(os.environ.get("FLIP_FETCH_MIN_INTERVAL") or 1.0)

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


def _state_path() -> Path:
    """Where the per-host clock lives — beside the integration config."""
    home = os.environ.get("FLIP_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".flip"
    return base / ".fetch-hosts.json"


def _pace(url: str, sleep=time.sleep) -> float:
    """Wait out the per-host cooldown; returns the seconds actually slept.

    Fail-open by design: a corrupt or unwritable state file must never break a
    capture. The politeness is real but it is not a lock, and losing it is
    strictly better than losing the user's source.
    """
    if _MIN_HOST_INTERVAL <= 0:
        return 0.0
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return 0.0
    path = _state_path()
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    waited = 0.0
    last = state.get(host)
    if isinstance(last, (int, float)):
        # wall-clock, so the cooldown survives separate `flip add-source` runs
        elapsed = time.time() - last
        if 0 <= elapsed < _MIN_HOST_INTERVAL:
            waited = _MIN_HOST_INTERVAL - elapsed
            sleep(waited)
    state[host] = time.time()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass
    return waited


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
    """Rungs 1-2: a paced GET, retried with backoff on transient statuses.

    Returns (body, final_url, mime, attempts). Raises the last error when the
    ladder's first two rungs are exhausted — the caller records that as a
    finding, because "we tried and it refused" is evidence and "we gave up on
    the first 429" is not.
    """
    _pace(url, sleep=sleep)
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
        # What we told the server we were. The ledger records the technique
        # even when the technique is a browser UA — provenance that hid this
        # would be the actual problem (SPEC §5.1).
        "user_agent": _UA,
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
