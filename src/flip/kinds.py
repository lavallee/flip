"""flip kind registry — Phase 1 outcome layer (design-outcome-kinds.md).

A *kind* names a desired output ("a lit review," "a decision packet") and
brings a `[contract]` — the requirements a finished notebook of that shape
must satisfy — plus optional `[workflow]` phases and `[versioning]` mode.
This is the "outcome mode" half of the Constitution's two entry modes (S1):
say what you're making, get pointed at a process, without anyone hand-wiring
a discipline stack.

Kinds load from three places, later winning on id collision:

1. **built-in** — shipped under ``src/flip/kinds_builtin/*.toml``.
2. **user** — ``$FLIP_HOME/kinds/`` (per-user, across every notebook).
3. **notebook** — ``<notebook>/.flip/kinds/`` (this notebook only).

Each of the last two accepts either a single file (``<id>.toml``) or a
directory (``<id>/kind.toml``) — the loader treats both identically (S2: the
minimum viable kind is one small file, but multi-file is legitimate from day
one). No registration step: drop a file in and `flip kind list` sees it.

Today's `flip new --kind <profile>` profiles (scout, ledger, …) are *also*
surfaced here as kinds — thin read-only adapters over `profiles.py`, never
duplicating their content — so kinds and profiles are one axis, not two.
This module is additive: it does not touch `flip new`'s existing profile
resolution path.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from . import pages as pages_mod
from . import profiles as profiles_mod
from .manifest import load_manifest, save_manifest
from .registry import flip_home
from .util import append_jsonl, detect_actor, today, utc_now

# Kind ids match the same shape as notebook slugs / profile ids: lowercase,
# hyphenated, starting with a letter — filesystem- and TOML-key-safe.
KIND_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Where a contract requirement's `entity` can count pages from — the entity
# dirs flip already scans (SPEC §9), plus "files" for a plain path/glob check
# against the notebook root (a required sibling file, e.g. criteria.md).
ENTITY_DIRS = ("references", "claims", "questions", "decisions", "sessions")
ENTITY_KINDS = (*ENTITY_DIRS, "files")

ORIGINS = ("built-in", "user", "notebook", "profile")


@dataclass
class ContractRequirement:
    """One `[[contract.require]]` entry: a single, doctor-checkable ask.

    `assembled_by` is required (design-outcome-kinds.md: "a field no render
    needs is doctor-findable cargo cult") — every requirement must name the
    render/output section that actually consumes it.
    """

    id: str
    what: str = ""
    entity: str | None = None
    field: str | None = None  # dotted frontmatter path within `entity`'s pages
    path: str | None = None  # relative path/glob, only meaningful for entity="files"
    min: int = 1
    assembled_by: str = ""
    prospective: bool = False  # true: cannot be honestly backfilled once adopted late


@dataclass
class Kind:
    id: str
    version: str = "0.1"
    summary: str = ""
    source_path: Path | None = None
    origin: str = "built-in"  # "built-in" | "user" | "notebook" | "profile"
    defaults: dict = field(default_factory=dict)  # manifest keys, e.g. visibility
    contract: list[ContractRequirement] = field(default_factory=list)
    workflow: list[dict] | None = None
    versioning: dict | None = None
    raw: dict = field(default_factory=dict)  # the full parsed TOML


@dataclass
class GapRow:
    """One line of a `flip kind adopt` gap manifest: what a requirement
    needs, what exists, and the three-tier honesty label for the shortfall."""

    requirement_id: str
    what: str
    have: int
    min: int
    tier: str  # "met" | "recoverable" | "reconstructible-with-loss" | "unrecoverable-by-construction"
    assembled_by: str
    prospective: bool


# --- parsing -----------------------------------------------------------------


def _parse_requirement(entry: dict, kind_id: str) -> ContractRequirement:
    rid = entry.get("id")
    if not rid:
        raise SystemExit(f"kind '{kind_id}': a [[contract.require]] entry is missing 'id'")
    assembled_by = entry.get("assembled_by")
    if not assembled_by:
        raise SystemExit(
            f"kind '{kind_id}': contract requirement '{rid}' has no assembled_by — "
            "every requirement must name the render/output section that needs it "
            "(a field no render needs is doctor-findable cargo cult); add "
            f'assembled_by = "..." to it'
        )
    entity = entry.get("entity")
    field_path = entry.get("field")
    if field_path and not entity:
        # "references.support.basis" style: the first segment names the entity.
        head, _, rest = str(field_path).partition(".")
        entity, field_path = head, (rest or None)
    if entity is not None and entity not in ENTITY_KINDS:
        raise SystemExit(
            f"kind '{kind_id}': requirement '{rid}' has unknown entity '{entity}' "
            f"(one of: {', '.join(ENTITY_KINDS)})"
        )
    return ContractRequirement(
        id=str(rid),
        what=str(entry.get("what", "")),
        entity=entity,
        field=field_path,
        path=entry.get("path"),
        min=int(entry.get("min", 1)),
        assembled_by=str(assembled_by),
        prospective=bool(entry.get("prospective", False)),
    )


def _kind_from_toml(text: str, source_path: Path | None, origin: str) -> Kind:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{source_path}: invalid kind TOML: {e}") from None
    kind_id = data.get("id")
    if not kind_id:
        raise SystemExit(f"{source_path}: kind file is missing required key 'id'")
    contract_table = data.get("contract") or {}
    requires = [_parse_requirement(e, kind_id) for e in contract_table.get("require", [])]
    workflow_table = data.get("workflow") or {}
    workflow = workflow_table.get("phase") if isinstance(workflow_table, dict) else None
    return Kind(
        id=str(kind_id),
        version=str(data.get("version", "0.1")),
        summary=str(data.get("summary") or "").strip(),
        source_path=source_path,
        origin=origin,
        defaults=dict(data.get("defaults") or {}),
        contract=requires,
        workflow=workflow,
        versioning=data.get("versioning"),
        raw=data,
    )


def _scan_kind_source(directory, origin: str) -> dict[str, Kind]:
    """Load every kind from one directory-like root (a Path or an
    importlib.resources Traversable): single-file (<id>.toml) and directory
    (<id>/kind.toml) forms, treated identically."""
    out: dict[str, Kind] = {}
    try:
        is_dir = directory.is_dir()
    except OSError:
        is_dir = False
    if not is_dir:
        return out
    for entry in sorted(directory.iterdir(), key=lambda e: e.name):
        if entry.is_file() and entry.name.endswith(".toml"):
            text = entry.read_text(encoding="utf-8")
            source = entry if isinstance(entry, Path) else Path(str(entry))
            k = _kind_from_toml(text, source, origin)
            out[k.id] = k
        elif entry.is_dir():
            kind_toml = entry / "kind.toml"
            if kind_toml.is_file():
                text = kind_toml.read_text(encoding="utf-8")
                source = kind_toml if isinstance(kind_toml, Path) else Path(str(kind_toml))
                k = _kind_from_toml(text, source, origin)
                out[k.id] = k
    return out


def _builtin_dir():
    return resources.files("flip") / "kinds_builtin"


def _user_dir() -> Path:
    return flip_home() / "kinds"


def _notebook_dir(root: Path) -> Path:
    return root / ".flip" / "kinds"


def _load_all(root: Path | None) -> dict[str, Kind]:
    merged: dict[str, Kind] = {}
    merged.update(_scan_kind_source(_builtin_dir(), "built-in"))
    merged.update(_scan_kind_source(_user_dir(), "user"))
    if root is not None:
        merged.update(_scan_kind_source(_notebook_dir(root), "notebook"))
    # Today's profiles, surfaced as rigor-shaped kinds with empty contracts —
    # a thin adapter, never overriding an actual kind file of the same id.
    for pid in profiles_mod.list_profiles():
        if pid in merged:
            continue
        prof = profiles_mod.load_profile(pid, root)
        merged[pid] = Kind(
            id=pid,
            version="",
            summary=prof.description,
            source_path=None,
            origin="profile",
            defaults={},
            contract=[],
            workflow=None,
            versioning=None,
            raw={},
        )
    return merged


def list_kinds(root: Path | None = None) -> list[Kind]:
    """Every kind visible from `root` (or just built-ins/user/profiles when
    root is None): built-ins, $FLIP_HOME/kinds/, notebook-local, and today's
    profiles — sorted by id."""
    return sorted(_load_all(root).values(), key=lambda k: k.id)


def load_kind(kind_id: str, root: Path | None = None) -> Kind:
    """Resolve one kind id, or refuse with the list of known ids."""
    kinds = _load_all(root)
    if kind_id not in kinds:
        raise SystemExit(
            f"unknown kind '{kind_id}'; known: {', '.join(sorted(kinds)) or '(none)'} "
            "(`flip kind list` for details, `flip kind new <id>` to scaffold one)"
        )
    return kinds[kind_id]


def kind_exists(kind_id: str, root: Path | None = None) -> bool:
    return kind_id in _load_all(root)


# --- gap manifest --------------------------------------------------------------


def _dotted_get(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _requirement_status(root: Path, req: ContractRequirement) -> tuple[int, int]:
    """(satisfying_count, total_existing_count) for one requirement.

    The two counts diverge only when `field` is set and some already-existing
    pages of that entity lack it — the shortfall that can be filled in but
    never contemporaneously (the reconstructible-with-loss case).
    """
    if req.entity == "files":
        pattern = req.path or req.field
        if not pattern:
            return 0, 0
        if any(ch in pattern for ch in "*?["):
            n = sum(1 for _ in root.glob(pattern))
            return n, n
        exists = 1 if (root / pattern).exists() else 0
        return exists, exists
    if req.entity not in ENTITY_DIRS:
        return 0, 0  # not automatically checkable — never counted as a gap we can size
    found, _errors = pages_mod.iter_pages_tolerant(root, req.entity)
    total = len(found)
    if not req.field:
        return total, total
    satisfying = sum(1 for p in found if _dotted_get(p.fm, req.field) not in (None, "", "?"))
    return satisfying, total


def gap_manifest(root: Path, kind: Kind) -> list[GapRow]:
    """One GapRow per contract requirement, tiered per the three-way honesty
    vocabulary (design-outcome-kinds.md, Phase 1 item 3):

    - **met** — the requirement is already satisfied.
    - **recoverable** — nothing exists yet for it; add it now, dated now,
      with no contemporaneity problem.
    - **reconstructible-with-loss** — pages of that entity already exist
      without the required field; filling it in now cannot be contemporaneous
      with when the work actually happened.
    - **unrecoverable-by-construction** — `prospective` requirements
      (frozen-before-looking asks) that were never captured; adopting the
      kind late means this one is gone for good.
    """
    rows = []
    for req in kind.contract:
        satisfying, total = _requirement_status(root, req)
        met = satisfying >= req.min
        if met:
            tier = "met"
        elif req.prospective:
            tier = "unrecoverable-by-construction"
        elif req.field and total > satisfying:
            tier = "reconstructible-with-loss"
        else:
            tier = "recoverable"
        rows.append(
            GapRow(
                requirement_id=req.id,
                what=req.what,
                have=satisfying,
                min=req.min,
                tier=tier,
                assembled_by=req.assembled_by,
                prospective=req.prospective,
            )
        )
    return rows


# --- adopt ---------------------------------------------------------------------


def adopt_kind(root: Path, kind_id: str) -> tuple[Kind, list[GapRow]]:
    """Adopt a kind onto an existing notebook: set manifest.kind, apply the
    kind's manifest defaults, log a crystallization event, and return the gap
    manifest. Refuses (via load_kind) if `kind_id` is unknown."""
    kind = load_kind(kind_id, root)
    manifest = load_manifest(root)
    manifest.kind = kind.id
    for key, value in kind.defaults.items():
        if hasattr(manifest, key):
            setattr(manifest, key, value)
    manifest.updated = today()
    save_manifest(root, manifest)
    append_jsonl(
        root / "log" / "log.jsonl",
        {"ts": utc_now(), "text": f"kind-adopt {kind.id}", "actor": detect_actor()},
    )
    return kind, gap_manifest(root, kind)


# --- flip kind new: scaffold a user kind file -----------------------------------

KIND_TEMPLATE = '''\
# {id} — a flip kind: "I am making a ___"
#
# This file IS the documentation: every key below is explained in place with
# a safe default. A kind with just id/version/summary/[defaults] is legal —
# everything else is opt-in. Loaded from $FLIP_HOME/kinds/{id}.toml (or a
# {id}/kind.toml directory, if you outgrow one file — same schema, either way).

id      = "{id}"
version = "0.1"

# One paragraph, outcome-first: what does a finished one of these look like,
# and what failure is it defending against? Plain language a domain expert
# would use describing their own process — no genre/discipline/slot words.
summary = """
Describe the outcome here: what it is, and what it protects against.
"""

# Manifest fields this kind sets when adopted (`flip kind adopt {id}`).
# Only keys the manifest already knows apply: visibility, renders_public,
# source_trail_public, citation_rule. Delete this table if you need none.
[defaults]
# visibility = "internal"

# Requirements a finished notebook of this kind must satisfy — each one is
# independently checkable by `flip doctor` (code kind-gap) and printed as a
# line in `flip kind adopt`'s gap manifest. Delete this example and write
# your own: at least one requirement is what makes a kind more than a label.
[[contract.require]]
id           = "example-requirement"  # short, stable — cited in doctor findings
what         = "Plain-language description of what must exist, and why."
entity       = "references"           # references|claims|questions|decisions|sessions|files
# field      = "support.basis"        # optional: a dotted frontmatter path to
                                       # check for a non-empty value on each
                                       # page of `entity`; omit to just count
                                       # pages. For entity = "files", set
                                       # `path` (below) to a relative path or
                                       # glob instead of `field`.
# path       = "criteria.md"
min          = 1                      # how many must satisfy it
assembled_by = "some-render-or-section"  # REQUIRED: the render/output section
                                       # that actually needs this — a field no
                                       # render needs is doctor-findable cargo
                                       # cult. Name a real one.
prospective  = false                  # true only if this can never be
                                       # honestly captured after the fact
                                       # (e.g. criteria frozen before looking);
                                       # adopting late then marks it
                                       # unrecoverable-by-construction, not a
                                       # WARN to silence.

# Optional named phases, each naming what it produces (dormant until you have
# more than one worth naming — delete if you don't).
# [[workflow.phase]]
# id       = "search"
# produces = "a dated search log"

# Optional: how this kind treats time. mode = "one-shot" (default — delete
# this table if that's you) | "living" (revisited on a schedule/trigger) |
# "editions".
# [versioning]
# mode = "one-shot"
'''


def scaffold_kind(kind_id: str, force: bool = False) -> Path:
    """Write $FLIP_HOME/kinds/<id>.toml from the commented template."""
    if not KIND_ID_RE.match(kind_id or ""):
        raise SystemExit(
            f"invalid kind id {kind_id!r}: use lowercase letters, digits, and hyphens, "
            "starting with a letter (e.g. swot-brief)"
        )
    path = _user_dir() / f"{kind_id}.toml"
    if path.exists() and not force:
        raise SystemExit(
            f"{path} already exists — edit it directly, or pass --force to overwrite"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(KIND_TEMPLATE.format(id=kind_id), encoding="utf-8")
    return path
