"""Source capture: fetcher routing, custody, provenance, entity pages (SPEC §5).

`add_source` is the write path for `flip add-source`: classify the target,
allocate a kind-prefixed id, capture bytes into sources/raw/ (builtin copy for
local files, a configured external fetcher for everything else), hash every
captured file into sources/_provenance.jsonl (append-only), and open a
references/<slug>.md entity page graded "?" — the canonical record of the
source (SPEC §5.3). `grade_source` is the write path for `flip grade`: record
the judgment keys on an existing page, round-tripping everything else on it
(frontmatter flip doesn't own and the prose body survive, SPEC §6.6).

Fetcher templates live in $FLIP_HOME/config.toml under [fetchers] (SPEC §15).
Placeholders: {url} = the target as given, {id} = the target with a leading
"doi:" stripped (for `doi-fetch {id}`-style tools), {dest} = the capture
directory sources/raw/<source id>/.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from . import manifest, pages
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
}

_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")
_ARXIV_RE = re.compile(r"^(arxiv:)?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)

_EXAMPLE_TEMPLATES = {
    "web": "single-file {url} --output {dest}",
    "paper": "doi-fetch {id} --dir {dest}",
}


def _classify(target: str) -> str:
    """Infer a source kind from the target when the caller didn't name one."""
    if Path(target).expanduser().exists():
        return "file"
    if target.startswith(("http://", "https://")):
        return "web"
    if target.lower().startswith("doi:") or _DOI_RE.match(target) or _ARXIV_RE.match(target):
        return "paper"
    raise SystemExit(
        f"can't classify '{target}' (not an existing file, http(s) URL, DOI, or arXiv id) — "
        "pass the kind explicitly, e.g. --kind web|paper|file|dataset|talk"
    )


def _config_path() -> Path:
    return Path(os.environ.get("FLIP_HOME", "~/.flip")).expanduser() / "config.toml"


def _fetcher_template(kind: str) -> str:
    """Look up the [fetchers] command template for a kind; actionable error if absent."""
    config = _config_path()
    example = _EXAMPLE_TEMPLATES.get(kind, "fetch-cmd {url} --output {dest}")
    stanza = f'[fetchers]\n{kind} = "{example}"'
    if not config.is_file():
        raise SystemExit(
            f"no fetcher configured for kind '{kind}' ({config} does not exist) — "
            f"create it with a stanza like:\n{stanza}"
        )
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{config}: invalid TOML: {e}") from None
    template = data.get("fetchers", {}).get(kind)
    if not isinstance(template, str) or not template.strip():
        raise SystemExit(
            f"no fetcher configured for kind '{kind}' in {config} — add a stanza like:\n{stanza}"
        )
    return template.strip()


def _tool_version(tool: str) -> str | None:
    """Best effort `<tool> --version`: first output line on success, else None."""
    try:
        proc = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip() or proc.stderr.strip()
    return out.splitlines()[0] if out else None


def _capture_copy(root: Path, source_id: str, target: str) -> tuple[list[Path], str]:
    """builtin:copy — copy one local file verbatim into sources/raw/<id><suffix>.

    Returns ([copied path], origin file:// URI).
    """
    src = Path(target).expanduser()
    if src.is_dir():
        raise SystemExit(
            f"'{target}' is a directory — point at a single file, or configure a "
            f"[fetchers] command in {_config_path()} for multi-file captures"
        )
    if not src.is_file():
        raise SystemExit(f"no such file '{target}' — check the path, or pass a URL/DOI instead")
    raw_dir = root / "sources" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{source_id}{src.suffix}"
    shutil.copy2(src, dest)
    return [dest], src.resolve().as_uri()


def _tokenize_template(template: str) -> list[str]:
    """Split a fetcher template into argv tokens.

    posix mode everywhere except Windows: posix-mode shlex treats backslashes
    as escapes, which mangles paths like C:\\Tools\\fetch.exe in a Windows
    user's config.toml.
    """
    return shlex.split(template, posix=(os.name != "nt"))


def _run_fetcher(
    root: Path, source_id: str, kind: str, target: str, template: str
) -> tuple[list[Path], str]:
    """Run a configured fetcher into sources/raw/<id>/; return (new files, argv[0])."""
    dest = root / "sources" / "raw" / source_id
    dest.mkdir(parents=True, exist_ok=True)
    before = {p for p in dest.rglob("*") if p.is_file()}
    bare = target[4:] if target.lower().startswith("doi:") else target
    argv = [
        tok.replace("{url}", target).replace("{id}", bare).replace("{dest}", str(dest))
        for tok in _tokenize_template(template)
    ]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=root)
    except FileNotFoundError:
        raise SystemExit(
            f"fetcher '{argv[0]}' for kind '{kind}' not found on PATH — "
            f"install it or fix [fetchers] in {_config_path()}"
        ) from None
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout).strip().splitlines()
        detail = lines[-1] if lines else "no output"
        raise SystemExit(
            f"fetcher for kind '{kind}' failed (exit {proc.returncode}): "
            f"{shlex.join(argv)} — {detail}"
        )
    new = [p for p in dest.rglob("*") if p.is_file() and p not in before]
    if not new:
        raise SystemExit(
            f"fetcher for kind '{kind}' wrote nothing to {dest} — "
            f"make sure its template in {_config_path()} uses the {{dest}} placeholder"
        )
    return new, argv[0]


def _regenerate_views(root: Path) -> None:
    """Refresh the generated index.md bodies / log.md after a mutation (SPEC §10)."""
    from . import views

    views.regenerate(root)


def _title_for(target: str, strategy: str) -> str:
    """The human-readable name a capture gets: no fetcher in the current
    protocol yields a title (they yield files), so the title is the file
    basename for copies and host+path for URLs; other targets (DOI, arXiv)
    keep the target string itself."""
    if strategy == "copy":
        return Path(target).expanduser().name
    if target.startswith(("http://", "https://")):
        parts = urlsplit(target)
        return f"{parts.netloc}{parts.path}".rstrip("/") or target
    return target


def _id_sort_key(fm: dict) -> tuple:
    m = re.match(r"^([A-Z]+)(\d+)$", str(fm.get("id", "")))
    return (0, m.group(1), int(m.group(2))) if m else (1, str(fm.get("id", "")), 0)


def add_source(
    root: Path, target: str, kind: str | None = None, note: str | None = None
) -> pages.Page:
    """Capture a source into the notebook; returns its new entity page.

    Routes by kind: "file" (or any kind whose configured fetcher is
    "builtin:copy") copies the file verbatim; everything else runs the
    [fetchers] command from $FLIP_HOME/config.toml. Appends one provenance
    event per captured file, opens references/<slug>.md at grade "?", touches
    the manifest. Local copies carry their origin file:// URI in provenance
    only; fetched targets also land on the page as `resource`.
    """
    root = require_notebook_root(root)
    kind = kind or _classify(target)
    source_id = pages.allocate_id(root, _ID_PREFIXES.get(kind, "S"))

    template = None if kind == "file" else _fetcher_template(kind)
    if template is None or template == "builtin:copy":
        files, origin = _capture_copy(root, source_id, target)
        tool, tool_version, strategy, url = "builtin:copy", None, "copy", origin
    else:
        files, tool = _run_fetcher(root, source_id, kind, target, template)
        tool_version, strategy, url = _tool_version(tool), "config", target

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
        event["actor"] = actor
        if note:
            event["note"] = note
        append_jsonl(prov_path, event)

    largest = max(files, key=lambda p: p.stat().st_size)
    title = _title_for(target, strategy)
    fm: dict = {
        "type": "Source",
        "id": source_id,
        "aliases": [source_id],
        "title": title,
        "description": note or f"{kind} source",
    }
    if strategy == "config":
        fm["resource"] = url  # for copies the origin URI lives in provenance, not the page
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
    slug_source = Path(title).stem if strategy == "copy" else title
    slug = pages.unique_slug(ref_dir, pages.slugify(slug_source, fallback=source_id.lower()))
    body = f"# {title}\n" + (f"\n{note}\n" if note else "")
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
