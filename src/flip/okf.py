"""OKF export — a policy filter over the bundle the notebook already is (SPEC §17).

Since v0.4 a flip notebook IS a conformant OKF v0.1 knowledge bundle at rest,
so exporting one is no longer a format transform: it is a **copy for outside
consumption**, honoring the manifest policy. `visibility` gates the export
(refuse unless `public` or `--include-private`); `source_trail_public`
decides whether custody detail ships (raw bytes, provenance ledger, log
ledgers and their generated log.md, URLs, fixity) or reference pages are
reduced to judgment stubs (grade / independence / freshness stay; the trail —
including capture notes and captured-file names in title/description — is
withheld). Nested exports (a bag or a previous OKF bundle inside the
notebook) are never payload: they are copies, not notebook content. The
exported bundle is a render (SPEC §11): regenerated in full on every export,
never edited in place, safe to delete.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import __version__, pages
from .manifest import load_manifest
from .registry import COPY_MARKERS
from .util import read_jsonl, utc_now

MARKER_START = "<!-- FLIP:START -->"
MARKER_END = "<!-- FLIP:END -->"
STATE_FILE = ".last-export.json"

# Directory names never part of an outside-facing bundle: generated renders,
# versioned drafts, reprocessable derivations, tooling internals. Dot-prefixed
# entries (.git, .venv, .flip, .obsidian, dotfiles) are excluded wholesale.
EXCLUDE_NAMES = {"renders", "drafts", "derived", "__pycache__", "node_modules"}

# Custody keys stripped from reference pages when the source trail is withheld
# (judgment keys — grade/independence/freshness/status — always ship). title
# and description are stripped separately: they carry the captured file's
# basename and the capture note.
TRAIL_KEYS = ("local", "resource", "url", "date", "authors", "publisher")

WITHHELD_NOTE = "_Source trail withheld by notebook policy; grading judgment shown above._"


def _regenerate_views(root: Path) -> None:
    """Refresh generated index.md bodies / log.md before copying (SPEC §10)."""
    from . import views

    views.regenerate(root)


def _included(rel_parts: tuple[str, ...], full_trail: bool) -> bool:
    """Policy filter for one file, as root-relative path parts."""
    wholesale = full_trail and rel_parts[0] in ("sources", "log")
    for part in rel_parts:
        if part.startswith("."):
            return False
        if part in EXCLUDE_NAMES:
            return False
        if part.startswith("_") and not wholesale:
            return False  # private scratch files; ledgers ship only with the trail
    if not full_trail:
        if rel_parts[0] in ("sources", "log"):
            return False  # custody bytes and event ledgers withheld
        if rel_parts == ("log.md",):
            return False  # the generated rendering of the withheld work log
    return True


def _export_dirs(root: Path) -> list[Path]:
    """Directories under `root` holding a previous export — a BagIt bag or an
    OKF bundle, marked by bagit.txt / .last-export.json (the same markers the
    registry prunes on). Their contents are copies of custody bytes, never
    notebook payload."""
    return [
        marker_path.parent
        for marker in COPY_MARKERS
        for marker_path in root.rglob(marker)
        if marker_path.parent != root
    ]


def _payload_files(root: Path, dest: Path, full_trail: bool) -> list[Path]:
    """Root-relative files passing the policy filter, sorted. A dest nested
    inside the notebook (or a stale export there) never feeds itself, and any
    nested export — bag or OKF bundle — is pruned wholesale: a stripped
    export must not ship raw custody bytes riding inside an old full-trail
    copy."""
    dest = dest.resolve()
    nested_exports = _export_dirs(root)
    out: list[Path] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.resolve().is_relative_to(dest):
            continue
        if any(path.is_relative_to(d) for d in nested_exports):
            continue
        rel = path.relative_to(root)
        if _included(rel.parts, full_trail):
            out.append(rel)
    return out


def _provenance_by_source(root: Path) -> dict[str, list[dict]]:
    """source_id → capture events, in ledger (chronological) order."""
    events: dict[str, list[dict]] = {}
    for ev in read_jsonl(root / "sources" / "_provenance.jsonl"):
        sid = ev.get("source_id")
        if sid:
            events.setdefault(str(sid), []).append(ev)
    return events


def _filter_reference_page(path: Path, prov: dict[str, list[dict]], full_trail: bool) -> None:
    """Apply the source-trail policy to one COPIED reference page (never the
    notebook's own). Full trail: enrich frontmatter with fixity from the
    provenance event for the page's `local` file. Withheld: strip custody
    keys plus title/description (capture note, captured basename) and replace
    the body with a judgment stub headed by the id. Foreign frontmatter keys
    survive either way.
    """
    page = pages.read_page(path)
    fm = dict(page.fm)
    if full_trail:
        events = prov.get(page.id) or []
        if not events:
            return  # nothing to add; keep the copied bytes untouched
        # Fixity must describe the file `local` points at: multi-file captures
        # log one event per file, so pick the event whose local_path matches;
        # fall back to the most recent event when none does.
        local = str(fm.get("local") or "")
        ev = next(
            (e for e in reversed(events) if str(e.get("local_path") or "") == local),
            events[-1],
        )
        for key, value in (
            ("sha256", ev.get("sha256")),
            ("retrieved_at", ev.get("ts")),
            ("captured_with", ev.get("tool")),
        ):
            if value:
                fm[key] = value
        body = page.body
    else:
        for key in TRAIL_KEYS:
            fm.pop(key, None)
        fm.pop("title", None)  # captured-file basename / fetched page name
        fm.pop("description", None)  # capture note
        heading = str(fm.get("id") or path.stem)
        body = f"# {heading}\n\n{WITHHELD_NOTE}\n"
    pages.write_page(path, fm, body)


def _write_stripped_refs_index(refs: Path) -> None:
    """Regenerate references/index.md from the stripped pages: id as label,
    the grade as description. The listing copied from the notebook carries
    titles and capture notes, which stripped mode withholds."""
    lines = ["# References", ""]
    for page_path in sorted(refs.glob("*.md")):
        if page_path.name in pages.RESERVED or page_path.name.startswith("_"):
            continue
        fm = pages.read_page(page_path).fm
        label = str(fm.get("id") or page_path.stem)
        line = f"* [{label}]({page_path.stem}.md)"
        grade = fm.get("grade")
        if grade:
            line += f" - grade {grade}"
        lines.append(line)
    (refs / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _drop_log_listing(index_path: Path) -> None:
    """Remove the Update Log bullet from the copied root listing: log.md does
    not ship when the trail is withheld, so its entry must not either. A
    text-level line filter — the manifest frontmatter stays byte-identical."""
    text = index_path.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if "](log.md)" not in line]
    new_text = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
    if new_text != text:
        index_path.write_text(new_text, encoding="utf-8")


def export_okf(
    root: Path,
    dest: Path,
    include_private: bool = False,
    announce: Path | None = None,
) -> Path:
    """Copy the notebook to `dest` as an outside-facing OKF bundle.

    Refuses unless the manifest's visibility is "public" or `include_private`
    is set. With the full trail (include_private or source_trail_public) the
    sources/ and log/ trees ship wholesale and reference pages gain fixity
    keys; without it, custody detail — raw bytes, ledgers, log.md, capture
    notes and titles on reference pages — is withheld. Regenerates `dest` in
    full; an existing `dest` is replaced only if it is a previous flip export.
    """
    root = Path(root)
    dest = Path(dest)
    m = load_manifest(root)  # validates the notebook root first
    visibility = m.policy.get("visibility", "internal")
    if visibility != "public" and not include_private:
        raise SystemExit(
            f"notebook visibility is '{visibility}'; OKF export is a render for outside "
            "consumption — set visibility: public in the root index.md or pass "
            "--include-private"
        )
    full_trail = include_private or bool(m.policy.get("source_trail_public", False))

    _regenerate_views(root)

    files = _payload_files(root, dest, full_trail)
    if dest.exists():
        if not (dest / STATE_FILE).is_file():
            raise SystemExit(
                f"{dest} exists and is not a previous flip OKF export; "
                "pick a fresh destination or remove it"
            )
        shutil.rmtree(dest)  # regenerate: the bundle is a render, never precious
    dest.mkdir(parents=True)

    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)

    prov = _provenance_by_source(root) if full_trail else {}
    refs = dest / "references"
    if refs.is_dir():
        for page_path in sorted(refs.glob("*.md")):
            if page_path.name in pages.RESERVED:
                continue  # the generated listing is handled below
            _filter_reference_page(page_path, prov, full_trail)
        if not full_trail and (refs / "index.md").is_file():
            _write_stripped_refs_index(refs)
    if not full_trail:
        _drop_log_listing(dest / "index.md")

    generated_at = utc_now()
    (dest / STATE_FILE).write_text(
        json.dumps(
            {"generated_at": generated_at, "tool": f"flip {__version__}", "notebook": m.slug},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if announce is not None:
        _announce(announce, dest, m.slug)
    return dest


def _announce(agents_md: Path, bundle: Path, slug: str) -> None:
    """Append (or replace) the FLIP marker block in an AGENTS.md, pointing agents
    at the bundle's root index — the same idiom OpenWiki uses, different marker."""
    try:
        rel = bundle.resolve().relative_to(agents_md.resolve().parent)
        pointer = str(rel / "index.md")
    except ValueError:
        pointer = str(bundle.resolve() / "index.md")
    block = (
        f"{MARKER_START}\n"
        f"This repository contains an OKF knowledge bundle exported from the flip "
        f"notebook `{slug}`. Start at [{pointer}]({pointer}) and follow links; the "
        f"bundle is generated — do not edit it by hand (edit the notebook and "
        f"re-export instead).\n"
        f"{MARKER_END}\n"
    )
    if agents_md.exists():
        text = agents_md.read_text(encoding="utf-8")
        if MARKER_START in text and MARKER_END in text:
            pre = text.split(MARKER_START)[0]
            post = text.split(MARKER_END, 1)[1]
            agents_md.write_text(pre + block + post, encoding="utf-8")
        else:
            agents_md.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    else:
        agents_md.write_text(block, encoding="utf-8")
