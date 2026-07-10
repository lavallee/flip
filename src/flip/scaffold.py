"""Scaffolding for `flip new`: root index.md manifest + notebook.md stubs.

Creates exactly two files — index.md (the OKF bundle root carrying the flip
manifest frontmatter, SPEC §4) and notebook.md (the prose heart, an OKF
concept page with `type: Notebook`). Everything else (sources/, log/,
references/, …) appears lazily when first needed (SPEC §3): empty structure
is worse than absent structure.
"""

from __future__ import annotations

from pathlib import Path

from . import pages, views
from .manifest import (
    DEFAULT_POLICY,
    VISIBILITIES,
    Manifest,
    require_valid_slug,
    save_manifest,
)
from .profiles import SECTIONS, Profile, load_profile
from .util import ROOT_FILE, today

NOTEBOOK_MD = "notebook.md"


def _notebook_md_body(name: str, profile: Profile) -> str:
    """Render the notebook.md body: a title line, then one stub per profile
    section — heading plus the prompt as a blockquote the author replaces
    (prompts are prompts, not a form; SPEC §13)."""
    parts = [f"# Reporter's notebook — {name}\n"]
    for section in profile.sections:
        spec = SECTIONS[section]
        parts.append(f"\n## {spec['heading']}\n\n> {spec['prompt']}\n")
    return "".join(parts)


def create_notebook(
    dest: Path,
    slug: str,
    kind: str,
    title: str = "",
    visibility: str | None = None,
) -> Path:
    """Create a notebook at `dest`: index.md + notebook.md, nothing else.

    Policy starts at the Manifest defaults, overlaid with the profile's
    forced_policy, then the explicit `visibility` argument if given. All
    validation runs before mkdir, so a bad call creates nothing. Returns
    `dest`.
    """
    if (dest / ROOT_FILE).exists():
        raise SystemExit(
            f"{dest} already contains {ROOT_FILE}; work in that notebook or "
            f"pick a different directory"
        )
    require_valid_slug(slug)  # before mkdir: a bad slug creates nothing
    profile = load_profile(kind)  # SystemExit with shipped kinds if unknown
    if visibility is not None and visibility not in VISIBILITIES:
        raise SystemExit(
            f"invalid visibility '{visibility}' (one of: {', '.join(VISIBILITIES)})"
        )
    m = Manifest(slug=slug, title=title, kind=kind, created=today(), updated=today())
    for key, value in profile.forced_policy.items():
        if key in DEFAULT_POLICY:
            setattr(m, key, value)
    if visibility is not None:
        m.visibility = visibility

    dest.mkdir(parents=True, exist_ok=True)
    save_manifest(dest, m)
    name = title or slug
    pages.write_page(
        dest / NOTEBOOK_MD,
        {"type": "Notebook", "description": name},
        _notebook_md_body(name, profile),
    )
    views.regenerate(dest)
    return dest
