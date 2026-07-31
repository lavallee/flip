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

**Default conduct, and how to change it (SPEC §5.1).** flip-fetch ships an
opinionated default, not a rule. It presents a browser User-Agent, fetches one
named document with no link-following or recursion, and holds a per-host
cooldown across invocations.

The reasoning, since a default should be arguable: a UA string is a
self-declared compatibility hint, not an access control — Chrome still says
"Mozilla/5.0" because the string has been negotiated fiction since 1994.
Blanket UA blocking is a blunt platform default aimed at bulk scrapers, and a
person capturing a page they are about to read and cite is bycatch in that
fight. Measured: the self-identifying string earned a 403 from x.com that a
browser UA answered with 165KB of the document the user asked for.

Every part of that is a knob. `--user-agent` (the word `identify` selects
flip-fetch's own name), `--min-interval`, and the `FLIP_FETCH_UA` /
`FLIP_FETCH_MIN_INTERVAL` environment equivalents. A deployment whose work
calls for a different policy — announcing itself to a partner's API, pacing
far slower for a fragile host, or moving faster against infrastructure it owns
— sets one and owns the consequences. flip has no opinion it will enforce over
yours.

What flip-fetch does NOT vary is the record: `user_agent`, `strategy` and
`attempts` go into the capture row as they were actually used. That is not a
restriction on the operator, it is what a provenance tool is *for* — a
notebook that misreported how its bytes were obtained would be worthless to
the person who later has to trust it, including its own author.

The higher rungs are not implemented here rather than forbidden. Authenticated
capture is a first-class method (`browser-session`) for material you have
legitimate access to; point a lane at a fetcher that carries your session.
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
from typing import NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
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
# arXiv ids reach arXiv directly; everything else is treated as a DOI.
_ARXIV_ID_RE = re.compile(r"^(arxiv:)?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)
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


class Capture(NamedTuple):
    """One method's result: the bytes, where they canonically came from, and
    whatever that method wants added to the envelope."""

    body: bytes
    url: str
    mime: str | None
    extra: dict


def _method_http_get(target: str, timeout: float, sleep, _email: str | None) -> Capture:
    """Rung 1-2: the live URL, retried through what is transient."""
    body, final_url, mime, attempts = _get(target, timeout, sleep=sleep)
    return Capture(body, final_url, mime, {"attempts": attempts} if attempts > 1 else {})


def _method_archive_replay(target: str, timeout: float, sleep, _email: str | None) -> Capture:
    """Rung 3: a third-party web archive holds what the live host won't serve.

    Fetches the RAW replay (`…/<timestamp>id_/…`), not the rewritten one: the
    `id_` form returns the bytes as archived, without the archive's own toolbar
    and link-rewriting injected. Custody should hold the document, not a
    rendering of it inside someone's viewer.
    """
    api = "http://archive.org/wayback/available?url=" + quote(target, safe="")
    replay = ""
    try:
        meta_body, _, _, _ = _get(api, timeout, sleep=sleep)
        snapshot = (json.loads(meta_body).get("archived_snapshots") or {}).get("closest") or {}
        replay = str(snapshot.get("url") or "")
    except (HTTPError, URLError, OSError, ValueError) as exc:
        # The lookup API rate-limits shared addresses hard (429s are routine).
        # Retrying it harder is the mistake this ladder exists to avoid, so
        # fall through to the replay path, which answers when the API won't and
        # redirects to the nearest snapshot on its own.
        sys.stderr.write(
            f"flip-fetch: wayback lookup unavailable ({type(exc).__name__}); "
            "trying the replay path directly\n"
        )
    if not replay:
        replay = f"https://web.archive.org/web/2024/{target}"
    # …/web/20241225054341/https://… -> …/web/20241225054341id_/https://…
    # The `id_` form returns the bytes as archived, without the archive's
    # toolbar and link-rewriting injected into the document.
    raw = re.sub(r"(/web/\d+)/", r"\1id_/", replay, count=1)
    try:
        body, final_url, mime, attempts = _get(raw, timeout, sleep=sleep)
    except HTTPError as exc:
        # 404 from the archive means "we hold nothing for this URL" — report the
        # fact, not the status line, so the caller knows the search was made.
        if exc.code == 404:
            raise LookupError(f"no archived snapshot for {target}") from exc
        raise
    # The snapshot we actually landed on — after any redirect from a partial
    # timestamp — is the authority on when this evidence is from.
    landed = re.search(r"/web/(\d{4,14})(?:id_)?/", final_url or "")
    stamp = landed.group(1) if landed else ""
    extra = {"backend_ref": final_url or replay}
    if len(stamp) >= 8:
        # WHEN THE EVIDENCE IS FROM, which is not when we retrieved it. A claim
        # resting on an archived page rests on the page as it was that day.
        extra["archived_at"] = (
            f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[8:10] or '00'}:"
            f"{stamp[10:12] or '00'}:{stamp[12:14] or '00'}Z"
        )
    if attempts > 1:
        extra["attempts"] = attempts
    # the target is what the claim cites; the replay URL is how we reached it
    return Capture(body, target, mime, extra)


def _method_publisher_api(target: str, timeout: float, sleep, email: str | None) -> Capture:
    """Rung 4: ask the publisher or registry instead of scraping the landing page.

    arXiv ids go to arXiv. DOIs go to Crossref for metadata, then Unpaywall for
    a legal open-access full text when an operator email is configured
    (Unpaywall requires one and 422s without a real address). When only
    metadata is reachable the metadata IS the capture — but it is recorded as
    `metadata-only`, never as if the document had been retrieved.
    """
    bare = target[4:] if target.lower().startswith("doi:") else target
    if _ARXIV_ID_RE.match(bare):
        arx = bare.lower().removeprefix("arxiv:")
        body, final_url, mime, _ = _get(f"https://arxiv.org/pdf/{arx}", timeout, sleep=sleep)
        return Capture(body, f"https://arxiv.org/abs/{arx}", mime, {"backend_ref": f"arxiv:{arx}"})

    meta_url = f"https://api.crossref.org/works/{quote(bare, safe='/')}"
    if email:
        meta_url += f"?mailto={quote(email)}"
    meta_body, _, _, _ = _get(meta_url, timeout, sleep=sleep)
    try:
        work = json.loads(meta_body)["message"]
    except (ValueError, KeyError) as exc:
        raise LookupError(f"crossref returned no work for {bare}") from exc

    pdf_url = None
    if email:
        try:
            oa_body, _, _, _ = _get(
                f"https://api.unpaywall.org/v2/{quote(bare, safe='/')}?email={quote(email)}",
                timeout, sleep=sleep,
            )
            location = json.loads(oa_body).get("best_oa_location") or {}
            pdf_url = location.get("url_for_pdf") or location.get("url")
        except (HTTPError, URLError, OSError, ValueError):
            pdf_url = None  # no OA copy is a normal answer, not a failure
    if pdf_url:
        body, final_url, mime, _ = _get(pdf_url, timeout, sleep=sleep)
        return Capture(body, f"https://doi.org/{bare}", mime,
                       {"backend_ref": f"unpaywall:{bare}"})

    title = (work.get("title") or [""])[0]
    sys.stderr.write(
        f"flip-fetch: only metadata is reachable for {bare}"
        + ("" if email else " (no --email, so Unpaywall was not consulted)")
        + "\n  recording it as metadata-only — the document itself is NOT in custody;"
        " the ladder continues (a rendering fetcher, or save the PDF yourself)\n"
    )
    return Capture(
        json.dumps(work, indent=2).encode("utf-8"),
        f"https://doi.org/{bare}", "application/json",
        {"backend_ref": f"crossref:{bare}", "status": "metadata-only",
         "title": title or None},
    )


_METHODS = {
    "http-get": _method_http_get,
    "archive-replay": _method_archive_replay,
    "publisher-api": _method_publisher_api,
}


def fetch(url: str, dest: str | Path, timeout: float = 30, sleep=time.sleep,
          method: str = "http-get", email: str | None = None) -> int:
    """Capture `url` into `dest/` + a flip.json envelope. Returns an exit code.

    `sleep` is injectable so the retry rung can be tested without wall time."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    runner = _METHODS.get(method)
    if runner is None:
        sys.stderr.write(
            f"flip-fetch: unknown method {method!r} (implemented here: "
            f"{', '.join(_METHODS)}). Higher rungs of SPEC §5.1 — browser-render, "
            "browser-session, self-contained-archive — need a purpose-built fetcher\n"
        )
        return 2
    try:
        body, final_url, mime, extra = runner(url, timeout, sleep, email)
    except HTTPError as e:
        sys.stderr.write(
            f"flip-fetch: HTTP {e.code} {e.reason} for {url} (method {method})\n"
            + (
                "  the live URL refused us; the ladder continues above this rung — "
                "try --method archive-replay, --method publisher-api, or a "
                "rendering fetcher (SPEC §5.1)\n"
                if method == "http-get" else
                "  this rung could not serve it either; climb further or record the\n"
                "  exhausted search with `flip pass`\n"
            )
        )
        return 1
    except LookupError as e:
        sys.stderr.write(
            f"flip-fetch: {e}\n  nothing found at this rung — climb further, or "
            "record the exhausted search with `flip pass` so \"searched, gone\" "
            "stays distinguishable from \"did not look\"\n"
        )
        return 1
    except (URLError, OSError, ValueError) as e:
        sys.stderr.write(f"flip-fetch: {url} (method {method}): {e}\n")
        return 1

    (dest / f"capture{_MIME_EXT.get(mime or '', '.bin')}").write_bytes(body)
    envelope = {
        "title": _title(body, mime),
        "canonical_url": final_url,
        "mime": mime,
        # The METHOD, not this tool's name: `tool`/`tool_version` in the
        # provenance row already record the actor (SPEC §5.1).
        "strategy": method,
        # What we told the server we were. The ledger records the technique
        # even when the technique is a browser UA — provenance that hid this
        # would be the actual problem (SPEC §5.1).
        "user_agent": _UA,
        "status": "success",
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **extra,
    }
    envelope = {k: v for k, v in envelope.items() if v}
    (dest / "flip.json").write_text(json.dumps({"flip": envelope}), encoding="utf-8")
    return 0


# The identifying alternative, offered by name so choosing it is one word
# rather than a string to look up. Nothing prefers it or the default; they are
# different policies for different situations.
IDENTIFYING_UA = "flip-fetch (+https://github.com/lavallee/flip)"

_USAGE = """usage: flip-fetch [options] URL DEST

  A minimal stdlib web fetcher for flip's [fetchers] lanes:
    web = "flip-fetch {url} {dest}"

options:
  --method NAME         capture method (SPEC §5.1). Implemented here:
                          http-get         the live URL (default)
                          archive-replay   a web archive's copy, raw bytes
                          publisher-api    Crossref/Unpaywall/arXiv for a DOI or
                                           arXiv id — pass {id}, not {url}
                        Higher rungs (browser-render, browser-session,
                        self-contained-archive) need a purpose-built fetcher.
  --email ADDR          your address, for publisher-api. Unpaywall requires one
                        and refuses without a real address; it also opts you
                        into Crossref's polite pool.
  --user-agent STRING   what to present as. The literal word `identify` selects
                        flip-fetch's own name. Default: a browser string — see
                        SPEC §5.1 for the reasoning and its limits.
  --min-interval SECS   per-host cooldown, held across invocations. 0 disables.
  --timeout SECS        per-attempt socket timeout (default 30).

Defaults are an opinion, not a rule. Set a policy that fits your work; the
capture ledger records what was actually used either way.
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    global _UA, _MIN_HOST_INTERVAL
    positional, timeout, method, email = [], 30.0, "http-get", os.environ.get("FLIP_FETCH_EMAIL")
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            sys.stdout.write(_USAGE)
            return 0
        if arg in ("--user-agent", "--min-interval", "--timeout", "--method", "--email"):
            if i + 1 >= len(argv):
                sys.stderr.write(f"flip-fetch: {arg} needs a value\n")
                return 2
            value = argv[i + 1]
            try:
                if arg == "--user-agent":
                    _UA = IDENTIFYING_UA if value == "identify" else value
                elif arg == "--method":
                    method = value
                elif arg == "--email":
                    email = value
                elif arg == "--min-interval":
                    _MIN_HOST_INTERVAL = float(value)
                else:
                    timeout = float(value)
            except ValueError:
                sys.stderr.write(f"flip-fetch: {arg} expects a number, got {value!r}\n")
                return 2
            i += 2
            continue
        positional.append(arg)
        i += 1
    if len(positional) < 2:
        sys.stderr.write(_USAGE)
        return 2
    return fetch(positional[0], positional[1], timeout=timeout,
                 method=method, email=email)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
