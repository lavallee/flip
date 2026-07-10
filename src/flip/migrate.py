"""v0.3 → v0.4 migration: JSONL entity ledgers become entity pages (SPEC §15).

A v0.3 notebook keeps its identity in notebook.toml and its entities in
JSONL ledgers (sources/ledger.jsonl, analysis/claims.jsonl,
log/decisions.jsonl, log/questions.jsonl) plus session files under
log/sessions/. `migrate` converts all of that to the v0.4 shape — manifest
frontmatter in the root index.md, one entity page per source / claim /
decision / question / session — preserving every id, every recorded field,
and the append-only event history (log/log.jsonl, log/passed.jsonl,
sources/_provenance.jsonl, derived/ are left untouched).

Each ledger's pages are written before that ledger is deleted, and
notebook.toml is deleted last, so an interrupted migration resumes cleanly:
re-running converts only what remains — rows whose id already has a page are
skipped (counted as already migrated), never duplicated. Running against a
v0.4 notebook is a refusal, not a no-op, so scripted callers notice.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from . import claims, manifest, pages
from .util import ROOT_FILE, is_notebook_root, read_jsonl, today

NOTEBOOK_TOML = "notebook.toml"

# v0.3 ledger locations, in conversion order (claims cite sources, so
# references/ pages must exist first for citation links).
SOURCES_LEDGER = Path("sources") / "ledger.jsonl"
CLAIMS_LEDGER = Path("analysis") / "claims.jsonl"
DECISIONS_LEDGER = Path("log") / "decisions.jsonl"
QUESTIONS_LEDGER = Path("log") / "questions.jsonl"
SESSIONS_DIR = Path("log") / "sessions"

_DESCRIPTION_LIMIT = 160


def _description(text: str) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= _DESCRIPTION_LIMIT else s[: _DESCRIPTION_LIMIT - 1].rstrip() + "…"


def _read_ledger(root: Path, rel: Path) -> list[dict]:
    try:
        return read_jsonl(root / rel)
    except ValueError as e:
        raise SystemExit(f"{e}; fix that line before migrating") from None


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after migrating —
    they are generated projections (SPEC §10)."""
    from . import views

    views.regenerate(root)


def _existing_page_ids(root: Path) -> set[str]:
    """Ids already carried by entity pages (page existence only — provenance
    ids must NOT count here, or a source's capture event would mask the
    ledger row that still needs its page written)."""
    ids: set[str] = set()
    for dirname in pages.SCAN_DIRS:
        found, _errors = pages.iter_pages_tolerant(root, dirname)
        ids.update(p.id for p in found if p.id)
    return ids


# --- manifest -------------------------------------------------------------


_TOP_STR_KEYS = ("title", "kind", "status", "created", "updated", "host")
_POLICY_KEYS = ("visibility", "renders_public", "source_trail_public", "citation_rule")
_TOP_KNOWN = ("slug", *_TOP_STR_KEYS, "relations", "consumers", "links", "tools", "policy")


def _manifest_from_toml(root: Path, path: Path) -> manifest.Manifest:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{path}: invalid TOML: {e}") from None
    slug = data.get("slug")
    if not isinstance(slug, str) or not slug:
        raise SystemExit(f"{path}: missing required key 'slug'; add e.g. slug = \"my-notebook\"")
    m = manifest.Manifest(slug=slug)
    for key in _TOP_STR_KEYS:
        if data.get(key) is not None:
            # tolerate unquoted TOML dates (tomllib yields date objects)
            setattr(m, key, str(data[key]))
    for key in ("relations", "consumers"):
        if isinstance(data.get(key), list):
            setattr(m, key, data[key])
    for key in ("links", "tools"):
        if isinstance(data.get(key), dict):
            setattr(m, key, data[key])
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    if policy.get("visibility") is not None:
        m.visibility = str(policy["visibility"])
    if policy.get("citation_rule") is not None:
        m.citation_rule = str(policy["citation_rule"])
    for key in ("renders_public", "source_trail_public"):
        if key in policy:
            setattr(m, key, bool(policy[key]))
    m.extras = {k: v for k, v in data.items() if k not in _TOP_KNOWN}
    policy_extras = {k: v for k, v in policy.items() if k not in _POLICY_KEYS}
    if policy_extras:
        m.extras["policy"] = policy_extras  # unknown policy tunables survive
    return m


# --- sources --------------------------------------------------------------

# Ledger fields consumed into the SPEC §5.3 frontmatter slots; anything else
# on a row is preserved verbatim after them (unknown keys survive, SPEC §6.6).
_SOURCE_CONSUMED = (
    "id", "title", "notes", "url", "date", "authors", "publisher",
    "local", "grade", "independence", "freshness", "status",
)


def _write_source_page(root: Path, row: dict) -> pages.Page:
    sid = str(row["id"])
    title = str(row.get("title") or "") or (
        Path(str(row["local"])).name if row.get("local") else sid
    )
    notes = str(row.get("notes") or "")
    fm: dict = {
        "type": "Source",
        "id": sid,
        "aliases": [sid],
        "title": title,
        "description": _description(notes) if notes else f"{row.get('kind', 'captured')} source",
    }
    if row.get("url"):
        fm["resource"] = str(row["url"])  # SPEC §5.3: the canonical URL slot
    for key in ("date", "authors", "publisher", "local"):
        if row.get(key) is not None:
            fm[key] = row[key]
    fm["grade"] = str(row.get("grade") or "?")
    fm["independence"] = str(row.get("independence") or "original")
    fm["freshness"] = str(row.get("freshness") or "fresh")
    fm["status"] = str(row.get("status") or "captured")
    fm.update({k: v for k, v in row.items() if k not in _SOURCE_CONSUMED})
    directory = root / "references"
    slug = pages.unique_slug(directory, pages.slugify(title, fallback=sid.lower()))
    body = f"# {title}\n" + (f"\n{notes}\n" if notes else "")
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    return pages.Page(path=path, fm=fm, body=body)


# --- claims ---------------------------------------------------------------

_CLAIM_CONSUMED = (
    "id", "text", "status", "load_bearing", "sources", "supports",
    "independent_corroboration", "first_asserted", "actor", "notes",
)


def _citations(src_by_id: dict[str, pages.Page], source_ids: list[str]) -> tuple[list[str], list[str]]:
    """(supports, citation lines), deduped, matching claims.add_claim's shape.
    Unresolvable ids are cited as plain text — dangling is legal (SPEC §6.1)."""
    supports: list[str] = []
    lines: list[str] = []
    for n, sid in enumerate(dict.fromkeys(str(s) for s in source_ids), 1):
        page = src_by_id.get(sid)
        if page is None:
            lines.append(f"[{n}] {sid}")
        else:
            supports.append(f"/references/{page.slug}")
            label = str(page.fm.get("title") or sid)
            lines.append(f"[{n}] [{label}](../references/{page.slug}.md)")
    return supports, lines


def _write_claim_page(root: Path, row: dict, src_by_id: dict[str, pages.Page]) -> pages.Page:
    cid = str(row["id"])
    text = str(row.get("text") or "").strip() or cid
    source_ids = [str(s) for s in row.get("sources") or []]
    supports, citation_lines = _citations(src_by_id, source_ids)
    notes = str(row.get("notes") or "")
    fm: dict = {
        "type": "Claim",
        "id": cid,
        "aliases": [cid],
        "description": _description(text),
        "status": str(row.get("status") or "asserted"),
        "load_bearing": bool(row.get("load_bearing")),
        "sources": source_ids,
        "supports": supports,
        # stored for consumers, recomputed here so it tracks the new pages
        "independent_corroboration": claims.corroboration_count(
            [p.fm for p in src_by_id.values()], source_ids
        ),
        "first_asserted": str(row.get("first_asserted") or today()),
    }
    if row.get("actor"):
        fm["actor"] = str(row["actor"])
    if notes:
        fm["notes"] = notes
    fm.update({k: v for k, v in row.items() if k not in _CLAIM_CONSUMED})
    parts = [text]
    if notes:
        parts.append(f"_{notes}_")
    if citation_lines:
        parts.append(claims.CITATIONS_HEADING + "\n" + "\n".join(citation_lines))
    body = "\n\n".join(parts) + "\n"
    directory = root / "claims"
    slug = pages.unique_slug(directory, pages.slugify(text, fallback=cid.lower()))
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    return pages.Page(path=path, fm=fm, body=body)


# --- decisions ------------------------------------------------------------

_DECISION_CONSUMED = ("id", "ts", "question", "decision", "why", "alternatives_rejected", "actor")


def _write_decision_page(root: Path, row: dict) -> pages.Page:
    did = str(row["id"])
    question = str(row.get("question") or "")
    decision = str(row.get("decision") or "") or did
    why = str(row.get("why") or "")
    rejected = [str(a) for a in row.get("alternatives_rejected") or []]
    fm: dict = {
        "type": "Decision",
        "id": did,
        "aliases": [did],
        "description": _description(decision),
        "question": question,
    }
    if rejected:
        fm["alternatives_rejected"] = rejected
    if row.get("ts"):
        fm["timestamp"] = str(row["ts"])
    if row.get("actor"):
        fm["actor"] = str(row["actor"])
    fm.update({k: v for k, v in row.items() if k not in _DECISION_CONSUMED})
    paragraphs = [
        f"**Question.** {question}",
        f"**Decision.** {decision}",
        f"**Why.** {why}",
    ]
    if rejected:
        paragraphs.append("**Rejected.** " + "; ".join(rejected))
    body = "\n\n".join(paragraphs) + "\n"
    directory = root / "decisions"
    slug = pages.unique_slug(directory, pages.slugify(decision, fallback="decision"))
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    return pages.Page(path=path, fm=fm, body=body)


# --- questions ------------------------------------------------------------


# Event fields consumed into the SPEC §7 question-page slots; anything else
# on an event is folded into the page frontmatter (unknown keys survive,
# SPEC §6.6 — matching what sources/claims/decisions do with row leftovers).
_QUESTION_CONSUMED = ("id", "ts", "text", "actor", "status", "note")


def _fold_question_events(events: list[dict]) -> list[dict]:
    """One record per question id, in ask order: the ask text and timestamp
    come from the first event, the status from the last event that set one
    (last status wins), and — when the final status is "answered" — the
    answering event contributes answered/answered_by and any note. Fields the
    migration doesn't consume (priority, blocking, confidence, …) are folded
    across all of the question's events, later events winning per key.
    """
    order: list[str] = []
    folds: dict[str, dict] = {}
    for ev in events:
        qid = str(ev.get("id") or "")
        if not qid:
            continue
        rec = folds.get(qid)
        if rec is None:
            rec = folds[qid] = {
                "id": qid, "ask": ev, "status": "open", "answer": None, "extras": {},
            }
            order.append(qid)
        if ev.get("status"):
            rec["status"] = str(ev["status"])
            rec["answer"] = ev if rec["status"] == "answered" else None
        rec["extras"].update({k: v for k, v in ev.items() if k not in _QUESTION_CONSUMED})
    return [folds[qid] for qid in order]


def _write_question_page(root: Path, rec: dict) -> pages.Page:
    qid = rec["id"]
    ask = rec["ask"]
    text = str(ask.get("text") or "").strip() or qid
    fm: dict = {
        "type": "Question",
        "id": qid,
        "aliases": [qid],
        "description": _description(text),
        "status": rec["status"],
    }
    if ask.get("ts"):
        fm["timestamp"] = str(ask["ts"])
    if ask.get("actor"):
        fm["actor"] = str(ask["actor"])
    body = text + "\n"
    answer = rec["answer"]
    if rec["status"] == "answered" and answer is not None:
        if answer.get("ts"):
            fm["answered"] = str(answer["ts"])
        if answer.get("actor"):
            fm["answered_by"] = str(answer["actor"])
        note = str(answer.get("note") or "").strip()
        if note:
            body = body.rstrip("\n") + f"\n\n## Answer\n{note}\n"
    fm.update(rec["extras"])
    directory = root / "questions"
    slug = pages.unique_slug(directory, pages.slugify(text, fallback="question"))
    path = pages.write_page(directory / f"{slug}.md", fm, body)
    return pages.Page(path=path, fm=fm, body=body)


# --- notebook.md ------------------------------------------------------------


def _upgrade_notebook_md(root: Path, m: manifest.Manifest) -> None:
    """Give a v0.3 notebook.md the OKF `type` frontmatter v0.4 requires.

    v0.3 never wrote frontmatter on notebook.md; v0.4 requires a `type` on
    every non-reserved page (SPEC §3). The prose body is preserved byte-for-
    byte; existing frontmatter keys survive (SPEC §6.6) and only a missing
    `type` (plus a `description` when absent) is added. An unparseable file
    is left alone — doctor reports it.
    """
    path = root / "notebook.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    try:
        fm, body = pages.parse(text)
    except ValueError:
        return
    if fm.get("type"):
        return
    if fm:
        fm = {"type": "Notebook", **fm}
    else:
        fm = {"type": "Notebook", "description": m.title or m.slug}
    pages.write_page(path, fm, body)


# --- sessions -------------------------------------------------------------


def _parse_session_file(text: str) -> tuple[dict, str]:
    """Split an old session file into (metadata, body).

    Real YAML frontmatter parses through the pages layer; otherwise a leading
    pseudo-frontmatter block — an initial run of `key: value` lines ended by
    a blank line, as some v0.3 templates wrote — is folded into metadata.
    Anything else is all body.
    """
    try:
        fm, body = pages.parse(text)
    except ValueError:
        return {}, text
    if fm:
        return fm, body
    lines = text.splitlines()
    meta: dict = {}
    consumed = 0
    for line in lines:
        head, sep, tail = line.partition(":")
        key = head.strip()
        bare = key.replace("_", "").replace("-", "")
        if not sep or not bare or not bare.isalnum() or key != key.lower():
            break  # metadata keys are lowercase identifiers (actor, model, started…)
        meta[key] = tail.strip()
        consumed += 1
    if not meta:
        return {}, text
    rest = "\n".join(lines[consumed:]).lstrip("\n")
    return meta, rest + ("\n" if rest and not rest.endswith("\n") else "")


def _move_session(root: Path, old: Path) -> Path:
    meta, body = _parse_session_file(old.read_text(encoding="utf-8"))
    fm: dict = {"type": "Work Session"}
    fm.update(meta)
    directory = root / "sessions"
    stem = pages.unique_slug(directory, old.stem)
    path = pages.write_page(directory / f"{stem}.md", fm, body)
    old.unlink()
    return path


# --- the migration --------------------------------------------------------


def migrate(root: Path) -> dict:
    """Convert a v0.3 notebook at `root` to v0.4 in place.

    Returns a summary dict of per-entity counts: {"sources": n, "claims": n,
    "decisions": n, "questions": n, "sessions": n, "already_migrated": n} —
    the last counts ledger rows skipped because a page with their id already
    exists (a resumed run).
    """
    root = Path(root)
    toml_path = root / NOTEBOOK_TOML
    if not toml_path.is_file():
        if is_notebook_root(root):
            raise SystemExit(
                f"{root} is already a v0.4 notebook (no {NOTEBOOK_TOML}); nothing to migrate"
            )
        raise SystemExit(
            f"{root} is not a flip notebook (no {NOTEBOOK_TOML} to migrate and no "
            f"{ROOT_FILE} with flip manifest frontmatter)"
        )

    # Parse everything before writing anything, so a bad ledger aborts clean.
    m = _manifest_from_toml(root, toml_path)
    source_rows = _read_ledger(root, SOURCES_LEDGER)
    claim_rows = _read_ledger(root, CLAIMS_LEDGER)
    decision_rows = _read_ledger(root, DECISIONS_LEDGER)
    question_events = _read_ledger(root, QUESTIONS_LEDGER)
    for what, rows, rel in (
        ("source", source_rows, SOURCES_LEDGER),
        ("claim", claim_rows, CLAIMS_LEDGER),
        ("decision", decision_rows, DECISIONS_LEDGER),
    ):
        for i, row in enumerate(rows, 1):
            if not row.get("id"):
                raise SystemExit(f"{root / rel}:{i}: {what} row has no id; fix it, then re-run")

    manifest.save_manifest(root, m)  # the root index.md IS the manifest now
    _upgrade_notebook_md(root, m)  # v0.3 notebook.md gains its OKF type

    counts = {
        "sources": 0, "claims": 0, "decisions": 0, "questions": 0, "sessions": 0,
        "already_migrated": 0,
    }
    # Resume support: a run interrupted between writing pages and unlinking
    # the ledger leaves rows whose pages already exist. Re-writing them would
    # duplicate pages under a -2 slug AND their ids — skip them instead.
    existing_ids = _existing_page_ids(root)

    def _fresh(row_id: object) -> bool:
        if str(row_id) in existing_ids:
            counts["already_migrated"] += 1
            return False
        return True

    for row in source_rows:
        if _fresh(row["id"]):
            _write_source_page(root, row)
            counts["sources"] += 1
    (root / SOURCES_LEDGER).unlink(missing_ok=True)

    src_by_id = {p.id: p for p in pages.iter_pages(root, "references") if p.id}
    for row in claim_rows:
        if _fresh(row["id"]):
            _write_claim_page(root, row, src_by_id)
            counts["claims"] += 1
    (root / CLAIMS_LEDGER).unlink(missing_ok=True)

    for row in decision_rows:
        if _fresh(row["id"]):
            _write_decision_page(root, row)
            counts["decisions"] += 1
    (root / DECISIONS_LEDGER).unlink(missing_ok=True)

    for rec in _fold_question_events(question_events):
        if _fresh(rec["id"]):
            _write_question_page(root, rec)
            counts["questions"] += 1
    (root / QUESTIONS_LEDGER).unlink(missing_ok=True)

    sessions_dir = root / SESSIONS_DIR
    if sessions_dir.is_dir():
        for old in sorted(sessions_dir.glob("*.md")):
            _move_session(root, old)
            counts["sessions"] += 1
        if not any(sessions_dir.iterdir()):
            sessions_dir.rmdir()

    toml_path.unlink()  # last: an interrupted migration stays resumable
    manifest.touch_updated(root)
    _regenerate_views(root)
    return counts
