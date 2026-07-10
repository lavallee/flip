"""Scaffolding for `flip new`: manifest + notebook.md section stubs.

Creates exactly two files — notebook.toml and notebook.md. Everything else
(sources/, log/, analysis/, …) appears lazily when first needed (SPEC §3):
empty structure is worse than absent structure.
"""

from __future__ import annotations

from pathlib import Path

from .manifest import (
    DEFAULT_POLICY,
    VISIBILITIES,
    Manifest,
    require_valid_slug,
    save_manifest,
)
from .profiles import SECTIONS, Profile, load_profile
from .util import MANIFEST, today

NOTEBOOK_MD = "notebook.md"


def _render_notebook_md(name: str, profile: Profile) -> str:
    """Render the notebook.md scaffold: a title line, then one stub per
    profile section — heading plus the prompt as a blockquote the author
    replaces (prompts are prompts, not a form; SPEC §7.1)."""
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
    """Create a notebook at `dest`: notebook.toml + notebook.md, nothing else.

    Policy = DEFAULT_POLICY overlaid with the profile's forced_policy, then
    the explicit `visibility` argument if given. Returns `dest`.
    """
    if (dest / MANIFEST).exists():
        raise SystemExit(
            f"{dest} already contains {MANIFEST}; work in that notebook or "
            f"pick a different directory"
        )
    require_valid_slug(slug)  # before mkdir: a bad slug creates nothing
    profile = load_profile(kind)  # SystemExit with shipped kinds if unknown
    if visibility is not None and visibility not in VISIBILITIES:
        raise SystemExit(
            f"invalid visibility '{visibility}' (one of: {', '.join(VISIBILITIES)})"
        )
    policy = {**DEFAULT_POLICY, **profile.forced_policy}
    if visibility is not None:
        policy["visibility"] = visibility

    dest.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(
        slug=slug,
        title=title,
        kind=kind,
        created=today(),
        updated=today(),
        policy=policy,
    )
    save_manifest(dest, manifest)
    (dest / NOTEBOOK_MD).write_text(
        _render_notebook_md(title or slug, profile), encoding="utf-8"
    )
    return dest
