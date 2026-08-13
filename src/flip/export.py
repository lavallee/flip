"""Interop exports (SPEC §17): BagIt bags and CSL JSON.

Exports are projections — the canonical artifact stays the plain-file
notebook, and exporters never mutate it. `export_bag` writes a BagIt 1.0 bag
for cold archival; `export_csl` maps the source entity pages under
references/ to CSL-JSON items for citation managers.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from . import claims as claims_mod
from . import pages, stance
from .manifest import load_manifest
from .util import ROOT_FILE, is_notebook_root, read_jsonl, sha256_file, today, utc_now

# The stable JSON projection contract (SPEC §17, Lane F). Bump only on a
# breaking shape change; renderers key off this string.
RENDER_CONTRACT = "flip-render/1"
RENDER_CONTRACT_2 = "flip-render/2"
LOG_TAIL = 20

# Directory names excluded from bag payloads: repo/tooling internals and
# derived renders are not evidentiary content (SPEC §11, §16).
EXCLUDE_DIRS = {".git", ".venv", ".flip", "renders", "__pycache__"}

_CSL_TYPES = {
    "paper": "article-journal",
    "web": "webpage",
    "article": "webpage",  # "article" sources are captured web articles
    "dataset": "dataset",
    "file": "dataset",
    "document": "dataset",
    "talk": "speech",
    "transcript": "speech",
}

# Fallback when a page carries no `kind`: infer from the id prefix (SPEC §9).
_PREFIX_CSL_TYPES = {
    "P": "article-journal",
    "A": "webpage",
    "F": "dataset",
    "T": "speech",
}


def _require_notebook(root: Path) -> Path:
    root = Path(root)
    if not is_notebook_root(root):
        raise SystemExit(
            f"{root} is not a flip notebook (no {ROOT_FILE} with flip manifest "
            "frontmatter); pass a notebook root or run `flip new <slug>` first"
        )
    return root


def _payload_files(root: Path) -> list[Path]:
    """Notebook files relative to root, excluded dirs pruned, sorted.

    Symlinks are followed: a valid link — file or directory — contributes its
    resolved CONTENT under the link's own name (so `drafts/current -> v1`
    yields `drafts/current/...` paths whose bytes duplicate `drafts/v1/...`).
    A dangling link is skipped with a warning on stderr. Self-referential
    directory loops are cut by tracking each branch's resolved ancestors.
    """
    out: list[Path] = []

    def walk(dir_path: Path, seen_reals: frozenset[Path]) -> None:
        real = dir_path.resolve()
        if real in seen_reals:  # symlink loop back into an ancestor
            return
        seen_reals = seen_reals | {real}
        for entry in sorted(dir_path.iterdir()):
            if entry.is_symlink() and not entry.exists():
                rel = entry.relative_to(root).as_posix()
                print(
                    f"warning: skipping dangling symlink {rel} -> {entry.readlink()}",
                    file=sys.stderr,
                )
                continue
            if entry.is_dir():
                if entry.name not in EXCLUDE_DIRS:
                    walk(entry, seen_reals)
            elif entry.is_file():
                out.append(entry.relative_to(root))

    walk(root, frozenset())
    return sorted(out)


def export_bag(root: Path, dest: Path) -> Path:
    """Write a BagIt 1.0 bag of the notebook at `dest` for cold archival.

    Payload (`data/`) is the full notebook tree minus EXCLUDE_DIRS;
    `manifest-sha256.txt` carries per-file fixity; `bag-info.txt` carries
    Bagging-Date and Payload-Oxum (<octets>.<files>).

    Symlinks are materialized: a valid link's content is copied under the
    link's name, so `drafts/current/` appears in the bag as a full copy of
    the current draft (deliberate duplication — a bag is for cold storage,
    where the pointer matters more than the bytes saved). Dangling links are
    skipped with a warning. If anything fails mid-export, the partial bag at
    `dest` is removed before exiting, so a retry starts clean.
    """
    root = _require_notebook(root)
    dest = Path(dest)
    if dest.exists():
        raise SystemExit(f"{dest} already exists; export to a fresh path or remove it first")
    data = dest / "data"
    total_bytes = 0
    manifest_lines: list[str] = []
    try:
        for rel in _payload_files(root):
            target = data / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, target)
            total_bytes += target.stat().st_size
            manifest_lines.append(f"{sha256_file(target)}  data/{rel.as_posix()}")
        (dest / "bagit.txt").write_text(
            "BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n", encoding="utf-8"
        )
        (dest / "manifest-sha256.txt").write_text(
            "\n".join(manifest_lines) + "\n", encoding="utf-8"
        )
        (dest / "bag-info.txt").write_text(
            f"Bagging-Date: {today()}\nPayload-Oxum: {total_bytes}.{len(manifest_lines)}\n",
            encoding="utf-8",
        )
    except SystemExit:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise SystemExit(
            f"export bag failed ({e}); removed the partial bag at {dest} — "
            "fix the cause and re-run"
        ) from None
    return dest


def _issued(date: object) -> dict | None:
    """Parse a page date ("2025-11-23", "2025-11", "2025") to CSL issued."""
    parts: list[int] = []
    for piece in str(date).split("T")[0].split("-")[:3]:
        if not piece.isdigit():
            break
        parts.append(int(piece))
    if not parts:
        return None
    return {"date-parts": [parts]}


def _note(fm: dict) -> str:
    """Judgment note; a grade of "?" is custody, not judgment, and says nothing."""
    bits = [
        f"{key}: {fm[key]}"
        for key in ("grade", "independence", "freshness")
        if fm.get(key) and fm[key] != "?"
    ]
    return "; ".join(bits)


def _csl_type(fm: dict) -> str:
    kind = str(fm.get("kind", ""))
    if kind in _CSL_TYPES:
        return _CSL_TYPES[kind]
    prefix = str(fm.get("id", "")).rstrip("0123456789")
    return _PREFIX_CSL_TYPES.get(prefix, "document")


def export_csl(root: Path) -> list[dict]:
    """Map references/ source pages to CSL-JSON items (one per source, id order).

    Item id is the compact source id (P3, A1, …); the CSL type comes from the
    page's `kind` when present (migrated pages keep it) else the id prefix.
    """
    root = _require_notebook(root)
    items: list[dict] = []
    for page in pages.iter_pages(root, "references"):
        fm = page.fm
        item: dict = {"id": fm.get("id") or page.slug, "type": _csl_type(fm)}
        if fm.get("title"):
            item["title"] = str(fm["title"])
        if fm.get("authors"):
            # as_list: a hand-edited scalar `authors: Jane Doe` is one author,
            # not a string to iterate char by char.
            item["author"] = [{"literal": str(a)} for a in pages.as_list(fm["authors"])]
        issued = _issued(fm["date"]) if fm.get("date") else None
        if issued:
            item["issued"] = issued
        url = fm.get("resource") or fm.get("url")
        if url:
            item["URL"] = str(url)
        if fm.get("publisher"):
            item["publisher"] = str(fm["publisher"])
        note = _note(fm)
        if note:
            item["note"] = note
        items.append(item)
    return sorted(items, key=_id_sort_key)


def _id_sort_key(item: dict) -> tuple:
    rid = str(item.get("id", ""))
    head = rid.rstrip("0123456789")
    tail = rid[len(head):]
    return (head, int(tail) if tail.isdigit() else 0, rid)


def export_okf(
    root: Path, dest: Path, include_private: bool = False, announce: Path | None = None
) -> Path:
    """OKF policy-filter export; see okf.py (SPEC §17)."""
    from .okf import export_okf as _export_okf

    return _export_okf(root, dest, include_private=include_private, announce=announce)


# --- the JSON render contract (SPEC §17, Lane F) ---------------------------------


def _provenance_index(root: Path) -> dict[str, list[dict]]:
    """source_id → capture events, chronological (ledger) order. A corrupt
    ledger yields nothing here — doctor pinpoints the line."""
    events: dict[str, list[dict]] = {}
    try:
        rows = read_jsonl(root / "sources" / "_provenance.jsonl")
    except ValueError:
        return {}
    for ev in rows:
        sid = ev.get("source_id")
        if sid:
            events.setdefault(str(sid), []).append(ev)
    return events


def _capture_event(fm: dict, prov: dict[str, list[dict]]) -> dict:
    """The provenance event describing the file `local` points at (multi-file
    captures log one event per file), else the most recent; {} when none."""
    events = prov.get(str(fm.get("id"))) or []
    if not events:
        return {}
    local = str(fm.get("local") or "")
    return next(
        (e for e in reversed(events) if str(e.get("local_path") or "") == local),
        events[-1],
    )


def _source_projection(page: pages.Page, prov: dict[str, list[dict]], full_trail: bool,
                       render_version: int = 1) -> dict:
    """One source as a render node. Judgment (grade/independence/freshness/
    kind) always ships; custody (title, canonical_url, captured_at, sha256)
    ships only with the full trail — the 0.4 lesson: anything derived from
    withheld data is withheld data (SPEC §17)."""
    fm = page.fm
    sid = fm.get("id") or page.slug
    out: dict = {
        "id": sid,
        # A source slug is derived from its title, so a withheld title would
        # round-trip through it — the slug is custody too (SPEC §17).
        "slug": page.slug if full_trail else str(sid),
        "kind": str(fm.get("kind", "")),
        "grade": str(fm.get("grade", "?")),
        "independence": str(fm.get("independence", "")),
        "freshness": str(fm.get("freshness", "")),
    }
    if render_version >= 2:
        support = fm.get("support")
        if isinstance(support, dict) and support:
            out["support"] = dict(support)
        for key in ("pipeline", "pipeline_evidence", "provenance_state"):
            if fm.get(key):
                out[key] = str(fm[key])
    if full_trail:
        ev = _capture_event(fm, prov)
        out["title"] = str(fm.get("title", ""))
        out["canonical_url"] = str(fm.get("resource") or fm.get("url") or "")
        out["captured_at"] = str(ev.get("ts", ""))
        out["sha256"] = str(ev.get("sha256", ""))
    return out


def _verification_projection(record: dict) -> dict:
    """One `verified:` event as a flip-render/1 verification record: the
    contract keeps its {method, by, against?, date, note?} shape, so the OKF
    {by, at, …} event maps back (`date` is the date part of `at`)."""
    out: dict = {"method": str(record.get("method", "")), "by": str(record.get("by", ""))}
    against = [str(a) for a in pages.as_list(record.get("against"))]
    if against:
        out["against"] = against
    out["date"] = str(record.get("at", ""))[:10]
    if record.get("note"):
        out["note"] = str(record.get("note"))
    return out


def _claim_projection(page: pages.Page, source_fms: list[dict],
                      render_version: int = 1) -> dict:
    fm = page.fm
    source_ids = claims_mod.source_ids(fm)
    out = {
        "id": fm.get("id") or page.slug,
        "slug": page.slug,
        "text": str(fm.get("description", "")),
        "status": str(fm.get("status", "")),
        "load_bearing": bool(fm.get("load_bearing", False)),
        "sources": source_ids,
    }
    # `corroboration` is OMITTED, not zeroed, where the axis does not apply
    # (SPEC §7). A renderer reading 0 would print "no independent support" of
    # a claim whose support is the document it is about; a renderer reading a
    # missing key has to go and look, which is the outcome this whole
    # distinction exists to produce. `subjects` (v2) is why it is missing.
    corroboration = claims_mod.claim_corroboration(source_fms, fm)
    if corroboration is not None:
        out["corroboration"] = corroboration
    out["verifications"] = [
        _verification_projection(v)
        for v in pages.as_list(fm.get("verified"))
        if isinstance(v, dict)
    ]
    if render_version >= 2:
        subjects = claims_mod.subject_ids(fm)
        if subjects:
            out["subjects"] = subjects
        # Absence scope and derivation edges (SPEC §7) travel when present:
        # a null's coverage IS its weight, and a renderer that can't see
        # derives_from can't show what a claim rests on.
        if isinstance(fm.get("absence"), dict):
            out["absence"] = dict(fm["absence"])
        derived = claims_mod.derivation_ids(fm)
        if derived:
            out["derives_from"] = derived
        if fm.get("value") is not None:
            out["value"] = str(fm.get("value"))
            if fm.get("unit"):
                out["unit"] = str(fm.get("unit"))
        # Stance and exposure travel only when the notebook used them (SPEC
        # §7.1). `exposure` is recomputed here rather than copied: it is
        # derived, so the export is a projection of the record, never a
        # carrier for a stored verdict.
        if stance.stance_records(fm) or stance.test_records(fm) or stance.rival_records(fm):
            out["exposure"] = stance.derive_exposure(fm)
            out["stances"] = [dict(r) for r in stance.stance_records(fm)]
            out["tests"] = [
                {**r, "severity": stance.test_severity(r)} for r in stance.test_records(fm)
            ]
            out["rivals"] = stance.rival_ids(fm)
            if stance.superseded_by(fm):
                out["superseded_by"] = stance.superseded_by(fm)
    return out


def _question_projection(page: pages.Page, render_version: int = 1) -> dict:
    fm = page.fm
    out = {
        "id": fm.get("id") or page.slug,
        "slug": page.slug,
        "text": str(fm.get("description", "")),
        "status": str(fm.get("status", "open")),
        "formulations": [dict(f) for f in pages.as_list(fm.get("formulations"))],
    }
    if render_version >= 2:
        out["resolves_via"] = [str(s) for s in pages.as_list(fm.get("resolves_via"))]
        # The journey keys (SPEC §7) travel only when the page carries them —
        # a renderer reading no `reopen_when` has nothing to watch, which is
        # the honest reading of a question that armed nothing.
        for key in ("closed_reason", "review_by"):
            if fm.get(key):
                out[key] = str(fm[key])
        triggers = [str(t) for t in pages.as_list(fm.get("reopen_when"))]
        if triggers:
            out["reopen_when"] = triggers
    return out


def _commission_projection(page: pages.Page) -> dict:
    """One commission contract as a flip-render/2 node (SPEC §7): the four
    contract fields, the lifecycle state, and the consumed receipt when the
    run returned one."""
    fm = page.fm
    out = {
        "id": fm.get("id") or page.slug,
        "deliverable": str(fm.get("description", "")),
        "status": str(fm.get("status", "proposed")),
        "universe": str(fm.get("universe", "")),
        "stop": str(fm.get("stop", "")),
        "does_not_redo": str(fm.get("does_not_redo", "")),
    }
    for key in ("for", "roi_low", "roi_high", "consumed"):
        if fm.get(key):
            out[key] = str(fm[key])
    return out


def _forecast_projection(page: pages.Page) -> dict:
    """One forecast as a flip-render/2 node (SPEC §7): the bet, its current
    scalars, and the resolution wiring a renderer needs to show a board —
    plus the update count (the full append-only trail stays on the page)."""
    fm = page.fm
    return {
        "id": fm.get("id") or page.slug,
        "question": str(fm.get("question") or fm.get("description", "")),
        "status": str(fm.get("status", "open")),
        "probability": fm.get("probability"),
        "confidence": fm.get("confidence"),
        "resolves_by": str(fm.get("resolves_by", "")),
        "resolves_via": [str(s) for s in pages.as_list(fm.get("resolves_via"))],
        "horizon": fm.get("horizon"),
        "updates": len(pages.as_list(fm.get("updates"))),
    }


def _decision_projection(page: pages.Page) -> dict:
    fm = page.fm
    return {
        "id": fm.get("id") or page.slug,
        "slug": page.slug,
        "text": str(fm.get("description", "")),
        "question": str(fm.get("question", "")),
        "alternatives_rejected": [str(a) for a in pages.as_list(fm.get("alternatives_rejected"))],
    }


_GOAL_RE = re.compile(r"^##\s+Goal[ \t]*\n(.*?)(?=^##\s|\Z)", re.S | re.M)


def _session_goal(body: str) -> str:
    m = _GOAL_RE.search(body)
    return " ".join(m.group(1).split()) if m else ""


def _session_projection(page: pages.Page) -> dict:
    fm = page.fm
    return {
        "id": page.slug,  # sessions have no compact id scheme (SPEC §8)
        "actor": pages.generated_by(fm),
        "model": str(fm.get("model", "")),
        "started": str(fm.get("started", "")),
        "ended": str(fm.get("ended", "")),
        "goal": _session_goal(page.body),
    }


def _id_num(entity_id: object) -> tuple:
    s = str(entity_id or "")
    head = s.rstrip("0123456789")
    tail = s[len(head):]
    return (head, int(tail) if tail.isdigit() else 0, s)


def export_json(root: Path, include_private: bool = False, render_version: int = 1) -> dict:
    """The `flip-render/1` (default) or `flip-render/2` JSON projection for
    renderers and site generators (SPEC §17, Lane F): stable ids,
    deterministic order (id-sorted entities, stable key order), one changing
    field (`generated`). Version 2 is a superset: sources gain `support`,
    `pipeline`/`pipeline_evidence`, `provenance_state`; claims gain
    `value`/`unit`. Version 1 stays byte-stable for existing consumers.

    `drafts` (version 2) ships only under `include_private`: drafts are
    unfinished prose that `export okf` already withholds from every
    outside-facing bundle, so they travel to internal renderers and nowhere
    else. The key is always present under /2, empty when withheld.

    Policy-filtered exactly like `export okf`: refuses unless visibility is
    public or `include_private`; without the full source trail
    (`source_trail_public: false` and not include_private) custody detail —
    titles, URLs, capture times, fixity, the whole work log — is withheld,
    while judgment (grade/independence/freshness) and the claims/questions the
    notebook stands on still ship.
    """
    root = _require_notebook(root)
    m = load_manifest(root)
    visibility = m.policy.get("visibility", "internal")
    if visibility != "public" and not include_private:
        raise SystemExit(
            f"notebook visibility is '{visibility}'; the JSON render is a projection for "
            "outside consumption — set visibility: public in the root index.md or pass "
            "--include-private"
        )
    full_trail = include_private or bool(m.policy.get("source_trail_public", False))

    source_pages = [p for p in pages.iter_pages(root, "references")
                    if str(p.fm.get("type", "")) == "Source"]
    source_fms = [p.fm for p in source_pages]
    prov = _provenance_index(root) if full_trail else {}

    sources = sorted(
        (_source_projection(p, prov, full_trail, render_version) for p in source_pages),
        key=lambda s: _id_num(s["id"]),
    )
    claims = sorted(
        (_claim_projection(p, source_fms, render_version) for p in pages.iter_pages(root, "claims")
         if str(p.fm.get("type", "")) == "Claim"),
        key=lambda c: _id_num(c["id"]),
    )
    questions = sorted(
        (_question_projection(p, render_version) for p in pages.iter_pages(root, "questions")
         if str(p.fm.get("type", "")) == "Question"),
        key=lambda q: _id_num(q["id"]),
    )
    decisions = sorted(
        (_decision_projection(p) for p in pages.iter_pages(root, "decisions")
         if str(p.fm.get("type", "")) == "Decision"),
        key=lambda d: _id_num(d["id"]),
    )
    # Forecasts arrived with flip-render/2 (SPEC §7); version 1 stays
    # byte-stable for existing consumers and never grows the key.
    forecasts = (
        sorted(
            (_forecast_projection(p) for p in pages.iter_pages(root, "forecasts")
             if str(p.fm.get("type", "")) == "Forecast"),
            key=lambda f: _id_num(f["id"]),
        )
        if render_version >= 2
        else None
    )
    # Commissions ride flip-render/2 for the same reason.
    commissions = (
        sorted(
            (_commission_projection(p) for p in pages.iter_pages(root, "commissions")
             if str(p.fm.get("type", "")) == "Commission"),
            key=lambda k: _id_num(k["id"]),
        )
        if render_version >= 2
        else None
    )
    # Session pages are the work log in entity form — their goals, and the
    # goal-derived filename slugs, are custody like log_tail (SPEC §17).
    sessions = (
        [_session_projection(p) for p in pages.iter_pages(root, "sessions")]
        if full_trail
        else []
    )

    # The work log is custody: withheld unless the full trail ships (SPEC §17).
    log_tail: list[dict] = []
    if full_trail:
        try:
            log_tail = read_jsonl(root / "log" / "log.jsonl")[-LOG_TAIL:]
        except ValueError:
            log_tail = []

    out = {
        "contract": RENDER_CONTRACT_2 if render_version >= 2 else RENDER_CONTRACT,
        "generated": utc_now(),
        "source_trail_public": full_trail,
        "notebook": {
            "uid": m.uid,
            "slug": m.slug,
            "title": m.title,
            "kind": m.kind,
            "status": m.status,
            "created": m.created,
            "updated": m.updated,
            "visibility": visibility,
        },
        "sources": sources,
        "claims": claims,
        "questions": questions,
        "decisions": decisions,
        "sessions": sessions,
        "log_tail": log_tail,
    }
    # Declared discipline pins travel with the render (flip-render/2 only —
    # version 1 stays byte-stable): the identity of the *standard*, not just
    # the author, rides with the bundle. Absent when nothing is declared —
    # the implicit set is self-description, not an advertised standard.
    if render_version >= 2 and m.disciplines:
        out["notebook"]["disciplines"] = [str(p) for p in m.disciplines]
    if forecasts is not None:
        out["forecasts"] = forecasts
    if commissions is not None:
        out["commissions"] = commissions
    if render_version >= 2:
        out["work"] = _work_pages(root)
        # Drafts arrived after work (flip-render/2, SPEC §11). They are the
        # notebook's unfinished prose, so they ride the *private* lane only:
        # `export okf` drops drafts/ from every outside-facing bundle
        # (okf.EXCLUDE_NAMES), and a draft reaching a public renderer just
        # because the notebook went public would contradict that. Internal
        # renderers — agent sites, review surfaces — pass include_private and
        # get them. Always an array under /2 so consumers can iterate without
        # a key check; empty when withheld or absent.
        out["drafts"] = _draft_pages(root) if include_private else []
    return out


def _work_pages(root: Path) -> list[dict]:
    """The notebook's WORK, for flip-render/2: the completed/in-progress
    prose that the sources and claims exist to support. notebook.md (the
    working memory) first, then root-level prose renders (criteria.md,
    review.md, baseline.md, HANDOFF.md, …), then analysis/ pages. The
    notebook's own prose is not custody — it ships regardless of the
    source-trail policy, exactly like claims and questions do."""
    out: list[dict] = []

    def _add(path: Path, rel: str, default_title: str) -> None:
        try:
            page = pages.read_page(path)
            title = str(page.fm.get("title") or default_title)
            body = page.body.strip()
        except SystemExit:  # a prose file without frontmatter (HANDOFF.md …)
            title, body = default_title, path.read_text(encoding="utf-8").strip()
        out.append({"path": rel, "title": title, "body": body})

    nb = root / "notebook.md"
    if nb.is_file():
        _add(nb, "notebook.md", "Working memory")
    for path in sorted(root.glob("*.md")):
        if path.name in ("index.md", "log.md", "notebook.md") or path.name.startswith("_"):
            continue
        _add(path, path.name, path.stem)
    analysis = root / "analysis"
    if analysis.is_dir():
        for path in sorted(analysis.glob("*.md")):
            if path.name in pages.RESERVED or path.name.startswith("_"):
                continue
            _add(path, f"analysis/{path.name}", path.stem)
    return out


def _draft_pages(root: Path) -> list[dict]:
    """The notebook's DRAFTS, for flip-render/2 (SPEC §11): the in-progress
    prose a reader of an internal surface actually wants to read.

    Two shapes exist in the wild and both ship. SPEC §11 versions drafts
    explicitly (`drafts/v0/`, `drafts/v1/`, a `current` symlink), while
    `flip new --kind pursuit` scaffolds a flat `drafts/question-plan.md`.
    Flat files sort first, then versioned directories in name order.

    `current` (and any other symlinked directory) is skipped: it resolves to
    a version already emitted, and following it would duplicate every draft
    under a second path — the same trap `export bag` documents. Each entry
    carries `slug` so renderers can build a stable route without re-deriving
    one from the path.
    """
    drafts = root / "drafts"
    if not drafts.is_dir():
        return []
    out: list[dict] = []

    def _add(path: Path, rel: str, slug: str, default_title: str) -> None:
        try:
            page = pages.read_page(path)
            title = str(page.fm.get("title") or default_title)
            body = page.body.strip()
        except SystemExit:  # a draft without frontmatter — the common case
            title, body = default_title, path.read_text(encoding="utf-8").strip()
        out.append({"slug": slug, "path": rel, "title": title, "body": body})

    for path in sorted(drafts.glob("*.md")):
        if path.name in pages.RESERVED or path.name.startswith("_"):
            continue
        _add(path, f"drafts/{path.name}", path.stem, path.stem)
    for version in sorted(p for p in drafts.iterdir() if p.is_dir()):
        if version.is_symlink() or version.name.startswith("_"):
            continue
        for path in sorted(version.glob("*.md")):
            if path.name in pages.RESERVED or path.name.startswith("_"):
                continue
            _add(
                path,
                f"drafts/{version.name}/{path.name}",
                f"{version.name}-{path.stem}",
                f"{path.stem} ({version.name})",
            )
    return out
