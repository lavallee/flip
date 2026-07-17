"""The manifest — flip identity in the root index.md frontmatter (SPEC §4).

OKF sanctions frontmatter on exactly one index: the bundle root. That is
where a notebook's identity, status, and policy live — visible to any OKF
consumer, editable as properties in Obsidian-style tools, preserved key-for-
key on rewrite. The index *body* is a generated directory listing owned by
views; save_manifest touches only the frontmatter and keeps the body as-is.

Unknown frontmatter keys survive: anything flip doesn't recognize is
collected into `Manifest.extras` at load and re-emitted at save (SPEC §6.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import pages
from .util import ROOT_FILE, today

VISIBILITIES = ("private", "internal", "client-confidential", "public")
STATUSES = ("active", "dormant", "done", "published", "archived")
FLIP_PROFILE_VERSION = "0.5"

# SPEC §3: slugs are filesystem- and cite-safe. Validated at create/save so a
# bad slug never reaches disk (it names files and every <slug>:<id> cross-ref).
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Manifest keys flip owns, in canonical frontmatter order.
KNOWN_KEYS = (
    "okf_version", "flip", "slug", "uid", "title", "kind", "status", "created",
    "updated", "host", "origin", "visibility", "renders_public",
    "source_trail_public", "citation_rule", "links", "relations", "consumers",
    "tools",
)

DEFAULT_POLICY = {
    "visibility": "internal",
    "renders_public": False,
    "source_trail_public": False,
    "citation_rule": "public-terminus",
}


@dataclass
class Manifest:
    slug: str
    uid: str = ""  # stable machine identity; travels with the bundle (SPEC §4)
    title: str = ""
    kind: str = "ledger"
    status: str = "active"
    created: str = ""
    updated: str = ""
    host: str = ""  # set only for detached notebooks (SPEC §3)
    origin: str = ""  # provenance of an imported copy, written by `flip import`
    visibility: str = DEFAULT_POLICY["visibility"]
    renders_public: bool = DEFAULT_POLICY["renders_public"]
    source_trail_public: bool = DEFAULT_POLICY["source_trail_public"]
    citation_rule: str = DEFAULT_POLICY["citation_rule"]
    links: dict = field(default_factory=dict)
    relations: list = field(default_factory=list)
    consumers: list = field(default_factory=list)
    tools: dict = field(default_factory=dict)
    # Unknown frontmatter keys, preserved verbatim across load/save.
    extras: dict = field(default_factory=dict)
    # The `flip:` profile version as declared on disk at load time. Read-only
    # context for doctor (missing-uid is gated to 0.5+); save always stamps
    # FLIP_PROFILE_VERSION, never this.
    flip_version: str = ""

    @property
    def policy(self) -> dict:
        """Policy fields as a dict — the shape doctor/export/okf consume."""
        return {
            "visibility": self.visibility,
            "renders_public": self.renders_public,
            "source_trail_public": self.source_trail_public,
            "citation_rule": self.citation_rule,
        }

    def policy_get(self, key: str, default=None):
        return self.policy.get(key, default)


def require_valid_slug(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        raise SystemExit(
            f"invalid slug {slug!r}: use lowercase letters, digits, and ._- "
            "(starting with a letter or digit), e.g. nj-schools"
        )
    return slug


def load_manifest(root: Path) -> Manifest:
    path = root / ROOT_FILE
    if not path.is_file():
        raise SystemExit(
            f"no {ROOT_FILE} in {root} — not a flip notebook root "
            "(run `flip new <slug>`, or `flip migrate` for a v0.3 notebook)"
        )
    fm = pages.read_page(path).fm
    if not isinstance(fm.get("slug"), str) or not fm["slug"]:
        raise SystemExit(
            f"{path}: frontmatter missing required key 'slug' — add e.g. slug: my-notebook"
        )
    m = Manifest(slug=fm["slug"])
    for key in ("uid", "title", "kind", "status", "created", "updated", "host",
                "origin", "visibility", "citation_rule"):
        if key in fm and fm[key] is not None:
            setattr(m, key, str(fm[key]))
    if fm.get("flip") is not None:
        m.flip_version = str(fm["flip"])
    for key in ("renders_public", "source_trail_public"):
        if key in fm:
            setattr(m, key, bool(fm[key]))
    m.extras = {k: v for k, v in fm.items() if k not in KNOWN_KEYS}
    # Known keys with foreign-typed values (tools: "a string", relations:
    # {a: map}, …) are never silently dropped: the typed field keeps its
    # default and the hand-authored value rides along in extras, re-emitted
    # verbatim under its own name on save (SPEC §6.6).
    for key, want in (("links", dict), ("tools", dict),
                      ("relations", list), ("consumers", list)):
        value = fm.get(key)
        if isinstance(value, want):
            setattr(m, key, value)
        elif key in fm and value is not None:
            m.extras[key] = value
    return m


def manifest_frontmatter(m: Manifest) -> dict:
    fm: dict = {"okf_version": "0.1", "flip": FLIP_PROFILE_VERSION, "slug": m.slug}
    if m.uid:
        fm["uid"] = m.uid
    if m.title:
        fm["title"] = m.title
    fm["kind"] = m.kind
    fm["status"] = m.status
    fm["created"] = m.created or today()
    fm["updated"] = m.updated or today()
    if m.host:
        fm["host"] = m.host
    if m.origin:
        fm["origin"] = m.origin
    fm["visibility"] = m.visibility
    fm["renders_public"] = m.renders_public
    fm["source_trail_public"] = m.source_trail_public
    fm["citation_rule"] = m.citation_rule
    for key, value in (("links", m.links), ("relations", m.relations),
                       ("consumers", m.consumers), ("tools", m.tools)):
        if value:
            fm[key] = value
    fm.update(m.extras)
    return fm


def save_manifest(root: Path, m: Manifest, body: str | None = None) -> None:
    """Rewrite the root index.md frontmatter; keep (or set) the body.

    The body is the generated listing owned by views — preserved byte-for-
    byte here; only the views layer replaces it. A brand-new notebook gets a
    minimal heading body.
    """
    require_valid_slug(m.slug)
    if m.status not in STATUSES:
        raise SystemExit(f"invalid status '{m.status}' (one of: {', '.join(STATUSES)})")
    if m.visibility not in VISIBILITIES:
        raise SystemExit(
            f"invalid visibility '{m.visibility}' (one of: {', '.join(VISIBILITIES)})"
        )
    path = root / ROOT_FILE
    if body is None:
        body = pages.read_page(path).body if path.is_file() else f"# {m.title or m.slug}\n"
    pages.write_page(path, manifest_frontmatter(m), body)


def touch_updated(root: Path) -> None:
    """Refresh `updated` to today; called by every mutating command."""
    m = load_manifest(root)
    if m.updated != today():
        m.updated = today()
        save_manifest(root, m)
