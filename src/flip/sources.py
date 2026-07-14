"""Source capture: fetcher routing, custody, provenance, entity pages (SPEC §5).

`add_source` is the write path for `flip add-source`: classify the target,
allocate a kind-prefixed id, capture bytes into sources/raw/ (builtin copy for
local files, a configured [fetchers] command for everything else via the
integrations layer), hash every captured file into sources/_provenance.jsonl
(append-only), and open a references/<slug>.md entity page graded "?" — the
canonical record of the source (SPEC §5.3). `grade_source` is the write path
for `flip grade`: record the judgment keys on an existing page, round-tripping
everything else on it (frontmatter flip doesn't own and the prose body survive,
SPEC §6.6).

Fetcher command templates and the capture runner live in `integrations` (SPEC
§15). A fetcher may hand back an optional neutral return envelope; when present,
its title/canonical_url flow onto the page and its strategy/retrieved_at/status/
backend_ref into provenance. Independence/freshness *hints* are recorded as a
page note only — grading stays a judgment made after reading, never auto-set.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from . import integrations, manifest, pages
from .util import (
    append_jsonl,
    detect_actor,
    require_notebook_root,
    sha256_file,
    utc_now,
)

GRADES = ("A", "B", "C", "?")
INDEPENDENCE = ("original", "republisher", "derivative", "self-interested")
FRESHNESS = ("fresh", "dated")

# SPEC §9 naming rules: P papers · A articles/web · F files/datasets/documents ·
# T talks/transcripts · S when unkinded/unknown. D is reserved for decisions —
# source ids never use it, so a bare [F3]/[D2] cite is unambiguous.
_ID_PREFIXES = {
    "paper": "P",
    "web": "A",
    "article": "A",
    "file": "F",
    "dataset": "F",
    "document": "F",
    "talk": "T",
    "transcript": "T",
    "social": "A",
}

_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")
_ARXIV_RE = re.compile(r"^(arxiv:)?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)
_X_POST_RE = re.compile(
    r"^/(?:i/web/)?(?:[^/]+/)?status(?:es)?/\d+(?:[/?#]|$)", re.IGNORECASE
)


def _classify(target: str) -> str:
    """Infer a source kind from the target when the caller didn't name one."""
    if Path(target).expanduser().exists():
        return "file"
    if target.startswith(("http://", "https://")):
        parts = urlsplit(target)
        host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("mobile.")
        if host in {"x.com", "twitter.com"} and _X_POST_RE.match(parts.path):
            return "social"
        return "web"
    if target.lower().startswith("doi:") or _DOI_RE.match(target) or _ARXIV_RE.match(target):
        return "paper"
    raise SystemExit(
        f"can't classify '{target}' (not an existing file, http(s) URL, DOI, or arXiv id) — "
        "pass the kind explicitly, e.g. --kind web|social|paper|file|dataset|talk"
    )


def _capture_copy(root: Path, source_id: str, target: str) -> tuple[list[Path], str]:
    """builtin:copy — copy one local file verbatim into sources/raw/<id><suffix>.

    Returns ([copied path], origin file:// URI).
    """
    src = Path(target).expanduser()
    if src.is_dir():
        raise SystemExit(
            f"'{target}' is a directory — point at a single file, or configure a "
            f"[fetchers] command in {integrations.config_path()} for multi-file captures"
        )
    if not src.is_file():
        raise SystemExit(f"no such file '{target}' — check the path, or pass a URL/DOI instead")
    raw_dir = root / "sources" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{source_id}{src.suffix}"
    shutil.copy2(src, dest)
    return [dest], src.resolve().as_uri()


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10)."""
    from . import views

    views.regenerate(root)


def _title_for(target: str, capture_kind: str) -> str:
    """The human-readable name a capture gets when the fetcher didn't supply one:
    the file basename for copies and host+path for URLs; other targets (DOI,
    arXiv) keep the target string itself."""
    if capture_kind == "copy":
        return Path(target).expanduser().name
    if target.startswith(("http://", "https://")):
        parts = urlsplit(target)
        return f"{parts.netloc}{parts.path}".rstrip("/") or target
    return target


def _hint_note(envelope: dict | None) -> str:
    """Render a fetcher's independence/freshness/status hints as a page note.

    Hints are leads for the grader, never the grade itself (custody discipline):
    they live in the body, not in the judgment frontmatter keys.
    """
    if not envelope:
        return ""
    bits = []
    if envelope.get("independence_hint") in INDEPENDENCE:
        bits.append(f"independence={envelope['independence_hint']}")
    if envelope.get("freshness_hint") in FRESHNESS:
        bits.append(f"freshness={envelope['freshness_hint']}")
    status = envelope.get("status")
    if isinstance(status, str) and status and status != "success":
        bits.append(f"status={status}")
    if not bits:
        return ""
    return (
        "> capture hints (from the fetcher, unverified — judge with `flip grade`): "
        + ", ".join(bits) + "\n"
    )


def _id_sort_key(fm: dict) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(fm.get("id", "")))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(fm.get("id", "")), 0)


def add_source(
    root: Path,
    target: str,
    kind: str | None = None,
    note: str | None = None,
    via: str | None = None,
) -> pages.Page:
    """Capture a source into the notebook; returns its new entity page.

    Routes by kind: "file" (or any kind whose configured fetcher is
    "builtin:copy") copies the file verbatim; everything else runs the
    [fetchers] command resolved from $FLIP_HOME/config.toml (optionally a named
    variant, `--via`). Appends one provenance event per captured file, opens
    references/<slug>.md at grade "?", touches the manifest. Local copies carry
    their origin file:// URI in provenance only; fetched targets also land on
    the page as `resource` (the fetcher's canonical_url when it reports one).
    """
    root = require_notebook_root(root)
    kind = kind or _classify(target)
    source_id = pages.allocate_id(root, _ID_PREFIXES.get(kind, "S"))

    resolved = None if kind == "file" else integrations.resolve("fetchers", kind, via=via)
    envelope: dict | None = None
    if resolved is None or resolved.template == "builtin:copy":
        files, origin = _capture_copy(root, source_id, target)
        tool, tool_version, capture_kind, strategy, url = (
            "builtin:copy", None, "copy", "copy", origin,
        )
    else:
        run = integrations.run_capture(resolved, root, source_id, target)
        files, tool, tool_version = run.files, run.tool, run.tool_version
        capture_kind, strategy, url, envelope = "config", run.strategy, target, run.envelope

    ts = utc_now()
    actor = detect_actor()
    prov_path = root / "sources" / "_provenance.jsonl"
    for f in sorted(files):
        event: dict = {
            "ts": ts,
            "source_id": source_id,
            "url": url,
            "local_path": f.relative_to(root).as_posix(),
            "sha256": sha256_file(f),
            "bytes": f.stat().st_size,
            "tool": tool,
        }
        if tool_version:
            event["tool_version"] = tool_version
        event["strategy"] = strategy
        if envelope:
            for key in ("canonical_url", "retrieved_at", "status", "mime", "backend_ref"):
                value = envelope.get(key)
                if value not in (None, "", [], {}):
                    event[key] = value
            if envelope.get("from_cache"):  # only the interesting signal: a store hit
                event["from_cache"] = True
        event["actor"] = actor
        if note:
            event["note"] = note
        append_jsonl(prov_path, event)

    # the page's primary artifact is the largest real capture, never the tiny
    # flip.json envelope sidecar (which is metadata, not content)
    primary = [f for f in files if f.name != "flip.json"] or files
    largest = max(primary, key=lambda p: p.stat().st_size)
    env_title = envelope.get("title") if envelope else None
    title = env_title.strip() if isinstance(env_title, str) and env_title.strip() \
        else _title_for(target, capture_kind)
    fm: dict = {
        "type": "Source",
        "id": source_id,
        "aliases": [source_id],
        "title": title,
        "description": note or f"{kind} source",
    }
    if capture_kind == "config":
        canonical = envelope.get("canonical_url") if envelope else None
        # for copies the origin URI lives in provenance, not the page
        fm["resource"] = canonical.strip() if isinstance(canonical, str) and canonical.strip() \
            else url
    fm.update(
        {
            "local": largest.relative_to(root).as_posix(),
            "grade": "?",
            "independence": "original",
            "freshness": "fresh",
            "status": "captured",
            "actor": actor,
        }
    )

    ref_dir = root / "references"
    # File captures slug from the stem: `districts.csv` lives at
    # references/districts.md, not districts-csv.md (dogfood finding:
    # extension noise doubles up on .md captures — "…-survey-md.md").
    slug_source = Path(title).stem if capture_kind == "copy" else title
    slug = pages.unique_slug(ref_dir, pages.slugify(slug_source, fallback=source_id.lower()))
    body = f"# {title}\n" + (f"\n{note}\n" if note else "")
    hint = _hint_note(envelope)
    if hint:
        body += ("\n" if not body.endswith("\n") else "") + hint
    path = pages.write_page(ref_dir / f"{slug}.md", fm, body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=path, fm=fm, body=body)


def source_pages(root: Path) -> list[pages.Page]:
    """Every source entity page under references/, filename order. Read-only
    helper for downstream consumers (claims, doctor, export); does not
    validate the notebook root — callers that mutate already have."""
    return pages.iter_pages(root, "references")


def list_sources(root: Path) -> list[dict]:
    """All sources as frontmatter dicts (+ slug and root-relative path), in id
    order. Read-only (backs `flip source list`)."""
    root = require_notebook_root(root)
    rows = [
        {**p.fm, "slug": p.slug, "path": p.path.relative_to(root).as_posix()}
        for p in source_pages(root)
    ]
    return sorted(rows, key=_id_sort_key)


def grade_source(
    root: Path,
    source_id: str,
    grade: str | None = None,
    independence: str | None = None,
    freshness: str | None = None,
    notes: str | None = None,
) -> pages.Page:
    """Record source-quality judgments on an existing page; returns the page.

    Touches only the keys flip owns here (grade/independence/freshness/notes);
    everything else on the page — foreign frontmatter, the prose body — round-
    trips untouched (SPEC §6.6), so an Obsidian-authored page survives.
    """
    root = require_notebook_root(root)
    for name, value, allowed in (
        ("grade", grade, GRADES),
        ("independence", independence, INDEPENDENCE),
        ("freshness", freshness, FRESHNESS),
    ):
        if value is not None and value not in allowed:
            raise SystemExit(f"invalid {name} '{value}' (one of: {', '.join(allowed)})")
    page = next((p for p in source_pages(root) if p.id == source_id), None)
    if page is None:
        known = ", ".join(p.id for p in source_pages(root) if p.id) or "none yet"
        raise SystemExit(
            f"unknown source id '{source_id}' in references/ (have: {known}) — "
            "run `flip add-source` first"
        )
    updates = {"grade": grade, "independence": independence, "freshness": freshness, "notes": notes}
    for key, value in updates.items():
        if value is not None:
            page.fm[key] = value
    pages.write_page(page.path, page.fm, page.body)
    manifest.touch_updated(root)
    _regenerate_views(root)
    return pages.Page(path=page.path, fm=page.fm, body=page.body)
