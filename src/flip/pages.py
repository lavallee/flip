"""Entity pages — the canonical record layer of a v0.4 notebook (SPEC §3, §6).

One markdown file with YAML frontmatter per source/claim/decision/question/
session. Pages are OKF concepts; flip is a strict producer and a tolerant
consumer:

- **Reading** uses PyYAML `safe_load`, so frontmatter written by humans,
  Obsidian, or other agents parses faithfully. Dates/datetimes are normalized
  back to ISO strings so page metadata stays JSON-serializable everywhere.
- **Writing** re-emits every key that was present — keys flip doesn't know
  survive round-trips (OKF's consumer rule, applied to writers, SPEC §6.6) —
  with insertion order preserved and a deterministic YAML style.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .util import next_id, read_jsonl

FM_DELIM = "---"
RESERVED = {"index.md", "log.md"}

# Entity directories and the id-prefix → directory routing (SPEC §9).
ENTITY_DIRS = ("references", "claims", "decisions", "questions", "sessions")
# Directories scanned when resolving ids: the entity dirs plus analysis/,
# where H# hypothesis pages live (SPEC §9 — any frontmatter scan resolves
# ids), plus threads/, where a beat root keeps its TH# thread pages (SPEC
# §14; a notebook has no threads/ dir, so the extra scan is free there).
# Analysis pages are concept pages and need no id, but when one carries
# an id it must resolve and count toward uniqueness like any other.
SCAN_DIRS = (*ENTITY_DIRS, "analysis", "threads")
PREFIX_DIR = {
    "P": "references", "A": "references", "F": "references",
    "T": "references", "S": "references",
    "C": "claims", "D": "decisions", "Q": "questions",
    "H": "analysis", "TH": "threads",
}

# Notebook-local, append-only id reservation file (one id per line): every
# successful allocation is recorded here, so deleting an entity page never
# frees its id (SPEC §9 — ids are never reused). Dot-dirs stay out of every
# export/bag payload, so reservations never ship.
IDS_FILE = Path(".flip") / "ids"


@dataclass
class Page:
    path: Path
    fm: dict
    body: str

    @property
    def id(self) -> str:
        return str(self.fm.get("id", ""))

    @property
    def slug(self) -> str:
        return self.path.stem


def _normalize(value):
    """YAML parses bare dates as date objects; flip keeps ISO strings."""
    if isinstance(value, _dt.datetime):
        if value.tzinfo is not None:
            # Convert to UTC before relabeling Z — a foreign-tz timestamp
            # (2026-07-09T14:30:00+02:00) names an instant, not a wall clock.
            return value.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return value.isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def parse(text: str) -> tuple[dict, str]:
    """Split a page into (frontmatter dict, body). Tolerant: a page with no
    frontmatter block parses as ({}, whole text); malformed YAML raises
    ValueError with a line-anchored message (doctor turns this into a finding).

    parse and write_page are inverses: write_page inserts one blank separator
    line between frontmatter and body, and parse strips it again, so a
    read-modify-write never accretes leading newlines (SPEC §12: never fight
    over whitespace). Deliberate extra blank lines a human left still survive.
    """
    if not text.startswith(FM_DELIM + "\n") and text.strip() != FM_DELIM:
        return {}, text
    end = text.find("\n" + FM_DELIM, len(FM_DELIM))
    if end == -1:
        return {}, text  # unterminated block: treat the whole file as body
    raw = text[len(FM_DELIM) + 1 : end]
    body = text[end + len(FM_DELIM) + 1 :]
    if body.startswith("\n"):
        body = body[1:]  # the newline closing the delimiter line
    if body.startswith("\n"):
        body = body[1:]  # write_page's one-blank-line separator (its inverse)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML frontmatter: {e}") from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return {str(k): _normalize(v) for k, v in data.items()}, body


def read_page(path: Path) -> Page:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"no page at {path}") from None
    try:
        fm, body = parse(text)
    except ValueError as e:
        raise SystemExit(f"{path}: {e}") from None
    return Page(path=path, fm=fm, body=body)


def dump_frontmatter(fm: dict) -> str:
    text = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False, width=88
    )
    return f"{FM_DELIM}\n{text}{FM_DELIM}\n"


def write_page(path: Path, fm: dict, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = body if body.endswith("\n") or body == "" else body + "\n"
    path.write_text(dump_frontmatter(fm) + "\n" + body, encoding="utf-8")
    return path


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "item", max_words: int = 8) -> str:
    words = _SLUG_STRIP.sub(" ", str(text).lower()).split()
    slug = "-".join(words[:max_words])[:64].strip("-")
    return slug or fallback


def unique_slug(directory: Path, slug: str) -> str:
    """First free filename for `slug` in `directory` (slug, slug-2, slug-3…)."""
    candidate, n = slug, 1
    while (directory / f"{candidate}.md").exists() or f"{candidate}.md" in RESERVED:
        n += 1
        candidate = f"{slug}-{n}"
    return candidate


def iter_pages(root: Path, dirname: str) -> list[Page]:
    """Entity pages in one directory, reserved and `_`-prefixed files skipped,
    sorted by filename. Unparseable pages raise via read_page (SystemExit);
    callers that must survive corruption (doctor, views) use iter_pages_tolerant.
    """
    directory = root / dirname
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.md")):
        if path.name in RESERVED or path.name.startswith("_"):
            continue
        out.append(read_page(path))
    return out


def iter_pages_tolerant(root: Path, dirname: str) -> tuple[list[Page], list[tuple[Path, str]]]:
    """Like iter_pages, but collects (path, error) instead of raising."""
    directory = root / dirname
    if not directory.is_dir():
        return [], []
    pages: list[Page] = []
    errors: list[tuple[Path, str]] = []
    for path in sorted(directory.glob("*.md")):
        if path.name in RESERVED or path.name.startswith("_"):
            continue
        try:
            fm, body = parse(path.read_text(encoding="utf-8"))
            pages.append(Page(path=path, fm=fm, body=body))
        except (ValueError, OSError) as e:
            errors.append((path, str(e)))
    return pages, errors


def as_list(value) -> list:
    """Coerce a frontmatter field to a list: None → [], list → copy, scalar →
    [value]. Hand-edited pages legally write `sources: A3` or `authors: Jane
    Doe`; every consumer of a list-typed field goes through here so a scalar
    is one item, never char-split.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def find_by_id(root: Path, entity_id: str) -> Page | None:
    """Resolve a compact id ([A3], [C7], [H1]…) to its page via frontmatter
    scan. Prefix routes to the right directory; falls back to scanning all
    scanned dirs for foreign-authored pages filed unconventionally.
    """
    prefix = entity_id.rstrip("0123456789")
    dirs = [PREFIX_DIR[prefix]] if prefix in PREFIX_DIR else []
    dirs += [d for d in SCAN_DIRS if d not in dirs]
    for dirname in dirs:
        for page in iter_pages(root, dirname):
            if page.id == entity_id:
                return page
    return None


def all_ids(root: Path) -> list[str]:
    """Every entity id ever used: current pages, every id that ever hit the
    provenance ledger, and every id in the .flip/ids reservation file (ids
    are never reused, even after a page is deleted — SPEC §9; provenance and
    the reservation file are append-only, so deleted entities stay reserved).
    """
    ids = [p.id for d in SCAN_DIRS for p in _safe_pages(root, d) if p.id]
    ids += [
        str(ev["source_id"])
        for ev in read_jsonl(root / "sources" / "_provenance.jsonl")
        if ev.get("source_id")
    ]
    ids += reserved_ids(root)
    return ids


def reserved_ids(root: Path) -> list[str]:
    """Ids recorded in the notebook-local reservation file, .flip/ids."""
    try:
        text = (root / IDS_FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def reserve_id(root: Path, entity_id: str) -> None:
    """Append one granted id to .flip/ids (append-only, one id per line)."""
    path = root / IDS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(entity_id + "\n")


def allocate_id(root: Path, prefix: str) -> str:
    """Allocate the next compact id for `prefix` and reserve it in .flip/ids.

    The one allocation path for C#/D#/Q#/source ids: allocation runs over
    all_ids (pages + provenance + reservations) and every granted id is
    recorded, so deleting a page later never frees its id (SPEC §9).
    """
    entity_id = next_id(prefix, all_ids(root))
    reserve_id(root, entity_id)
    return entity_id


def _safe_pages(root: Path, dirname: str) -> list[Page]:
    pages, _errors = iter_pages_tolerant(root, dirname)
    return pages
