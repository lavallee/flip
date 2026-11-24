"""Transcripts — conversations kept verbatim, and citable by the passage (SPEC §8, §9).

SPEC §8 has always said a session page carries a "pointer to the raw
transcript when kept". This is the layer that keeps it, and it exists because
of what a notebook otherwise loses: claims and graded sources are the
*residue* of thinking, not the thinking. A conversation is where a position
actually got built — where the objection landed, where the framing turned over
— and a notebook that keeps only the conclusions cannot later show anyone
(including its own author) why the conclusion is the shape it is.

So a transcript is captured as a **source**, not as an attachment:

- the bytes land in `sources/raw/` under normal custody, immutable and hashed,
  with a provenance row whose method is `human-in-loop` — a person was in the
  conversation and handed flip the file (SPEC §5.1)
- it gets a `T#` id, so a claim can cite it like any other evidence
- **excerpts** pin a named passage: `flip transcript excerpt T1 --lines 88-104
  --label relevance-null` records the exact lines, hashes the quoted text, and
  copies it onto the page. A claim then cites `T1§relevance-null` and the
  exchange that produced it travels with it.

The excerpt quote is *derived from the raw file every time*, never authored:
an excerpt that could be hand-edited would be a quotation flip vouched for and
could not check. Raw captures are immutable (SPEC §5.1), so the line range
stays meaningful for the life of the notebook, and the stored sha256 is what
proves the copy on the page is the passage that was pinned.

Grading is untouched by all of this. A transcript is `self-reported` evidence
about the world and grades C at best; what it is genuinely primary evidence
*of* is the conversation itself, which is exactly what it gets cited for.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import events, pages, passages, util
from . import sources as sources_mod

# flip owns this section of a transcript page and regenerates it wholly; the
# prose above it round-trips untouched (SPEC §6.6). The section is the shared
# passage core's, since every held source can now carry pins (SPEC §5.7).
EXCERPTS_HEADING = passages.EXCERPTS_HEADING


def _transcript_pages(root: Path) -> list[pages.Page]:
    return [
        p
        for p in pages.iter_pages(root, "references")
        if str(p.fm.get("medium") or "") == "conversation"
    ]


def _find_transcript(root: Path, source_id: str) -> pages.Page:
    """The transcript page carrying `source_id`, or an actionable refusal."""
    page = next((p for p in _transcript_pages(root) if p.id == source_id), None)
    if page is not None:
        return page
    # A plain source id is a different mistake from an unknown one, and the
    # fix is different too — say which happened rather than "not found".
    other = next(
        (p for p in pages.iter_pages(root, "references") if p.id == source_id), None
    )
    if other is not None:
        raise SystemExit(
            f"{source_id} is a source but not a transcript (no `medium: conversation`); "
            "excerpts pin passages in a captured conversation — capture one with "
            "`flip session transcript`"
        )
    known = ", ".join(p.id for p in _transcript_pages(root) if p.id) or "none captured yet"
    raise SystemExit(
        f"unknown transcript id '{source_id}' (transcripts: {known}); "
        "capture one with `flip session transcript`"
    )


def _raw_path(root: Path, page: pages.Page) -> Path:
    local = str(page.fm.get("local") or "")
    path = root / local if local else None
    if not local or path is None or not path.is_file():
        raise SystemExit(
            f"{page.id} has no readable capture at "
            f"{local or '(no `local` recorded)'}; custody is missing, so no passage "
            "can be pinned against it — re-capture the transcript"
        )
    return path


def capture_transcript(
    root: Path,
    file: str | Path,
    title: str | None = None,
    participants: list[str] | None = None,
    model: str | None = None,
    note: str | None = None,
) -> pages.Page:
    """Capture a conversation verbatim as a citable source; returns its page.

    Custody is the ordinary copy path (immutable bytes, sha256, one provenance
    row) with the method recorded as `human-in-loop`: the bytes came from a
    person saving a conversation they were in, which `copy` alone would
    understate. The page carries `medium: conversation` — the marker every
    transcript-aware command routes on — plus the participants and model when
    given, and opens ungraded like any other capture.
    """
    root = util.require_notebook_root(root)
    src = Path(str(file)).expanduser()
    if not src.is_file():
        raise SystemExit(
            f"no transcript file at '{file}'; write the conversation to a file first "
            "(markdown or text), then capture it"
        )
    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        raise SystemExit(f"transcript file '{file}' is empty; nothing to keep")

    extra: dict = {"medium": "conversation"}
    if participants:
        extra["participants"] = [str(p) for p in participants]
    if model:
        extra["model"] = str(model)
    extra["lines"] = len(lines)
    extra["excerpts"] = []

    page = sources_mod.add_source(
        root,
        str(src),
        kind="conversation",
        note=note,
        strategy="human-in-loop",
        extra_fm=extra,
    )
    if title:
        page = sources_mod.retitle_source(root, page.fm["id"], title)
    return page


def add_excerpt(
    root: Path,
    source_id: str,
    label: str,
    start: int,
    end: int,
    note: str | None = None,
) -> dict:
    """Pin lines `start`-`end` of a transcript under `label`; returns the record.

    The quote is read out of the immutable capture, hashed, and written onto
    the page — never taken from the caller, so a stored excerpt is always the
    passage it says it is. Re-pinning an existing label is refused: a claim
    already citing `T1§label` would silently come to rest on different words.

    The record keeps the shape transcript excerpts have always had
    (`{label, lines, sha256, words, note?}`); reading, rendering and doctor's
    checks are the shared passage core's (`flip.passages`), which reads a
    record with no `held` key as a pin on the raw capture — what a transcript
    excerpt is.
    """
    root = util.require_notebook_root(root)
    label = str(label or "").strip()
    if not util.EXCERPT_LABEL_RE.match(label):
        raise SystemExit(
            f"invalid excerpt label '{label}': lowercase letters, digits and hyphens, "
            "starting with a letter or digit (it doubles as the page anchor)"
        )
    page = _find_transcript(root, source_id)
    existing = passages.records(page.fm)
    if any(str(e.get("label")) == label for e in existing):
        raise SystemExit(
            f"{source_id} already pins '{label}'; labels are stable because claims cite "
            f"them ({util.format_excerpt_ref(source_id, label)}) — pick another label, "
            "or drop the old one with `flip transcript unpin` if nothing cites it"
        )
    raw = _raw_path(root, page)
    text = passages._lines_text(
        raw.read_text(encoding="utf-8", errors="replace"), start, end, source_id
    )
    record: dict = {
        "label": label,
        "lines": [start, end],
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "words": len(text.split()),
    }
    if note:
        record["note"] = str(note)
    page.fm["excerpts"] = existing + [record]
    passages.write_source_page(root, page, quotes={label: text})
    events.emit(root, "transcript.excerpt", source_id, label=label, lines=[start, end],
                note=note)
    return record


def remove_excerpt(root: Path, source_id: str, label: str) -> dict:
    """Drop a pinned excerpt. Refuses while any claim still cites it — the ref
    would keep resolving to the source and quietly widen from one exchange to
    the whole conversation."""
    root = util.require_notebook_root(root)
    _find_transcript(root, source_id)
    return passages.unpin(root, source_id, label, op="transcript.unpin")


def excerpts(root: Path, source_id: str) -> list[dict]:
    """Every passage pinned on a transcript, in the order they were pinned."""
    return passages.records(_find_transcript(root, source_id).fm)


def find_excerpt(root: Path, source_id: str, label: str) -> dict | None:
    """One pinned excerpt record, or None. Read-only; used by resolution and
    doctor, both of which must tolerate a label that doesn't exist. Since
    passage pins exist on every source, this answers for any source."""
    return passages.find_pin(root, source_id, label)


def read_passage(root: Path, source_id: str, label: str) -> dict:
    """Return the cited lines only when they still match the recorded pin."""
    page = _find_transcript(root, source_id)
    record = next((e for e in passages.records(page.fm) if e.get("label") == label), None)
    if not record:
        raise SystemExit(f"{source_id} has no pinned passage '{label}'")
    raw = _raw_path(root, page).resolve()
    if not raw.is_relative_to((root / "sources/raw").resolve()):
        raise SystemExit(f"{source_id} capture is outside notebook custody")
    reading = passages.read_record(root, page, record)
    if reading.state == "invalid":
        raise SystemExit(f"{source_id} has an invalid line range for '{label}'")
    if reading.state != "intact":
        raise SystemExit(f"{source_id} passage '{label}' no longer matches the pinned digest")
    return {"ref": util.format_excerpt_ref(source_id, label),
            "lines": list(passages._lines(record) or []),
            "sha256": record.get("sha256"), "text": reading.text}


def anchor_for(label: str) -> str:
    """The in-page anchor a claim's `resource` points at for an excerpt."""
    return passages.anchor_for(label)
