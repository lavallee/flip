"""`flip rename` — the only sanctioned way to change an entity slug (SPEC §9).

Filenames are human slugs; the compact id in frontmatter is immutable. So a
rename is a file move plus a notebook-wide link rewrite: every flip-generated
edge that pointed at the old filename — relative markdown links in page
bodies (`../references/<slug>.md`), bundle-absolute links, and the bundle
paths claims carry in `supports` (`/references/<slug>`) — is rewritten to the
new slug, and the generated listings are refreshed. Ids, aliases, and the
page's own content never change, so `[A3]`-style cites keep resolving.

Rewrites are textual and resolution-checked: a markdown link is only touched
when it actually resolves to the renamed file, so a same-named page in a
different directory is never caught by accident. Custody and derivation
trees (sources/, derived/) are never edited — captured bytes stay verbatim.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import manifest, pages, util, views

# Entity slugs (SPEC §3 naming rules): lowercase, digits, dashes.
ENTITY_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Directory components never scanned for links: custody bytes and derivations
# are verbatim (SPEC §5.1); renders are disposable; the rest is tooling noise.
_PRUNE = {"sources", "derived", "renders", "node_modules", "__pycache__"}

# A markdown link target, with an optional quoted title after it:
# [text](../references/x.md) or [text](../references/x.md "Title").
_MD_LINK_RE = re.compile(r"\]\(([^)\s]+)(\s+(?:\"[^\"]*\"|'[^']*'))?\)")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:")


def rename_entity(root: Path, entity_id: str, new_slug: str) -> tuple[Path, Path, int]:
    """Rename the page carrying `entity_id` to `<new_slug>.md`, rewriting every
    link to it notebook-wide. Returns (old path, new path, files rewritten).
    """
    root = util.require_notebook_root(root)
    if not ENTITY_SLUG_RE.match(new_slug or ""):
        raise SystemExit(
            f"invalid slug {new_slug!r}: entity slugs use lowercase letters, digits, "
            "and dashes (starting with a letter or digit), e.g. lecun-jepa-keynote"
        )
    if f"{new_slug}.md" in pages.RESERVED:
        raise SystemExit(
            f"'{new_slug}' is an OKF reserved name (index/log) and can't name an entity page"
        )
    page = pages.find_by_id(root, entity_id)
    if page is None:
        known = sorted(
            {p.id for d in pages.SCAN_DIRS for p in pages.iter_pages(root, d) if p.id},
            key=lambda s: (s.rstrip("0123456789"), len(s), s),
        )
        hint = f"known ids: {', '.join(known)}" if known else "no entity pages yet"
        raise SystemExit(f"no page with id '{entity_id}' ({hint}); `flip open <id>` resolves ids")
    old_path = page.path
    new_path = old_path.parent / f"{new_slug}.md"
    if new_path == old_path:
        raise SystemExit(f"{entity_id} is already named {new_slug}.md; nothing to do")
    if new_path.exists():
        raise SystemExit(
            f"{new_path.relative_to(root).as_posix()} already exists; pick a different slug"
        )
    old_path.rename(new_path)
    changed = _rewrite_links(root, old_path, new_path)
    manifest.touch_updated(root)
    views.regenerate(root)  # listings and the root body pick up the new slug
    return old_path, new_path, changed


def _md_files(root: Path) -> list[Path]:
    """Every markdown file that may carry flip-generated links: entity pages,
    analysis/, drafts/, notebook.md/HANDOFF.md/…; pruned trees skipped."""
    out = []
    for path in sorted(root.rglob("*.md")):
        parts = path.relative_to(root).parts
        if any(p in _PRUNE or p.startswith(".") for p in parts[:-1]):
            continue
        out.append(path)
    return out


def _rewrite_links(root: Path, old_path: Path, new_path: Path) -> int:
    """Rewrite links to `old_path` across the notebook; returns files changed.

    Two edge forms exist (SPEC §7, §9): relative/bundle-absolute markdown
    links ending in `<old slug>.md` (rewritten only when they resolve to the
    renamed file), and extensionless bundle paths `/dir/<old slug>` as used by
    claims' `supports` frontmatter (matched with the directory attached, so a
    same-named page elsewhere is untouched).
    """
    dirname = old_path.parent.name
    old_norm = os.path.normpath(old_path)
    supports_re = re.compile(
        re.escape(f"/{dirname}/{old_path.stem}") + r"(?![A-Za-z0-9._-])"
    )

    def _sub_link(match: re.Match, md_file: Path) -> str:
        target = match.group(1)
        title = match.group(2) or ""  # optional quoted link title, preserved
        base, sep, frag = target.partition("#")
        if not base.endswith(".md") or _SCHEME_RE.match(base):
            return match.group(0)
        anchor = root / base.lstrip("/") if base.startswith("/") else md_file.parent / base
        if os.path.normpath(anchor) != old_norm:
            return match.group(0)
        return "](" + base[: -len(old_path.name)] + new_path.name + sep + frag + title + ")"

    changed = 0
    for md_file in _md_files(root):
        text = md_file.read_text(encoding="utf-8")
        new_text = _MD_LINK_RE.sub(lambda m: _sub_link(m, md_file), text)
        new_text = supports_re.sub(f"/{dirname}/{new_path.stem}", new_text)
        if new_text != text:
            md_file.write_text(new_text, encoding="utf-8")
            changed += 1
    return changed
