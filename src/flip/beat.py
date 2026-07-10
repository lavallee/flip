"""Beats — the grouping layer above notebooks (SPEC §14).

A beat is a standing mission that outlives any single notebook: an OKF
bundle with the same grammar as a notebook but a different manifest key
(`flip_beat:` instead of `flip:` in the root index.md frontmatter), so the
two root kinds never shadow each other — notebook commands inside a child
notebook resolve to the notebook, `flip beat …` commands walk up past it to
the beat.

The pieces:

- **Manifest** — root index.md frontmatter (`Beat` dataclass, load/save with
  the same extras-preservation discipline as `manifest.Manifest`); beat.md is
  the prose working memory (`type: Beat`).
- **Threads** — the beat's unit of attention, one entity page per thread
  under threads/ (`type: Thread`, ids TH# via pages.allocate_id, never
  reused). Triage is computed, not stored: `rank_threads` weights the five
  0–1 scores at read time and never mutates pages.
- **Coverage** — coverage.jsonl is the append-only memory of outcomes:
  graduations, drops, and anything coverage-relevant. Negative coverage
  (drops with reasons) prevents re-scouting dead angles.
- **Graduation** — the beat's core act: a thread becomes a child notebook
  under notebooks/<slug>/, linked both ways (thread `notebook:` key, child
  manifest `links.beat`).

Every mutator ends with touch_updated + regenerate, mirroring the notebook
layer's mutation tail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import pages, scaffold, util, views
from .manifest import STATUSES, load_manifest, require_valid_slug, save_manifest
from .util import ROOT_FILE, today

FLIP_BEAT_VERSION = "0.1"
BEAT_MD = "beat.md"
THREADS_DIR = "threads"
NOTEBOOKS_DIR = "notebooks"
COVERAGE_JSONL = "coverage.jsonl"
LOG_JSONL = Path("log") / "log.jsonl"
LOG_MD = "log.md"

THREAD_KINDS = ("arc", "vein")
THREAD_STATUSES = ("open", "active", "dormant", "done", "dropped")
# Statuses that rank: the threads still competing for attention (SPEC §14).
RANKED_STATUSES = ("open", "active")

# Default triage weights (SPEC §14), overridable in the beat manifest.
DEFAULT_WEIGHTS = {
    "payoff": 0.30, "access": 0.25, "urgency": 0.20,
    "connection": 0.15, "uniqueness": 0.10,
}
DEFAULT_SCORE = 0.5  # a missing score reads as 0.5; ranking never mutates pages

# Beat manifest keys flip owns, in canonical frontmatter order.
KNOWN_KEYS = ("okf_version", "flip_beat", "slug", "mission", "status",
              "created", "updated", "weights")

RECENT_LOG_COUNT = 8

_ID_NUM = re.compile(r"(\d+)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# beat.md prompt stubs — prompts, not a form (same spirit as profile sections).
_BEAT_MD_SECTIONS = (
    ("Mission", "What is this beat FOR? One paragraph a stranger could act on."),
    ("Standing sources", "Where does material for this beat keep coming from — "
                         "agendas, dockets, feeds, people? List them so the next "
                         "pass starts warm."),
    ("What counts as covered", "When is a thread here done — published, decided, "
                               "or deliberately dropped? Name the bar."),
)


# --- root discovery -------------------------------------------------------------


def is_beat_root(directory: Path) -> bool:
    """A flip beat root is a directory whose index.md opens with a frontmatter
    block declaring a `flip_beat:` version (SPEC §14). Same cheap textual
    sniff as util.is_notebook_root — and deliberately disjoint from it:
    `flip_beat:` never matches a `flip:` prefix test, so a beat root is
    invisible to notebook root discovery and vice versa.
    """
    path = directory / ROOT_FILE
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return False
    if not head.startswith("---\n"):
        return False
    block = head.split("\n---", 1)[0]
    return any(line.startswith("flip_beat:") for line in block.splitlines())


def find_beat_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default cwd) to the nearest beat root. The walk
    does not stop at a notebook root: run from inside a child notebook it
    keeps climbing to the enclosing beat."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if is_beat_root(candidate):
            return candidate
    return None


def require_beat_root(start: Path | None = None) -> Path:
    root = find_beat_root(start)
    if root is None:
        raise SystemExit(
            "not inside a flip beat (no index.md with flip_beat frontmatter found "
            "here or above); run `flip beat new <slug>` to create one"
        )
    return root


# --- beat manifest ----------------------------------------------------------------


@dataclass
class Beat:
    slug: str
    mission: str = ""
    status: str = "active"
    created: str = ""
    updated: str = ""
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    # Unknown frontmatter keys, preserved verbatim across load/save.
    extras: dict = field(default_factory=dict)


def load_beat(root: Path) -> Beat:
    path = root / ROOT_FILE
    if not path.is_file():
        raise SystemExit(
            f"no {ROOT_FILE} in {root} — not a flip beat root "
            "(run `flip beat new <slug>` to create one)"
        )
    fm = pages.read_page(path).fm
    if not isinstance(fm.get("slug"), str) or not fm["slug"]:
        raise SystemExit(
            f"{path}: frontmatter missing required key 'slug' — add e.g. slug: my-beat"
        )
    b = Beat(slug=fm["slug"])
    for key in ("mission", "status", "created", "updated"):
        if key in fm and fm[key] is not None:
            setattr(b, key, str(fm[key]))
    b.extras = {k: v for k, v in fm.items() if k not in KNOWN_KEYS}
    # Same never-drop rule as the notebook manifest: a foreign-typed value for
    # a known key rides along in extras verbatim instead of being discarded.
    weights = fm.get("weights")
    if isinstance(weights, dict):
        b.weights = weights
    elif "weights" in fm and weights is not None:
        b.extras["weights"] = weights
    return b


def beat_frontmatter(b: Beat) -> dict:
    fm: dict = {"okf_version": "0.1", "flip_beat": FLIP_BEAT_VERSION, "slug": b.slug}
    if b.mission:
        fm["mission"] = b.mission
    fm["status"] = b.status
    fm["created"] = b.created or today()
    fm["updated"] = b.updated or today()
    fm["weights"] = dict(b.weights) if b.weights else dict(DEFAULT_WEIGHTS)
    fm.update(b.extras)
    return fm


def save_beat(root: Path, b: Beat, body: str | None = None) -> None:
    """Rewrite the root index.md frontmatter; keep (or set) the body.

    The body is the generated listing owned by regenerate — preserved
    byte-for-byte here unless a new one is passed."""
    require_valid_slug(b.slug)
    if b.status not in STATUSES:
        raise SystemExit(f"invalid status '{b.status}' (one of: {', '.join(STATUSES)})")
    path = root / ROOT_FILE
    if body is None:
        body = pages.read_page(path).body if path.is_file() else f"# {b.slug}\n"
    pages.write_page(path, beat_frontmatter(b), body)


def touch_updated(root: Path) -> None:
    """Refresh the beat manifest's `updated` to today; part of every mutation."""
    b = load_beat(root)
    if b.updated != today():
        b.updated = today()
        save_beat(root, b)


# --- creation -----------------------------------------------------------------------


def _beat_md_body(slug: str, mission: str) -> str:
    parts = [f"# Beat — {slug}\n"]
    for heading, prompt in _BEAT_MD_SECTIONS:
        if heading == "Mission" and mission:
            parts.append(f"\n## {heading}\n\n{mission}\n")
        else:
            parts.append(f"\n## {heading}\n\n> {prompt}\n")
    return "".join(parts)


def create_beat(dest: Path, slug: str, mission: str = "") -> Path:
    """Create a beat at `dest`: index.md + beat.md, nothing else (threads/,
    notebooks/, log/, coverage.jsonl appear lazily with use). All validation
    runs before mkdir, so a bad call creates nothing. Returns `dest`."""
    if (dest / ROOT_FILE).exists():
        raise SystemExit(
            f"{dest} already contains {ROOT_FILE} (a beat or notebook root); "
            "work in it or pick a different directory"
        )
    require_valid_slug(slug)  # before mkdir: a bad slug creates nothing
    mission = " ".join(str(mission or "").split())
    b = Beat(slug=slug, mission=mission, created=today(), updated=today())
    dest.mkdir(parents=True, exist_ok=True)
    save_beat(dest, b)
    pages.write_page(
        dest / BEAT_MD,
        {"type": "Beat", "description": mission},
        _beat_md_body(slug, mission),
    )
    regenerate(dest)
    return dest


# --- threads ---------------------------------------------------------------------


def _id_num(entity_id: str) -> int:
    m = _ID_NUM.search(str(entity_id))
    return int(m.group(1)) if m else 0


def _require_text(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise SystemExit(f"empty {what}; pass a non-empty {what} string")
    return value


def _validate_scores(scores: dict) -> dict:
    """Scores are the five SPEC §14 dimensions, each 0–1; anything else is a
    typo worth stopping for (a silently ignored score never ranks)."""
    out = {}
    for key, value in scores.items():
        if key not in DEFAULT_WEIGHTS:
            raise SystemExit(
                f"unknown score '{key}' (one of: {', '.join(DEFAULT_WEIGHTS)})"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not 0 <= value <= 1:
            raise SystemExit(f"score {key}={value!r} out of range; scores are 0–1")
        out[key] = float(value)
    return out


def parse_score_pairs(pairs: tuple[str, ...] | list[str]) -> dict[str, float]:
    """CLI `--score key=value` pairs → dict (values must parse as numbers;
    key validity and range are checked where the scores land)."""
    out: dict[str, float] = {}
    for pair in pairs:
        key, sep, value = str(pair).partition("=")
        try:
            if not sep or not key.strip():
                raise ValueError
            out[key.strip()] = float(value)
        except ValueError:
            raise SystemExit(
                f"bad --score '{pair}': expected key=value with a number, "
                "e.g. --score payoff=0.8"
            ) from None
    return out


def _find_thread(root: Path, thread_id: str) -> pages.Page:
    page = pages.find_by_id(root, thread_id)
    if page is None or str(page.fm.get("type", "")) != "Thread":
        known = sorted(
            (p.id for p in pages.iter_pages(root, THREADS_DIR) if p.id),
            key=_id_num,
        )
        hint = (
            f"known: {', '.join(known)}"
            if known
            else 'none yet; add one with `flip beat thread add "<title>" --kind arc|vein`'
        )
        raise SystemExit(f"no thread '{thread_id}' in {THREADS_DIR}/ ({hint})")
    return page


def _finish(root: Path) -> None:
    """Common tail of every beat mutation: bump `updated`, refresh the views."""
    touch_updated(root)
    regenerate(root)


def add_thread(
    root: Path,
    title: str,
    kind: str,
    note: str | None = None,
    scores: dict | None = None,
) -> pages.Page:
    """Open a thread: threads/<slug>.md with the next TH#. Returns the Page.

    `kind` is arc (self-initiated investigation) or vein (recurring
    story-type monitored reactively); `scores` carries only the keys actually
    judged — missing dimensions read as 0.5 at rank time, never stored."""
    root = require_beat_root(root)
    title = _require_text(title, "title")
    if kind not in THREAD_KINDS:
        raise SystemExit(f"invalid kind '{kind}' (one of: {', '.join(THREAD_KINDS)})")
    scores = _validate_scores(scores or {})
    thread_id = pages.allocate_id(root, "TH")
    fm: dict = {
        "type": "Thread",
        "id": thread_id,
        "aliases": [thread_id],
        "title": title,
        "kind": kind,
        "status": "open",
    }
    if scores:
        fm["scores"] = scores
    fm["timestamp"] = util.utc_now()
    fm["actor"] = util.detect_actor()
    body = (note or "").strip() or title
    directory = root / THREADS_DIR
    slug = pages.unique_slug(directory, pages.slugify(title, fallback="thread"))
    path = pages.write_page(directory / f"{slug}.md", fm, body + "\n")
    _finish(root)
    return pages.Page(path=path, fm=fm, body=body + "\n")


def _append_note(body: str, note: str) -> str:
    """Append prose under a dated heading — the thread body is its running
    rationale, newest entries at the bottom."""
    base = body.rstrip("\n")
    return (base + "\n\n" if base else "") + f"## {today()}\n\n{note}\n"


def update_thread(
    root: Path,
    thread_id: str,
    status: str | None = None,
    note: str | None = None,
    scores: dict | None = None,
    next_review: str | None = None,
) -> pages.Page:
    """Update a thread page in place (round-trip rule, SPEC §6.6): only the
    keys this function owns change; foreign frontmatter keys and the body
    survive. A note lands in the body under a dated heading; scores merge
    key-by-key into the existing dict. Returns the Page."""
    root = require_beat_root(root)
    if status is None and note is None and not scores and next_review is None:
        raise SystemExit(
            "nothing to update; pass at least one of --status/--note/--score/--next-review"
        )
    if status is not None and status not in THREAD_STATUSES:
        raise SystemExit(
            f"invalid status '{status}' (one of: {', '.join(THREAD_STATUSES)})"
        )
    if status == "dropped":
        raise SystemExit(
            "use `flip beat thread drop <id> --reason …` to drop a thread — "
            "the reason is the record that prevents re-scouting dead angles"
        )
    scores = _validate_scores(scores or {})
    if next_review is not None and not _DATE_RE.match(next_review):
        raise SystemExit(
            f"bad next-review date '{next_review}': expected YYYY-MM-DD, e.g. {today()}"
        )
    page = _find_thread(root, thread_id)
    if status is not None:
        page.fm["status"] = status
    if scores:
        merged = dict(page.fm.get("scores") or {})
        merged.update(scores)
        page.fm["scores"] = merged
    if next_review is not None:
        page.fm["next_review"] = next_review
    body = page.body
    note = (note or "").strip()
    if note:
        body = _append_note(body, note)
    pages.write_page(page.path, page.fm, body)
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


def drop_thread(root: Path, thread_id: str, reason: str) -> pages.Page:
    """Kill a thread, first-class: status → dropped, the reason recorded in
    frontmatter (`dropped_reason`), the body, and the coverage ledger —
    negative coverage prevents re-scouting dead angles (SPEC §14)."""
    root = require_beat_root(root)
    reason = _require_text(reason, "reason")
    page = _find_thread(root, thread_id)
    if page.fm.get("status") == "dropped":
        raise SystemExit(f"thread {thread_id} is already dropped; nothing to do")
    page.fm["status"] = "dropped"
    page.fm["dropped_reason"] = reason
    body = _append_note(page.body, f"Dropped: {reason}")
    pages.write_page(page.path, page.fm, body)
    coverage_event(root, thread=thread_id, note=f"dropped: {reason}")
    _finish(root)
    return pages.Page(path=page.path, fm=page.fm, body=body)


# --- graduation ---------------------------------------------------------------------


def graduate(
    root: Path,
    thread_id: str,
    notebook_slug: str,
    kind: str = "scout",
    title: str = "",
) -> Path:
    """The beat's core act: turn a thread into a child notebook (SPEC §14).

    Scaffolds notebooks/<slug>/ (per the notebook profile `kind`), stamps the
    thread `status: active` + `notebook: <slug>`, links the notebook manifest
    back (`links: {beat: "<beat-slug>#<id>"}`), and appends a coverage event.
    Returns the notebook path."""
    root = require_beat_root(root)
    b = load_beat(root)
    page = _find_thread(root, thread_id)
    status = str(page.fm.get("status", "open"))
    if page.fm.get("notebook"):
        raise SystemExit(
            f"thread {thread_id} already graduated to notebook "
            f"'{page.fm['notebook']}'; open a new thread for a fresh angle"
        )
    if status in ("dropped", "done"):
        raise SystemExit(
            f"thread {thread_id} is {status}; reopen it first "
            f"(`flip beat thread update {thread_id} --status open`)"
        )
    require_valid_slug(notebook_slug)  # before it names a path under notebooks/
    dest = root / NOTEBOOKS_DIR / notebook_slug
    if dest.exists():
        raise SystemExit(
            f"notebook slug '{notebook_slug}' is taken ({dest} exists); pick another"
        )
    # create_notebook validates slug and kind before mkdir, so a bad call
    # leaves the beat untouched.
    scaffold.create_notebook(dest, notebook_slug, kind, title=title)
    m = load_manifest(dest)
    m.links["beat"] = f"{b.slug}#{thread_id}"
    save_manifest(dest, m)
    page.fm["status"] = "active"
    page.fm["notebook"] = notebook_slug
    pages.write_page(page.path, page.fm, page.body)
    coverage_event(
        root, thread=thread_id, notebook=notebook_slug,
        note=f"graduated to {kind} notebook '{notebook_slug}'",
    )
    _finish(root)
    return dest


# --- ranking ---------------------------------------------------------------------


def effective_weights(b: Beat) -> dict[str, float]:
    """Default weights overlaid with the beat manifest's `weights:`; an
    unknown weight key is a typo that would silently skew every ranking."""
    weights = dict(DEFAULT_WEIGHTS)
    for key, value in (b.weights or {}).items():
        if key not in DEFAULT_WEIGHTS:
            raise SystemExit(
                f"unknown weight '{key}' in the beat manifest "
                f"(one of: {', '.join(DEFAULT_WEIGHTS)}); fix index.md `weights:`"
            )
        weights[key] = float(value)
    return weights


def thread_score(page: pages.Page, weights: dict[str, float]) -> float:
    scores = page.fm.get("scores") or {}
    if not isinstance(scores, dict):
        scores = {}
    total = 0.0
    for key, weight in weights.items():
        value = scores.get(key, DEFAULT_SCORE)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            value = DEFAULT_SCORE
        total += weight * float(value)
    return round(total, 4)


def rank_threads(root: Path) -> list[tuple[float, pages.Page]]:
    """Open/active threads by weighted score, best first — triage is computed,
    never stored (SPEC §14). Missing scores read as 0.5; ties break on id, so
    the order is deterministic. Ranking never mutates pages."""
    b = load_beat(root)
    weights = effective_weights(b)
    ranked = [
        (thread_score(p, weights), p)
        for p in pages.iter_pages(root, THREADS_DIR)
        if str(p.fm.get("type", "")) == "Thread"
        and str(p.fm.get("status", "open")) in RANKED_STATUSES
    ]
    ranked.sort(key=lambda pair: (-pair[0], _id_num(pair[1].id)))
    return ranked


# --- ledgers -----------------------------------------------------------------------


def coverage_event(
    root: Path,
    thread: str | None = None,
    notebook: str | None = None,
    note: str = "",
    actor: str | None = None,
) -> dict:
    """Append one event to coverage.jsonl — the beat's cross-notebook memory
    of outcomes (SPEC §14). Pure append; callers own the mutation tail."""
    row: dict = {"ts": util.utc_now()}
    if thread:
        row["thread"] = thread
    if notebook:
        row["notebook"] = notebook
    if note:
        row["note"] = note
    row["actor"] = actor or util.detect_actor()
    util.append_jsonl(root / COVERAGE_JSONL, row)
    return row


def log_event(root: Path, text: str) -> dict:
    """Append one work-log event to the beat's log/log.jsonl; returns the row."""
    root = require_beat_root(root)  # before any write: no stray log/ dirs
    text = _require_text(text, "log text")
    row = {"ts": util.utc_now(), "text": text, "actor": util.detect_actor()}
    util.append_jsonl(root / LOG_JSONL, row)
    _finish(root)
    return row


# --- generated views -----------------------------------------------------------------


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _read_log(root: Path) -> list[dict]:
    try:
        return util.read_jsonl(root / LOG_JSONL)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line") from None


def child_notebooks(root: Path) -> list[dict]:
    """Child notebooks under notebooks/, slug order: {slug, kind, status,
    title, path}. Tolerant — a broken child manifest reads as '?' here;
    the child's own doctor is where that gets reported."""
    directory = root / NOTEBOOKS_DIR
    if not directory.is_dir():
        return []
    out = []
    for child in sorted(p for p in directory.iterdir() if p.is_dir()):
        if not util.is_notebook_root(child):
            continue
        row = {"slug": child.name, "kind": "?", "status": "?", "title": "",
               "path": child.relative_to(root).as_posix()}
        try:
            m = load_manifest(child)
            row.update(slug=m.slug, kind=m.kind, status=m.status, title=m.title)
        except SystemExit:
            pass
        out.append(row)
    return out


def _thread_pages(root: Path) -> list[pages.Page]:
    found, _errors = pages.iter_pages_tolerant(root, THREADS_DIR)
    return [p for p in found if str(p.fm.get("type", "")) == "Thread"]


def regenerate(root: Path) -> None:
    """Rewrite the beat's generated projections after a mutation: log.md
    (newest-first, same renderer as notebooks), threads/index.md, and the
    root index.md *body* — through save_beat, so the manifest frontmatter
    (including keys flip doesn't know) is preserved. Deterministic; canonical
    records (thread pages, JSONL ledgers) are never touched."""
    b = load_beat(root)  # validates the root before writing anything
    try:
        events = util.read_jsonl(root / LOG_JSONL)
    except ValueError:
        events = []  # corrupt ledger: leave log.md as-is
    if events:
        views.write_log_md(root, events)
    _write_threads_index(root, b)
    save_beat(root, b, body=_root_body(root, b, events))


def _write_threads_index(root: Path, b: Beat) -> None:
    directory = root / THREADS_DIR
    if not directory.is_dir():
        return
    threads = _thread_pages(root)
    index = directory / "index.md"
    if not threads:
        if index.is_file() and views.is_generated_index(index):
            index.unlink()
        return
    weights = effective_weights(b)
    lines = ["# Threads", ""]
    for page in threads:
        label = " ".join(str(page.fm.get("title") or page.id or page.slug).split())
        status = str(page.fm.get("status", "open"))
        detail = f"{page.fm.get('kind', '?')} · {status}"
        if status in RANKED_STATUSES:
            detail += f" · score {thread_score(page, weights):.2f}"
        lines.append(f"* [{label}]({page.slug}.md) - {detail}")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _root_body(root: Path, b: Beat, events: list[dict]) -> str:
    """The beat index.md body: heading, mission line, and the OKF directory
    listing. Sections appear once they have content."""
    lines = [f"# {b.slug}"]
    if b.mission:
        lines += ["", b.mission]
    bullets: list[str] = []
    threads = _thread_pages(root)
    if threads:
        live = sum(1 for p in threads if str(p.fm.get("status", "open")) in RANKED_STATUSES)
        bullets.append(
            f"* [Threads](threads/) - {_count(len(threads), 'thread')}, {live} open/active"
        )
    notebooks = child_notebooks(root)
    if notebooks:
        bullets.append(f"* [Notebooks](notebooks/) - {_count(len(notebooks), 'child notebook')}")
        for nb in notebooks:
            label = nb["title"] or nb["slug"]
            bullets.append(f"  * [{label}]({nb['path']}/) - {nb['kind']} · {nb['status']}")
    if (root / LOG_MD).is_file():
        detail = f"{_count(len(events), 'logged event')}, newest first" if events else "work log"
        bullets.append(f"* [Update Log]({LOG_MD}) - {detail}")
    if bullets:
        lines.append("")
        lines += bullets
    return "\n".join(lines) + "\n"


# --- the beat view --------------------------------------------------------------------


def _dormant_due(root: Path) -> list[pages.Page]:
    """Dormant threads whose next_review date has arrived (string compare is
    safe: dates are ISO YYYY-MM-DD)."""
    out = []
    for page in _thread_pages(root):
        if str(page.fm.get("status", "")) != "dormant":
            continue
        review = str(page.fm.get("next_review", ""))
        if review and review <= today():
            out.append(page)
    return out


def _thread_row(page: pages.Page, score: float | None = None) -> dict:
    row = {
        "id": page.id,
        "title": str(page.fm.get("title", "")),
        "kind": str(page.fm.get("kind", "?")),
        "status": str(page.fm.get("status", "open")),
    }
    if score is not None:
        row["score"] = score
    for key in ("notebook", "next_review"):
        if page.fm.get(key):
            row[key] = str(page.fm[key])
    return row


def beat_show(root: Path, as_data: bool = False) -> str | dict:
    """The beat's resume-here screen: mission, ranked triage, dormant threads
    due for review, the notebook roster, and the recent log. Computed, never
    stored (SPEC §14)."""
    b = load_beat(root)
    ranked = rank_threads(root)
    due = _dormant_due(root)
    notebooks = child_notebooks(root)
    recent = _read_log(root)[-RECENT_LOG_COUNT:]
    if as_data:
        return {
            "slug": b.slug,
            "mission": b.mission,
            "status": b.status,
            "updated": b.updated,
            "weights": effective_weights(b),
            "threads": [_thread_row(p, score) for score, p in ranked],
            "dormant_due": [_thread_row(p) for p in due],
            "notebooks": notebooks,
            "recent_log": recent,
        }
    lines = [" · ".join([b.slug, "beat", b.status, b.updated])]
    if b.mission:
        lines.append(f"mission: {b.mission}")
    if ranked:
        lines += ["", "THREADS (ranked)"]
        for score, page in ranked:
            parts = [f"{score:.2f}", page.id, str(page.fm.get("kind", "?")),
                     str(page.fm.get("status", "open")),
                     " ".join(str(page.fm.get("title", "")).split())]
            if page.fm.get("notebook"):
                parts.append(f"→ {page.fm['notebook']}")
            lines.append("  " + " · ".join(parts))
    if due:
        lines += ["", "DORMANT PAST REVIEW"]
        for page in due:
            lines.append(
                f"  {page.id} · next_review {page.fm.get('next_review')} · "
                + " ".join(str(page.fm.get("title", "")).split())
            )
    if notebooks:
        lines += ["", "NOTEBOOKS"]
        for nb in notebooks:
            label = f" · {nb['title']}" if nb["title"] else ""
            lines.append(f"  {nb['slug']} · {nb['kind']} · {nb['status']}{label}")
    if recent:
        lines += ["", "RECENT LOG"]
        lines += [
            f"  {e.get('ts', '')} · {e.get('actor', '')} · "
            + " ".join(str(e.get("text", "")).split())
            for e in recent
        ]
    return "\n".join(lines)
