"""Passage pins on any held source (SPEC §5.7, §9).

A claim that rests on a source rests, in practice, on a few of its words. A
transcript has been able to say which words since excerpts were added: a pin
records a line range and a digest of the held text, and a claim cites
`T1§label`. This module is that mechanism for every source with held text — a
captured web page's extraction, a PDF's extracted text, a local document — so
a reader of the notebook alone can re-run "does the source say this?" against
the exact passage, and flip can say whether the passage it vouched for is
still the passage on disk.

**What "the held text" is, and why the pin says so.** A source can have two
readable copies: the raw capture (`sources/raw/…`, immutable) and the text
derivative (`sources/text/<id>.txt`, produced by an extractor and logged in
`derived/_derivations.jsonl`). They are different evidence. The raw bytes are
the document; the derivative is a machine's reading of it, and extraction can
drop content — a table column, a footnote, a minus sign. So every pin records
`held: raw | text`, the SHA-256 of the copy it was pinned against, and — on a
derivative — the extraction that produced it (tool, version, method, when,
and the digest of the raw input). A pin on the derivative is a pin on a
derivative, and the record says so rather than letting it pass as the
document's own words.

**What is stored, and what is derived.** A pin stores a locator (a 1-indexed
inclusive line range; a quote pin also stores the exact character span), the
SHA-256 of the pinned text, the SHA-256 of the held copy, the word count, and
who pinned it when. The pinned text itself is never stored as an authored
value: it is re-read from the held copy every time and checked against the
digest, so a pin a writer could hand-edit cannot exist. The generated
`## Excerpts` section on the source page is a view of the same re-read.

**Labels are stable**, because claims cite them. Re-pinning a label is refused
unless `relocate` is asked for and the new location holds exactly the same
words (same digest) — the one legitimate case, a re-extraction that moved the
passage. Unpinning is refused while any claim cites the label.

Transcript excerpts (`flip transcript excerpt`, SPEC §8) are pins in this same
list. Their records predate this module and carry no `held` key; a record
without one is a raw pin, which is exactly what a transcript excerpt is. They
are read, verified, rendered and checked here unchanged.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from . import events, manifest, pages, util
from . import sources as sources_mod

# flip owns this section of a source page and regenerates it wholly; the prose
# above it round-trips untouched (SPEC §6.6).
EXCERPTS_HEADING = "## Excerpts"

# Which copy a pin reads. `raw` is the capture as held; `text` is the logged
# text derivative of it.
HELD_COPIES = ("raw", "text")

MAX_LINES = 400

# Words of context shown either side of a near miss.
_MISS_CONTEXT_WORDS = 8

_ANCHOR_STRIP = re.compile(r"[^a-z0-9-]+")


def anchor_for(label: str) -> str:
    """The in-page anchor a claim's `resource` points at for a pinned passage."""
    return _ANCHOR_STRIP.sub("-", str(label).lower()).strip("-")


def records(fm: dict) -> list[dict]:
    """The pins on a source page (`excerpts:`), in the order they were made."""
    return [e for e in pages.as_list(fm.get("excerpts")) if isinstance(e, dict)]


def is_transcript(fm: dict) -> bool:
    return str(fm.get("medium") or "") == "conversation"


def pin_command(source_id: str, fm: dict | None, label: str = "<label>") -> str:
    """The command that pins a passage on this source, for refusal messages."""
    if fm is not None and is_transcript(fm):
        return f"flip transcript excerpt {source_id} --label {label} --lines A-B"
    return f'flip source passage pin {source_id} --label {label} --quote "…"'


def find_source(root: Path, source_id: str) -> pages.Page:
    """The references/ page carrying `source_id`, or an actionable refusal."""
    found = [p for p in pages.iter_pages(root, "references") if p.id]
    page = next((p for p in found if p.id == source_id), None)
    if page is not None:
        return page
    known = ", ".join(p.id for p in found) or "none captured yet"
    raise SystemExit(
        f"unknown source id '{source_id}' in references/ (have: {known}); capture it "
        "with `flip add-source` first"
    )


def find_pin(root: Path, source_id: str, label: str) -> dict | None:
    """One pin record on any source, or None. Read-only and tolerant: used by
    citation checks and doctor, which must cope with a label that is absent."""
    page = next(
        (p for p in pages.iter_pages(root, "references") if p.id == source_id), None
    )
    if page is None:
        return None
    return next((e for e in records(page.fm) if str(e.get("label")) == label), None)


# --- the held copy ---------------------------------------------------------------


@dataclass
class Held:
    """One readable copy of a source: which, where, its text and its digest."""

    kind: str  # "raw" | "text"
    path: Path
    text: str
    sha256: str
    extraction: dict | None = None


def _decode(data: bytes) -> str:
    # No newline translation: a quote pin's character span is an offset into
    # exactly this string, so it must not depend on the platform reading it.
    return data.decode("utf-8", errors="replace")


def _raw_path(root: Path, page: pages.Page) -> Path | None:
    local = str(page.fm.get("local") or "")
    if local:
        path = root / local
        return path if path.is_file() else None
    try:
        return sources_mod.primary_raw(root, page.id)
    except SystemExit:
        return None


def _text_path(root: Path, source_id: str) -> Path:
    return root / "sources" / "text" / f"{source_id}.txt"


def _extraction_for(root: Path, source_id: str, digest: str) -> dict | None:
    """The derivation row that produced the derivative with this digest, as
    the summary a pin carries — or None when no logged run produced it."""
    found = None
    for row in util.read_jsonl(root / sources_mod.DERIVATIONS):
        if str(row.get("source_id") or "") != source_id:
            continue
        if str(row.get("kind") or "") != "text":
            continue
        outputs = [o for o in row.get("outputs") or [] if isinstance(o, dict)]
        if any(o.get("sha256") == digest for o in outputs):
            found = row
    if found is None:
        return None
    summary: dict = {"tool": found.get("tool")}
    for key in ("tool_version", "method", "via"):
        if found.get(key):
            summary[key] = found[key]
    summary["at"] = found.get("ts")
    inputs = [i for i in found.get("inputs") or [] if isinstance(i, dict)]
    if inputs and inputs[0].get("sha256"):
        summary["from_sha256"] = inputs[0]["sha256"]
    return summary


def _readable_raw(path: Path) -> str | None:
    """The raw capture as text when it is text, else None."""
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return None
    if path.name == "record.json" and b'"flip_record"' in data:
        return None
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return _decode(data)


def held_copy(root: Path, page: pages.Page, held: str | None = None) -> Held:
    """The copy a new pin will read, chosen explicitly or by the default rule.

    Default: the logged text derivative when one exists, otherwise the raw
    capture when it is plain text. A transcript always reads its raw capture —
    the conversation is already text, and that is what its excerpts have
    always been pinned against.
    """
    sid = page.id
    if held is not None and held not in HELD_COPIES:
        raise SystemExit(f"invalid --held '{held}' (one of: {', '.join(HELD_COPIES)})")
    text_path = _text_path(root, sid)
    if held is None:
        held = "raw" if is_transcript(page.fm) or not text_path.is_file() else "text"
    if held == "text":
        if not text_path.is_file():
            raise SystemExit(
                f"{sid} has no text derivative (sources/text/{sid}.txt); derive one with "
                f"`flip extract {sid}`, or pin against the raw capture with --held raw "
                "if it is plain text"
            )
        data = text_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        extraction = _extraction_for(root, sid, digest)
        if extraction is None:
            raise SystemExit(
                f"sources/text/{sid}.txt matches no row in "
                f"{sources_mod.DERIVATIONS.as_posix()}, so flip cannot say what produced "
                "it — a pin on it would vouch for text of unknown origin. Re-extract with "
                f"`flip extract {sid}` (add --force to replace a hand edit, with a --note), "
                "or pin against the raw capture with --held raw"
            )
        return Held("text", text_path, _decode(data), digest, extraction)
    raw = _raw_path(root, page)
    if raw is None:
        raise SystemExit(
            f"{sid} has no readable raw capture "
            f"({page.fm.get('local') or 'no `local` recorded'}); custody is missing, so "
            "no passage can be pinned against it — re-capture the source"
        )
    text = _readable_raw(raw)
    if text is None:
        hint = (
            f"pin against its text derivative instead (`flip extract {sid}`, then pin "
            "with --held text)"
            if not text_path.is_file()
            else "pin against its text derivative with --held text"
        )
        raise SystemExit(
            f"{sid}'s raw capture ({raw.relative_to(root).as_posix()}) is not plain "
            f"text, so there are no lines in it to pin; {hint}"
        )
    return Held("raw", raw, text, hashlib.sha256(raw.read_bytes()).hexdigest())


def _held_for_record(root: Path, page: pages.Page, record: dict) -> tuple[Path | None, str]:
    """(path of the copy this record was pinned against, kind)."""
    kind = str(record.get("held") or "raw")
    if kind == "text":
        path = _text_path(root, page.id)
        return (path if path.is_file() else None), kind
    return _raw_path(root, page), kind


# --- locating a passage ----------------------------------------------------------


def _line_starts(text: str) -> list[int]:
    """Character offset of each line's start, by the splitlines rule."""
    starts, at = [], 0
    for line in text.splitlines(keepends=True):
        starts.append(at)
        at += len(line)
    return starts or [0]


def _line_of(starts: list[int], offset: int) -> int:
    """1-indexed line holding character `offset`."""
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _lines_text(text: str, start: int, end: int, source_id: str) -> str:
    lines = text.splitlines()
    total = len(lines)
    if start < 1 or end < start:
        raise SystemExit(
            f"invalid line range {start}-{end}: start must be >= 1 and end >= start"
        )
    if start > total:
        raise SystemExit(
            f"line range {start}-{end} starts past the end of {source_id} "
            f"({total} lines) — nothing to pin"
        )
    if end > total:
        raise SystemExit(
            f"line range {start}-{end} runs past the end of {source_id} "
            f"({total} lines); pin a range that exists"
        )
    if end - start + 1 > MAX_LINES:
        raise SystemExit(
            f"range {start}-{end} is {end - start + 1} lines; a passage over {MAX_LINES} "
            f"lines is the document, not a passage — cite {source_id} itself, or pin the "
            "part that carries the point"
        )
    return "\n".join(lines[start - 1 : end])


def _ws_pattern(words: list[str], flags: int = 0) -> re.Pattern:
    return re.compile(r"\s+".join(re.escape(w) for w in words), flags)


def _matches(held: str, quote: str) -> tuple[list[tuple[int, int]], str]:
    """Every occurrence of `quote` in `held` as (start, end) spans, and how it
    matched: `exact`, or `whitespace` when only a match that treats every run
    of whitespace as one gap succeeds (a quote copied across the line breaks
    of an extraction). Overlapping occurrences are all reported."""
    spans: list[tuple[int, int]] = []
    at = held.find(quote)
    while at != -1:
        spans.append((at, at + len(quote)))
        at = held.find(quote, at + 1)
    if spans:
        return spans, "exact"
    words = quote.split()
    if not words:
        return [], "exact"
    pattern = _ws_pattern(words)
    at = 0
    while True:
        m = pattern.search(held, at)
        if m is None:
            break
        spans.append((m.start(), m.end()))
        at = m.start() + 1
    return spans, "whitespace"


def _longest(words: list[str], held: str, prefix: bool) -> tuple[int, re.Match | None]:
    """The most words from the start (or end) of the quote that occur in the
    held text, and where. Occurrence is monotone in the count, so bisect."""
    lo, hi, best = 0, len(words), None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        part = words[:mid] if prefix else words[len(words) - mid :]
        m = _ws_pattern(part).search(held)
        if m:
            lo, best = mid, m
        else:
            hi = mid - 1
    return lo, best


def _clip(words: list[str]) -> str:
    return " ".join(words[:_MISS_CONTEXT_WORDS]) + (" …" if len(words) > _MISS_CONTEXT_WORDS else "")


def _nearest_miss(held: Held, quote: str, source_id: str) -> str:
    """One sentence saying how close the held text comes to the quote."""
    words = quote.split()
    starts = _line_starts(held.text)
    folded = _ws_pattern(words, re.IGNORECASE).search(held.text) if words else None
    if folded:
        line = _line_of(starts, folded.start())
        return (
            f"the quote occurs with different capitalisation at line {line}: "
            f"\"{held.text[folded.start():folded.end()]}\" — quote it exactly as held"
        )
    head, head_at = _longest(words, held.text, prefix=True)
    tail, tail_at = _longest(words, held.text, prefix=False)
    if not head and not tail:
        return (
            f"no run of the quote's words occurs in it — not even its first word "
            f"\"{words[0] if words else ''}\" or its last"
        )
    if head >= tail and head_at is not None:
        line = _line_of(starts, head_at.start())
        after = held.text[head_at.end():].split()
        return (
            f"the first {head} of the quote's {len(words)} words occur at line {line}; "
            f"there the held text goes on \"{_clip(after) or '(end of text)'}\" where the "
            f"quote goes on \"{_clip(words[head:])}\""
        )
    assert tail_at is not None
    line = _line_of(starts, tail_at.start())
    before = held.text[: tail_at.start()].split()[-_MISS_CONTEXT_WORDS:]
    return (
        f"the last {tail} of the quote's {len(words)} words occur at line {line}; "
        f"before them the held text has \"… {' '.join(before)}\" where the quote has "
        f"\"… {' '.join(words[: len(words) - tail][-_MISS_CONTEXT_WORDS:])}\""
    )


def _where(held: Held, spans: list[tuple[int, int]]) -> str:
    starts = _line_starts(held.text)
    shown = ", ".join(str(_line_of(starts, s)) for s, _ in spans[:6])
    return shown + (" …" if len(spans) > 6 else "")


def _locate_quote(
    held: Held,
    quote: str,
    source_id: str,
    occurrence: int | None,
    context: str | None,
) -> tuple[int, int, str]:
    """(start, end, how) of the one occurrence of `quote` the caller means."""
    copy = "text derivative" if held.kind == "text" else "raw capture"
    base = 0
    region = held.text
    if context:
        ctx_spans, _ = _matches(held.text, context)
        if not ctx_spans:
            raise SystemExit(
                f"--context does not occur in {source_id}'s {copy}: "
                f"{_nearest_miss(held, context, source_id)}"
            )
        if len(ctx_spans) > 1:
            raise SystemExit(
                f"--context occurs {len(ctx_spans)} times in {source_id}'s {copy} (lines "
                f"{_where(held, ctx_spans)}); give a longer context that occurs once"
            )
        base, end = ctx_spans[0]
        region = held.text[base:end]
    spans, how = _matches(region, quote)
    spans = [(s + base, e + base) for s, e in spans]
    if not spans:
        if context:
            raise SystemExit(
                f"the quote does not occur inside the --context passage of {source_id}; "
                "the context must contain the quote"
            )
        why = _nearest_miss(held, quote, source_id)
        lossy = (
            " This is the text derivative, and extraction can drop or reorder content: "
            "check the raw capture (--held raw, if it is text) or re-extract"
            if held.kind == "text" else ""
        )
        raise SystemExit(
            f"the quote does not occur in {source_id}'s {copy} — a pin must be words the "
            f"held copy actually contains. Nearest miss: {why}.{lossy}"
        )
    if occurrence is not None:
        if occurrence < 1 or occurrence > len(spans):
            raise SystemExit(
                f"--occurrence {occurrence} is out of range: the quote occurs "
                f"{len(spans)} time(s){' inside the context' if context else ''}"
            )
        start, end = spans[occurrence - 1]
        return start, end, how
    if len(spans) > 1:
        raise SystemExit(
            f"the quote occurs {len(spans)} times in {source_id}'s {copy} (lines "
            f"{_where(held, spans)}); say which one — --occurrence N (1-{len(spans)}, in "
            "reading order), or --context with surrounding text that occurs once"
        )
    start, end = spans[0]
    return start, end, how


# --- reading a pin back ----------------------------------------------------------


@dataclass
class Reading:
    """A pin re-read from its held copy."""

    state: str  # "intact" | "drifted" | "unbacked" | "invalid"
    text: str | None
    held_current: bool | None
    detail: str = ""


def _span(record: dict) -> tuple[int, int] | None:
    span = record.get("span")
    if isinstance(span, list) and len(span) == 2 and all(type(n) is int for n in span):
        return span[0], span[1]
    return None


def _lines(record: dict) -> tuple[int, int] | None:
    span = record.get("lines")
    if isinstance(span, list) and len(span) == 2 and all(type(n) is int for n in span):
        return span[0], span[1]
    return None


def read_record(root: Path, page: pages.Page, record: dict) -> Reading:
    """Re-read a pin from its held copy and check it against its digest.

    Never raises on a bad pin: the state says what is wrong, so doctor, the
    snapshot and the page renderer can all report it.
    """
    path, _kind = _held_for_record(root, page, record)
    if path is None:
        return Reading("unbacked", None, None, "the held copy is gone")
    data = path.read_bytes()
    current = hashlib.sha256(data).hexdigest()
    recorded = record.get("held_sha256")
    held_current = None if not recorded else recorded == current
    text = _decode(data)
    span = _span(record)
    if span is not None:
        start, end = span
        if start < 0 or end < start or end > len(text):
            return Reading("drifted", None, held_current, "the span runs past the held copy")
        quoted = text[start:end]
    else:
        lines = _lines(record)
        if lines is None:
            return Reading("invalid", None, held_current, "the pin has no valid line range")
        all_lines = text.splitlines()
        if lines[0] < 1 or lines[1] < lines[0] or lines[1] > len(all_lines):
            return Reading("drifted", None, held_current,
                           "the line range runs past the held copy")
        quoted = "\n".join(all_lines[lines[0] - 1 : lines[1]])
    if hashlib.sha256(quoted.encode("utf-8")).hexdigest() != str(record.get("sha256")):
        return Reading("drifted", None, held_current,
                       "the text at the pinned location no longer hashes to the pin")
    return Reading("intact", quoted, held_current)


def describe(source_id: str, record: dict, reading: Reading | None = None) -> dict:
    """A pin as the read surfaces show it: the record plus its ref (and, when
    re-read, its state and text)."""
    out = {"ref": util.format_excerpt_ref(source_id, str(record.get("label"))), **record}
    out["held"] = str(record.get("held") or "raw")
    if reading is not None:
        out["state"] = reading.state
        out["held_current"] = reading.held_current
        out["text"] = reading.text
    return out


def read_pin(root: Path, source_id: str, label: str) -> dict:
    """A pinned passage, verified: refuses unless the held copy still carries
    exactly the pinned words. Returns the text, the reference, the lines (and
    span), the digest, and which copy it was read from."""
    page = find_source(root, source_id)
    record = next((e for e in records(page.fm) if str(e.get("label")) == label), None)
    if record is None:
        known = ", ".join(str(e.get("label")) for e in records(page.fm)) or "none pinned"
        raise SystemExit(f"{source_id} has no pinned passage '{label}' (pinned: {known})")
    path, _ = _held_for_record(root, page, record)
    if path is not None and str(record.get("held") or "raw") == "raw":
        if not path.resolve().is_relative_to((root / "sources" / "raw").resolve()):
            raise SystemExit(f"{source_id} capture is outside notebook custody")
    reading = read_record(root, page, record)
    if reading.state != "intact":
        raise SystemExit(
            f"{util.format_excerpt_ref(source_id, label)} cannot be read: {reading.detail}. "
            + _repair(source_id, page.fm, record, reading)
        )
    out = {
        "ref": util.format_excerpt_ref(source_id, label),
        "source": source_id,
        "label": label,
        "held": str(record.get("held") or "raw"),
        "lines": list(_lines(record) or []),
    }
    if _span(record) is not None:
        out["span"] = list(_span(record) or [])
    out["sha256"] = record.get("sha256")
    out["held_sha256"] = record.get("held_sha256")
    out["held_current"] = reading.held_current
    if record.get("extraction"):
        out["extraction"] = record["extraction"]
    out["text"] = reading.text
    return out


def _repair(source_id: str, fm: dict, record: dict, reading: Reading) -> str:
    label = str(record.get("label"))
    if reading.state == "unbacked":
        if str(record.get("held") or "raw") == "text":
            return (f"The text derivative it was pinned on is gone; re-extract with "
                    f"`flip extract {source_id}`, then re-anchor the same words with "
                    f"`flip source passage pin {source_id} --label {label} --quote \"…\" "
                    "--relocate`")
        return "Custody is missing; restore the raw capture or unpin."
    if str(record.get("held") or "raw") == "text":
        return (
            "The text derivative has changed since the pin (re-extracted?). If the same "
            f"words are still in it, re-anchor them: `flip source passage pin {source_id} "
            f"--label {label} --quote \"…\" --relocate`; if they are gone, the extraction "
            "lost them — read the raw capture"
        )
    if is_transcript(fm):
        return "Raw captures are immutable, so the pin record was hand-edited; re-pin it."
    return ("Raw captures are immutable, so the pin record was hand-edited; re-anchor it "
            f"with `flip source passage pin {source_id} --label {label} … --relocate`.")


# --- writing pins ----------------------------------------------------------------


def _validate_label(label: str) -> str:
    label = str(label or "").strip()
    if not util.EXCERPT_LABEL_RE.match(label):
        raise SystemExit(
            f"invalid passage label '{label}': lowercase letters, digits and hyphens, "
            "starting with a letter or digit (it doubles as the page anchor)"
        )
    return label


def pin(
    root: Path,
    source_id: str,
    label: str,
    *,
    quote: str | None = None,
    lines: tuple[int, int] | None = None,
    held: str | None = None,
    occurrence: int | None = None,
    context: str | None = None,
    relocate: bool = False,
    note: str | None = None,
) -> dict:
    """Pin a passage of any held source under `label`; returns the record.

    Exactly one of `quote` (words the held copy must contain) or `lines` (a
    1-indexed inclusive range) locates the passage. The pinned text is read
    out of the held copy and hashed — never taken from the caller — so a
    stored pin is always the words it says it is.
    """
    root = util.require_notebook_root(root)
    label = _validate_label(label)
    if (quote is None) == (lines is None):
        raise SystemExit("locate the passage with exactly one of --quote or --lines")
    if quote is not None and not quote.strip():
        raise SystemExit("empty --quote; give the words the passage is made of")
    if (occurrence is not None or context) and quote is None:
        raise SystemExit("--occurrence and --context disambiguate a --quote; a line range "
                         "is already one place")
    page = find_source(root, source_id)
    existing = records(page.fm)
    old = next((e for e in existing if str(e.get("label")) == label), None)
    if old is not None and not relocate:
        raise SystemExit(
            f"{source_id} already pins '{label}'; labels are stable because claims cite "
            f"them ({util.format_excerpt_ref(source_id, label)}) — pick another label; "
            "pass --relocate to re-anchor the same words after a re-extraction; or drop "
            "the old pin with `flip source passage unpin` if nothing cites it"
        )
    if relocate and old is None:
        raise SystemExit(f"--relocate needs an existing pin; {source_id} pins no '{label}'")
    if not existing and not is_transcript(page.fm) and EXCERPTS_HEADING in page.body:
        raise SystemExit(
            f"{page.path.name} already has a hand-written '{EXCERPTS_HEADING}' section; "
            "flip regenerates that section from the pins, so rename the heading first"
        )
    copy = held_copy(root, page, held)
    if quote is not None:
        start, end, how = _locate_quote(copy, quote, source_id, occurrence, context)
        starts = _line_starts(copy.text)
        text = copy.text[start:end]
        first = _line_of(starts, start)
        last = _line_of(starts, max(start, end - 1))
        if last - first + 1 > MAX_LINES:
            raise SystemExit(
                f"the quote spans {last - first + 1} lines; a passage over {MAX_LINES} "
                f"lines is the document, not a passage — cite {source_id} itself"
            )
        locator: dict = {"lines": [first, last], "span": [start, end]}
    else:
        assert lines is not None
        text = _lines_text(copy.text, lines[0], lines[1], source_id)
        locator = {"lines": [lines[0], lines[1]]}
        how = "exact"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if relocate:
        assert old is not None
        if digest != str(old.get("sha256")):
            raise SystemExit(
                f"--relocate keeps a label only for the same words: the passage found "
                f"hashes {digest[:12]}, the pin '{label}' hashes "
                f"{str(old.get('sha256'))[:12]}. Claims citing "
                f"{util.format_excerpt_ref(source_id, label)} rest on the old words; pin "
                "the new ones under a new label"
            )
    record: dict = {"label": label, "held": copy.kind, **locator, "sha256": digest,
                    "held_sha256": copy.sha256}
    if copy.extraction:
        record["extraction"] = copy.extraction
    record["words"] = len(text.split())
    if how == "whitespace":
        record["match"] = "whitespace"
    if note:
        record["note"] = str(note)
    elif relocate and old is not None and old.get("note"):
        record["note"] = old["note"]
    if relocate and old is not None:
        record["by"] = old.get("by")
        record["at"] = old.get("at")
        record["relocated"] = {"by": util.detect_actor(), "at": util.utc_now(),
                               "from_held_sha256": old.get("held_sha256")}
        record = {k: v for k, v in record.items() if v is not None}
        page.fm["excerpts"] = [record if e is old else e for e in existing]
    else:
        record["by"] = util.detect_actor()
        record["at"] = util.utc_now()
        page.fm["excerpts"] = existing + [record]
    write_source_page(root, page)
    events.emit(root, "source.pin", source_id, label=label, held=copy.kind,
                lines=record["lines"], sha256=digest, relocated=True if relocate else None,
                note=note)
    return record


def unpin(root: Path, source_id: str, label: str, op: str = "source.unpin") -> dict:
    """Drop a pin. Refuses while any claim still cites it — the ref would keep
    resolving to the source and quietly widen from one passage to the whole."""
    root = util.require_notebook_root(root)
    page = find_source(root, source_id)
    existing = records(page.fm)
    record = next((e for e in existing if str(e.get("label")) == label), None)
    if record is None:
        known = ", ".join(str(e.get("label")) for e in existing) or "none pinned"
        raise SystemExit(f"{source_id} does not pin '{label}' (pinned: {known})")
    ref = util.format_excerpt_ref(source_id, label)
    citing = claims_citing(root, ref)
    if citing:
        whole = "whole transcript" if is_transcript(page.fm) else "whole source"
        raise SystemExit(
            f"{', '.join(citing)} still cite{'s' if len(citing) == 1 else ''} {ref}; "
            f"unpin would leave them resting on the {whole} instead of the "
            "passage — repoint or drop those citations first"
        )
    page.fm["excerpts"] = [e for e in existing if str(e.get("label")) != label]
    write_source_page(root, page)
    events.emit(root, op, source_id, label=label)
    return record


def claims_citing(root: Path, ref: str) -> list[str]:
    """Claim ids whose `sources:` carry this exact passage ref, in id order."""
    from . import claims as claims_mod

    return [
        p.id
        for p in pages.iter_pages(root, "claims")
        if p.id and ref in claims_mod.source_refs(p.fm)
    ]


# --- the generated section -------------------------------------------------------


def _meta(record: dict) -> str:
    span = _lines(record) or (1, 1)
    meta = f"Lines {span[0]}–{span[1]} · sha256 `{str(record.get('sha256'))[:12]}`"
    if record.get("held") == "text":
        ex = record.get("extraction") if isinstance(record.get("extraction"), dict) else {}
        how = ", ".join(str(ex[k]) for k in ("tool", "method") if ex.get(k))
        meta += f" · pinned on the text derivative{f' ({how})' if how else ''}"
    elif record.get("held") == "raw":
        meta += " · pinned on the raw capture"
    if record.get("note"):
        meta += f" · {record['note']}"
    return meta


def render(root: Path, page: pages.Page, quotes: dict[str, str] | None = None) -> str:
    """The generated `## Excerpts` section: one anchored subsection per pin.

    The label is the whole heading text so `references/<slug>.md#<label>`
    resolves in every renderer that slugifies headings — the same anchor a
    claim's `resource` points at. A pin that can no longer be read renders as
    a line saying so rather than stopping the write.
    """
    found = records(page.fm)
    if not found:
        return ""
    quotes = quotes or {}
    out = [EXCERPTS_HEADING, ""]
    for record in found:
        label = str(record.get("label"))
        text = quotes.get(label)
        if text is None:
            reading = read_record(root, page, record)
            text = reading.text
        out.append(f"### {label}")
        out.append("")
        out.append(_meta(record))
        out.append("")
        if text is None:
            out.append(f"> (this passage cannot be read from its held copy: "
                       f"{reading.detail} — see `flip doctor`)")
        else:
            # A line pin is its lines joined with "\n", so split it back the same
            # way (splitlines would drop a trailing blank line of the range).
            shown = text.splitlines() if _span(record) is not None else text.split("\n")
            out.extend(f"> {line}" if line.strip() else ">" for line in shown)
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def write_source_page(
    root: Path, page: pages.Page, quotes: dict[str, str] | None = None
) -> pages.Page:
    """Persist a source page, regenerating only the `## Excerpts` section.

    Everything above it — the capture note, whatever a person wrote about the
    source — round-trips untouched (SPEC §6.6).
    """
    head = page.body.split(EXCERPTS_HEADING, 1)[0].rstrip("\n")
    section = render(root, page, quotes)
    body = (head + "\n\n" if head else "") + section if section else (head + "\n" if head else "")
    pages.write_page(page.path, page.fm, body)
    manifest.touch_updated(root)
    from . import views

    # Source pages live in references/; pin and unpin touch nothing else.
    views.regenerate(root, changed=("references",))
    return pages.Page(path=page.path, fm=page.fm, body=body)


__all__ = [
    "EXCERPTS_HEADING", "HELD_COPIES", "MAX_LINES", "Held", "Reading",
    "anchor_for", "claims_citing", "describe", "find_pin", "find_source", "held_copy",
    "is_transcript", "pin", "pin_command", "read_pin", "read_record", "records",
    "render", "unpin", "write_source_page",
]
