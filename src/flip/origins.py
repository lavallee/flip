"""Where a source's content comes from (SPEC §5.4, "Origin").

`independence: derivative` says a source republishes something. It never said
WHAT, and the corroboration count could not see it: two captures of one wire
story, or a report quoting another report's figure, counted as two independent
paths to the fact when they are one. This module is the record that says what,
and the place the count reads it.

**The record.** `origin:` on a source page, set by `flip source origin`:

    origin: {republishes: A14, because: "AP copy, same byline and text", by, at}
    origin: {ref: "https://example.org/report", because: "…", by, at}

`republishes` names another source in this notebook; `ref` names an origin the
notebook does not hold (a URL, a DOI, any identifier). Both may be given. The
judgment is authored, with a reason, by a named actor, like a grade; flip does
not infer it, because nothing in the bytes says that one report took its
figure from another.

**How it is used.** Every source has an *origin key*: follow `republishes`
until it stops (a cycle cannot be written, and a hand-made one stops where it
would repeat); a source whose chain ends in an external `ref` keys on that ref
— or on the held source whose own address is that ref, when there is one — and
a source with no origin record keys on itself. Corroboration counts DISTINCT
KEYS among the sources it would otherwise count, so sources that share an
origin count once, and every surface that shows the count can say which
sources were collapsed and why (`collapsed`).

A notebook that records no origin gets exactly the number it always got: with
no `origin:` key on any page, every source keys on itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import events, manifest, pages, util

_SOURCE_ID_RE = re.compile(r"^[A-Z]+\d+$")
# Query parameters that say how someone arrived, never which document it is.
_TRACKING = re.compile(r"^(utm_[a-z]+|fbclid|gclid|mc_cid|mc_eid|ref_src)$", re.IGNORECASE)


def record(fm: dict) -> dict | None:
    """A source page's origin record, or None."""
    value = fm.get("origin")
    if not isinstance(value, dict):
        return None
    if not str(value.get("republishes") or "").strip() and not str(value.get("ref") or "").strip():
        return None
    return value


def canonical(url: object) -> str:
    """The form two spellings of one address share, for comparison only:
    scheme and host lowercased, a leading `www.` dropped, the fragment and a
    trailing slash dropped, tracking parameters removed. Not a URL: a key."""
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc:
        return text.rstrip("/")
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not _TRACKING.match(k)])
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), query, ""))


def _address(fm: dict) -> str:
    resource = str(fm.get("resource") or fm.get("url") or "")
    return canonical(resource) if "://" in resource else ""


class Keys:
    """Origin keys over one set of source pages. Build once per read."""

    def __init__(self, source_fms: list[dict]) -> None:
        self.by_id = {str(fm.get("id")): fm for fm in source_fms if fm.get("id")}
        self.any = any(record(fm) for fm in self.by_id.values())
        self.owner: dict[str, str] = {}
        if self.any:
            for sid in sorted(self.by_id, key=_id_key):
                address = _address(self.by_id[sid])
                if address and address not in self.owner:
                    self.owner[address] = sid
        self._memo: dict[str, str] = {}

    def key(self, sid: str) -> str:
        """`source:<id>` or `ref:<canonical ref>` — equal keys, one origin."""
        if not self.any:
            return f"source:{sid}"
        if sid not in self._memo:
            self._memo[sid] = self._walk(sid)
        return self._memo[sid]

    def _walk(self, sid: str) -> str:
        seen: set[str] = set()
        current = sid
        while True:
            seen.add(current)
            fm = self.by_id.get(current)
            origin = record(fm) if fm is not None else None
            if origin is None:
                return f"source:{current}"
            nxt = str(origin.get("republishes") or "").strip()
            if nxt and nxt not in seen and nxt in self.by_id:
                current = nxt
                continue
            if nxt and nxt not in self.by_id:
                return f"source:{nxt}"  # a held id that went missing: still one origin
            ref = canonical(origin.get("ref"))
            if ref:
                owner = self.owner.get(ref)
                if owner and owner not in seen:
                    current = owner
                    continue
                return f"ref:{ref}"
            return f"source:{current}"

    def chain(self, sid: str) -> list[str]:
        """Why `sid` keys where it does, one step per line."""
        steps: list[str] = []
        seen: set[str] = set()
        current = sid
        while current not in seen:
            seen.add(current)
            origin = record(self.by_id.get(current) or {})
            if origin is None:
                break
            because = str(origin.get("because") or "").strip()
            why = f" ({because})" if because else ""
            nxt = str(origin.get("republishes") or "").strip()
            if nxt:
                steps.append(f"{current} republishes {nxt}{why}")
                if nxt not in self.by_id:
                    break
                current = nxt
                continue
            ref = str(origin.get("ref") or "").strip()
            owner = self.owner.get(canonical(ref))
            if owner and owner not in seen:
                steps.append(f"{current} comes from {ref}, which {owner} holds{why}")
                current = owner
                continue
            steps.append(f"{current} comes from {ref}{why}")
            break
        return steps


def display(key: str) -> str:
    return key.split(":", 1)[1] if ":" in key else key


def collapsed(keys: Keys, ids: list[str]) -> list[dict]:
    """Groups of `ids` that share one origin, in first-seen order — each
    `{origin, sources, why}` — for every group of two or more."""
    groups: dict[str, list[str]] = {}
    for sid in dict.fromkeys(ids):
        groups.setdefault(keys.key(sid), []).append(sid)
    out = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        why: list[str] = []
        for sid in members:
            why.extend(step for step in keys.chain(sid) if step not in why)
        out.append({"origin": display(key), "sources": members, "why": why})
    return out


def _id_key(sid: str) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", sid)
    return (0, m.group(1), int(m.group(2))) if m else (1, sid, 0)


def set_origin(
    root: Path,
    source_id: str,
    republishes: str | None = None,
    ref: str | None = None,
    because: str | None = None,
    clear: bool = False,
) -> pages.Page:
    """Record (or clear) where a source's content comes from; returns the page.

    Refuses an unknown or non-source id, a source naming itself, and a chain
    that would close a cycle — a cycle would make every source in it its own
    origin. `because` is required either way: an origin is a judgment, and
    the next reader needs what it rested on.
    """
    from . import sources as sources_mod

    root = util.require_notebook_root(root)
    republishes = (republishes or "").strip() or None
    ref = (ref or "").strip() or None
    because = (because or "").strip()
    if clear and (republishes or ref):
        raise SystemExit("choose either an origin (--republishes/--ref) or --clear")
    if not clear and not (republishes or ref):
        raise SystemExit(
            "name the origin: --republishes <source id> for a source this notebook holds, "
            "--ref <url or identifier> for one it does not (or both)"
        )
    if not because:
        raise SystemExit(
            "an origin needs --because: say what shows this source carries another's "
            "content (same wire byline and text, a quoted figure with its citation …)"
        )
    if ref and _SOURCE_ID_RE.match(ref):
        raise SystemExit(f"--ref {ref} looks like a source id; use --republishes {ref}")
    by_id = {p.id: p for p in sources_mod.source_pages(root) if p.id}
    page = by_id.get(source_id)
    if page is None:
        known = ", ".join(sorted(by_id, key=_id_key)) or "none yet"
        raise SystemExit(
            f"unknown source id '{source_id}' in references/ (have: {known}) — "
            "run `flip add-source` first"
        )
    previous = record(page.fm)
    if clear:
        if previous is None:
            raise SystemExit(f"{source_id} records no origin; nothing to clear")
        page.fm.pop("origin", None)
    else:
        if republishes:
            if republishes == source_id:
                raise SystemExit(f"{source_id} cannot republish itself")
            if republishes not in by_id:
                hint = ("" if _SOURCE_ID_RE.match(republishes) else
                        "; for an origin the notebook does not hold, use --ref")
                raise SystemExit(
                    f"unknown source id '{republishes}' for --republishes (have: "
                    f"{', '.join(sorted(by_id, key=_id_key)) or 'none'}){hint}"
                )
            seen: set[str] = set()
            current: str | None = republishes
            while current and current not in seen:
                if current == source_id:
                    raise SystemExit(
                        f"{source_id} republishing {republishes} would close a cycle "
                        f"({republishes} already traces its content back to {source_id})"
                    )
                seen.add(current)
                nxt = record(by_id[current].fm) if current in by_id else None
                current = str((nxt or {}).get("republishes") or "").strip() or None
        value: dict = {}
        if republishes:
            value["republishes"] = republishes
        if ref:
            value["ref"] = ref
        value["because"] = because
        value["by"] = util.detect_actor()
        value["at"] = util.utc_now()
        page.fm["origin"] = value
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    from . import views

    views.regenerate(root, changed=("references",))
    events.emit(root, "source.origin", source_id, republishes=republishes, ref=ref,
                because=because, cleared=True if clear else None)
    return page


__all__ = ["Keys", "canonical", "collapsed", "display", "record", "set_origin"]
