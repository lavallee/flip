"""Computed views and generated at-rest projections (SPEC §10).

Views are computed, never canonical. Two surfaces live here:

- **`flip show`** — hot_view/claims_view/stale_view assemble windowed
  projections (open questions, claims needing work, dated sources, recent
  log, latest session) from the entity pages and JSONL ledgers. Each returns
  rendered plain text, or a plain dict when `as_data=True` (for `--json`).
- **`regenerate(root)`** — rewrites the at-rest equivalents after every
  mutation: `log.md` (newest-first view of log/log.jsonl), each entity
  directory's `index.md` listing, and the root `index.md` *body* (the OKF
  directory listing; the manifest frontmatter is preserved untouched).
  Deterministic: the same notebook state always produces the same bytes.

Reads are tolerant (pages.iter_pages_tolerant): one corrupt page never takes
down a view — `flip doctor` is where corruption gets reported.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from . import pages
from .manifest import Manifest, load_manifest, save_manifest
from .profiles import Profile, load_profile
from .util import age_months, read_jsonl

# Claim status enum (SPEC §7), in display order.
CLAIM_STATUS_ORDER = (
    "asserted",
    "verified",
    "needs-2nd",
    "unconfirmed",
    "false-positive",
    "retracted",
    "superseded",
)
# Statuses that mean "this claim still needs verification work".
NEEDS_WORK_STATUSES = ("asserted", "needs-2nd")
RECENT_LOG_COUNT = 8
TRUNCATE_WIDTH = 80

LOG_JSONL = Path("log") / "log.jsonl"
LOG_MD = "log.md"

# Entity directory → (listing title, root-listing description builder input).
_DIR_TITLES = {
    "references": "References",
    "claims": "Claims",
    "decisions": "Decisions",
    "questions": "Questions",
    "sessions": "Sessions",
}

_ID_NUM = re.compile(r"(\d+)$")


def _trunc(text: object, width: int = TRUNCATE_WIDTH) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= width:
        return s
    return s[: width - 1].rstrip() + "…"


def _one_line(text: object) -> str:
    return " ".join(str(text or "").split())


def _id_num(entity_id: str) -> int:
    m = _ID_NUM.search(str(entity_id))
    return int(m.group(1)) if m else 0


def _read(root: Path, rel: Path | str) -> list[dict]:
    """Read an optional ledger; a corrupt line becomes an actionable exit."""
    try:
        return read_jsonl(root / rel)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line (flip doctor pinpoints it)") from None


def _pages(root: Path, dirname: str) -> list[pages.Page]:
    """Entity pages, filename order; corrupt pages skipped (doctor flags them)."""
    out, _errors = pages.iter_pages_tolerant(root, dirname)
    return out


def _profile_or_default(m: Manifest, root: Path) -> Profile:
    """Views tolerate an unresolvable kind; doctor is where that gets flagged."""
    try:
        return load_profile(m.kind, root)
    except SystemExit:
        return Profile(id=m.kind)


def _question_text(page: pages.Page) -> str:
    """The question text: the body up to any ## Answer, else the description."""
    body = page.body.lstrip("\n")
    if body.startswith("## Answer"):
        body = ""
    body = body.split("\n## Answer", 1)[0].strip()
    return body or str(page.fm.get("description", ""))


def _open_questions(root: Path) -> list[dict]:
    """Question pages whose status is not "answered" (missing status = open)."""
    out = []
    for page in _pages(root, "questions"):
        if str(page.fm.get("type", "")) != "Question":
            continue
        if str(page.fm.get("status", "open")) == "answered":
            continue
        out.append(
            {"id": page.id, "text": _question_text(page), "ts": str(page.fm.get("timestamp", ""))}
        )
    out.sort(key=lambda q: _id_num(q["id"]))
    return out


def _claim_rows(root: Path) -> list[dict]:
    """Claim pages as plain dicts (fm + slug + root-relative path), id order."""
    rows = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in _pages(root, "claims")
        if str(p.fm.get("type", "")) == "Claim"
    ]
    rows.sort(key=lambda r: _id_num(str(r.get("id", ""))))
    return rows


def _claims_needing_work(root: Path) -> list[dict]:
    claims = [c for c in _claim_rows(root) if c.get("status") in NEEDS_WORK_STATUSES]
    claims.sort(key=lambda c: not c.get("load_bearing", False))  # load-bearing first, stable
    return claims


def _source_rows(root: Path) -> list[dict]:
    rows = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in _pages(root, "references")
        if str(p.fm.get("type", "")) == "Source"
    ]
    rows.sort(key=lambda r: _id_num(str(r.get("id", ""))))
    return rows


def _latest_session(root: Path) -> str | None:
    sessions = root / "sessions"
    if not sessions.is_dir():
        return None
    files = [
        p
        for p in sessions.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and p.name not in pages.RESERVED
        and not p.name.startswith((".", "_"))
    ]
    if not files:
        return None
    newest = max(files, key=lambda p: p.name)  # names are UTC-stamped (SPEC §3)
    return newest.relative_to(root).as_posix()


def _stale_sources(rows: list[dict], freshness_months: int) -> list[dict]:
    """Sources judged dated, or whose page date is at/past the profile threshold."""
    today = datetime.now(timezone.utc).date()
    out = []
    for row in rows:
        if row.get("freshness") == "dated":
            out.append(row)
            continue
        age = age_months(row.get("date"), today)
        if age is not None and age >= freshness_months:
            out.append(row)
    return out


def _claim_line(c: dict, with_status: bool = False) -> str:
    parts = [str(c.get("id", "?"))]
    if with_status:
        parts.append(str(c.get("status", "")))
    if c.get("load_bearing"):
        parts.append("[load-bearing]")
    parts.append(_trunc(c.get("description", "")))
    sources = pages.as_list(c.get("sources"))
    parts.append("sources: " + (", ".join(str(s) for s in sources) if sources else "none"))
    parts.append(f"corroboration: {c.get('independent_corroboration', 0)}")
    return " · ".join(parts)


def hot_view(root: Path, as_data: bool = False) -> str | dict:
    """Current focus: open questions, claims needing work, recent activity."""
    m = load_manifest(root)
    profile = _profile_or_default(m, root)
    questions = _open_questions(root)
    claims = _claims_needing_work(root)
    recent = _read(root, LOG_JSONL)[-RECENT_LOG_COUNT:]
    session = _latest_session(root)
    dated = _stale_sources(_source_rows(root), profile.freshness_months)
    if as_data:
        return {
            "slug": m.slug,
            "kind": m.kind,
            "status": m.status,
            "updated": m.updated,
            "open_questions": questions,
            "claims_needing_work": claims,
            "recent_log": recent,
            "latest_session": session,
            "dated_sources": len(dated),
        }
    lines = [" · ".join([m.slug, m.kind, m.status, m.updated])]
    if questions:
        lines += ["", "OPEN QUESTIONS"]
        lines += [f"  {q['id']} · {_trunc(q['text'])}" for q in questions]
    if claims:
        lines += ["", "CLAIMS NEEDING WORK"]
        lines += [f"  {_claim_line(c, with_status=True)}" for c in claims]
    if recent:
        lines += ["", "RECENT LOG"]
        lines += [
            f"  {e.get('ts', '')} · {e.get('actor', '')} · {_trunc(e.get('text', ''))}"
            for e in recent
        ]
    if session:
        lines += ["", "LATEST SESSION", f"  {session}"]
    if dated:
        lines += ["", f"DATED SOURCES: {len(dated)}"]
    return "\n".join(lines)


def claims_view(root: Path, as_data: bool = False) -> str | dict:
    """All claims grouped by status, enum order first, unknown statuses last."""
    load_manifest(root)  # fail early with an actionable error if this isn't a notebook
    claims = _claim_rows(root)
    groups: dict[str, list[dict]] = {}
    for c in claims:
        groups.setdefault(str(c.get("status", "unknown")), []).append(c)
    order = [s for s in CLAIM_STATUS_ORDER if s in groups]
    order += [s for s in groups if s not in CLAIM_STATUS_ORDER]
    if as_data:
        return {"total": len(claims), "by_status": {s: groups[s] for s in order}}
    if not claims:
        return "no claims recorded (claims/ is absent or empty)"
    lines: list[str] = []
    for status in order:
        lines.append(status.upper())
        lines += [f"  {_claim_line(c)}" for c in groups[status]]
        lines.append("")
    return "\n".join(lines).rstrip()


def stale_view(root: Path, as_data: bool = False) -> str | dict:
    """What has gone cold: dated sources, open questions, stuck claims."""
    m = load_manifest(root)
    profile = _profile_or_default(m, root)
    dated = _stale_sources(_source_rows(root), profile.freshness_months)
    questions = _open_questions(root)
    stuck = _claims_needing_work(root)
    if as_data:
        return {"dated_sources": dated, "open_questions": questions, "stuck_claims": stuck}
    lines: list[str] = []
    if dated:
        lines.append("DATED SOURCES")
        for row in dated:
            lines.append(
                f"  {row.get('id', '?')} · {_trunc(row.get('title', ''))}"
                f" · date: {row.get('date') or 'unknown'}"
                f" · freshness: {row.get('freshness', '?')}"
            )
        lines.append("")
    if questions:
        lines.append("OPEN QUESTIONS")
        lines += [f"  {q['id']} · {_trunc(q['text'])}" for q in questions]
        lines.append("")
    if stuck:
        lines.append("STUCK CLAIMS")
        lines += [f"  {_claim_line(c, with_status=True)}" for c in stuck]
        lines.append("")
    if not lines:
        return "nothing stale"
    return "\n".join(lines).rstrip()


# --- generated at-rest views (SPEC §10) --------------------------------------


def regenerate(root: Path) -> None:
    """Rewrite the generated projections after a mutation (SPEC §6.5, §10).

    Writes, in order: log.md at the root (skipped while there are no log
    events, so a fresh notebook stays two files), an index.md listing inside
    each entity directory that exists, and the root index.md *body* — through
    save_manifest, so the manifest frontmatter (including keys flip doesn't
    know) is preserved byte-for-key. Hand-edits to any of these don't survive;
    canonical records (entity pages, JSONL ledgers) are never touched.
    """
    m = load_manifest(root)  # validates the root before writing anything
    try:
        events = read_jsonl(root / LOG_JSONL)
    except ValueError:
        events = []  # corrupt ledger: leave log.md as-is; doctor pinpoints the line
    if events:
        write_log_md(root, events)
    for dirname in pages.ENTITY_DIRS:
        _write_dir_index(root, dirname)
    save_manifest(root, m, body=_root_body(root, m, events))


def write_log_md(root: Path, events: list[dict]) -> None:
    """log.md: the OKF-reserved, newest-first view of log/log.jsonl (SPEC §8).

    Shared with the beat layer (beat.regenerate) so beat and notebook logs
    render identically."""
    by_day: dict[str, list[dict]] = {}
    for ev in events:
        day = str(ev.get("ts", ""))[:10] or "undated"
        by_day.setdefault(day, []).append(ev)
    lines = ["# Update Log"]
    for day in sorted(by_day, reverse=True):
        lines += ["", f"## {day}", ""]
        for ev in reversed(by_day[day]):  # newest first within the day
            actor = _one_line(ev.get("actor", ""))
            suffix = f" _({actor})_" if actor else ""
            lines.append(f"* **Update**: {_one_line(ev.get('text', ''))}{suffix}")
    (root / LOG_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_dir_index(root: Path, dirname: str) -> None:
    """<dirname>/index.md: one listing line per entity page, filename order.

    Empty structure is worse than absent structure (SPEC §1.10): when the
    directory holds no entity pages, a previously generated listing (its
    frontmatter-free shape marks it as flip's) is deleted rather than left
    stale — authored files, even misplaced ones, are never deleted.
    """
    directory = root / dirname
    if not directory.is_dir():
        return
    entries = _pages(root, dirname)
    index = directory / "index.md"
    if not entries:
        if index.is_file() and is_generated_index(index):
            index.unlink()
        return
    lines = [f"# {_DIR_TITLES.get(dirname, dirname.title())}", ""]
    for page in entries:
        label = _one_line(page.fm.get("title") or page.id or page.slug)
        line = f"* [{label}]({page.slug}.md)"
        desc = _one_line(page.fm.get("description", ""))
        if desc:
            line += f" - {desc}"
        lines.append(line)
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_generated_index(index: Path) -> bool:
    """A frontmatter-free index.md is flip's generated listing; anything
    carrying frontmatter (or unreadable) is treated as authored and kept.
    Shared with the beat layer (threads/index.md follows the same rule)."""
    try:
        fm, _body = pages.parse(index.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    return not fm


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _root_body(root: Path, m: Manifest, events: list[dict]) -> str:
    """The root index.md body: title heading + OKF directory listing (SPEC §4).

    Sections appear once they have content — an empty entity directory gets
    no bullet, matching _write_dir_index dropping its listing.
    """
    lines = [f"# {m.title or m.slug}"]
    bullets: list[str] = []
    counts = {d: n for d in pages.ENTITY_DIRS if (n := len(_pages(root, d)))}
    if "references" in counts:
        bullets.append(
            f"* [References](references/) - {_count(counts['references'], 'captured source')} "
            "with custody and grading"
        )
    if "claims" in counts:
        bullets.append(
            f"* [Claims](claims/) - {_count(counts['claims'], 'claim')} with status and citations"
        )
    if "decisions" in counts:
        bullets.append(
            f"* [Decisions](decisions/) - {_count(counts['decisions'], 'recorded decision')}"
        )
    if "questions" in counts:
        open_n = len(_open_questions(root))
        bullets.append(
            f"* [Questions](questions/) - {_count(counts['questions'], 'question')}, {open_n} open"
        )
    if "sessions" in counts:
        bullets.append(f"* [Sessions](sessions/) - {_count(counts['sessions'], 'work session')}")
    if (root / LOG_MD).is_file():
        detail = f"{_count(len(events), 'logged event')}, newest first" if events else "work log"
        bullets.append(f"* [Update Log]({LOG_MD}) - {detail}")
    if bullets:
        lines.append("")
        lines += bullets
    return "\n".join(lines) + "\n"
