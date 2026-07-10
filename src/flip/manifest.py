"""notebook.toml read/write (SPEC §4).

TOML is read with stdlib tomllib and written by template so flip carries no
TOML-writer dependency. `save_manifest` re-renders the whole file: manifests
are small and flip owns every field it writes; hand-added comments do not
survive a rewrite, which is why judgments live in ledgers, not the manifest.
Unknown keys and tables DO survive: anything flip doesn't recognize is
collected into `Manifest.extras` at load and rendered back at save, so a
hand-added `description` or `[beat]` table isn't dropped by the first
mutating command.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .util import MANIFEST, today

VISIBILITIES = ("private", "internal", "client-confidential", "public")
STATUSES = ("active", "dormant", "done", "published", "archived")

# SPEC §3: slugs are filesystem- and cite-safe. Validated at create/save so a
# bad slug never reaches disk (a quote or newline would break the TOML and
# every <slug>#<id> cross-reference).
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

_KNOWN_SCALARS = {"slug", "title", "kind", "status", "created", "updated", "host"}
_KNOWN_TABLES = {"policy", "links", "tools"}


@dataclass
class Manifest:
    slug: str
    title: str = ""
    kind: str = "ledger"
    status: str = "active"
    created: str = ""
    updated: str = ""
    host: str = ""  # set only for detached notebooks (SPEC §3)
    policy: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    tools: dict = field(default_factory=dict)
    # Unknown top-level keys and tables, preserved verbatim across a
    # load/save round-trip (insertion order kept).
    extras: dict = field(default_factory=dict)

    def policy_get(self, key: str, default=None):
        return self.policy.get(key, default)


DEFAULT_POLICY = {
    "visibility": "internal",
    "renders_public": False,
    "source_trail_public": False,
    "citation_rule": "public-terminus",
}


def load_manifest(root: Path) -> Manifest:
    path = root / MANIFEST
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"no {MANIFEST} in {root}") from None
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{path}: invalid TOML: {e}") from None
    if not isinstance(data.get("slug"), str) or not data["slug"]:
        raise SystemExit(f"{path}: missing required field 'slug'; add e.g. slug = \"my-notebook\"")
    top = {k: v for k, v in data.items() if k in _KNOWN_SCALARS}
    extras = {k: v for k, v in data.items() if k not in _KNOWN_SCALARS | _KNOWN_TABLES}
    return Manifest(
        **top,
        policy=data.get("policy", {}),
        links=data.get("links", {}),
        tools=data.get("tools", {}),
        extras=extras,
    )


# TOML basic-string escapes (TOML 1.0 §String): the named ones, then \uXXXX
# for every other control character.
_STR_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}

_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _escape_str(s: str) -> str:
    out = []
    for ch in s:
        if ch in _STR_ESCAPES:
            out.append(_STR_ESCAPES[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return "".join(out)


def _toml_key(k: str) -> str:
    return k if _BARE_KEY_RE.match(k) else f'"{_escape_str(k)}"'


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):  # nested table value → inline table
        return "{ " + ", ".join(f"{_toml_key(k)} = {_toml_value(x)}" for k, x in v.items()) + " }"
    return f'"{_escape_str(str(v))}"'


def _render_table(name: str, table: dict) -> str:
    if not table:
        return ""
    lines = [f"[{_toml_key(name)}]"]
    for k, v in table.items():
        lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def render_manifest(m: Manifest) -> str:
    head = [f"slug = {_toml_value(m.slug)}"]
    if m.title:
        head.append(f"title = {_toml_value(m.title)}")
    head.append(f"kind = {_toml_value(m.kind)}")
    if m.host:
        head.append(f"host = {_toml_value(m.host)}")
    head.append(f"status = {_toml_value(m.status)}")
    head.append(f"created = {_toml_value(m.created or today())}")
    head.append(f"updated = {_toml_value(m.updated or today())}")
    extra_tables: dict[str, dict] = {}
    for k, v in m.extras.items():
        if isinstance(v, dict):
            extra_tables[k] = v  # unknown table → its own [table]
        else:
            head.append(f"{_toml_key(k)} = {_toml_value(v)}")  # unknown scalar/list
    parts = ["\n".join(head) + "\n"]
    for name, table in (("policy", m.policy), ("links", m.links), ("tools", m.tools)):
        rendered = _render_table(name, table)
        if rendered:
            parts.append(rendered)
    for name, table in extra_tables.items():
        rendered = _render_table(name, table)
        if rendered:
            parts.append(rendered)
    return "\n".join(parts)


def require_valid_slug(slug: object) -> str:
    """Validate a slug at create/save time; SystemExit with the rule if bad."""
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise SystemExit(
            f"invalid slug {slug!r}: use lowercase letters, digits, and ._- "
            "(starting with a letter or digit), e.g. 'nj-schools'"
        )
    return slug


def save_manifest(root: Path, m: Manifest) -> None:
    require_valid_slug(m.slug)
    if m.status not in STATUSES:
        raise SystemExit(f"invalid status '{m.status}' (one of: {', '.join(STATUSES)})")
    vis = m.policy.get("visibility")
    if vis is not None and vis not in VISIBILITIES:
        raise SystemExit(f"invalid visibility '{vis}' (one of: {', '.join(VISIBILITIES)})")
    (root / MANIFEST).write_text(render_manifest(m), encoding="utf-8")


def touch_updated(root: Path) -> None:
    """Refresh `updated` to today; called by every mutating command."""
    m = load_manifest(root)
    if m.updated != today():
        m.updated = today()
        save_manifest(root, m)
