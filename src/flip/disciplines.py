"""flip discipline registry — Phase 3 composition layer (design-composition-0.14.md).

A *discipline* names a policy standard the work is held to ("lineage",
"forecasting", "systematic-screening") — distinct from a kind, which names
what you're making. A discipline declares the policy areas it owns
(``[[slot]]`` — the slot is the real partition, never the class), the bars
it applies (``[[gate]]`` — enforced gates block; attested gates record that
a third party already ran a verification flip cannot re-run), and its
advisory rubric (``[[check]]``).

Disciplines load from three places, later winning on id collision:

1. **built-in** — shipped under ``src/flip/disciplines_builtin/*.toml``.
2. **user** — ``$FLIP_HOME/disciplines/`` (per-user, across every notebook).
3. **notebook** — ``<notebook>/.flip/disciplines/`` (this notebook only).

Each of the last two accepts either a single file (``<id>.toml``) or a
directory (``<id>/discipline.toml``) — same loader philosophy as kinds.

Versioning policy (pinned at the 0.14 freeze): versions are ``MAJOR.MINOR``
strings. **1.x is reserved for self-descriptions of enforcement flip itself
guarantees** (lineage, forecasting — the checks exist in doctor and are
release-tested); **0.x marks authored disciplines whose content is still
earning its stability**. Manifest pins accept ``id@MAJOR`` (any minor — the
normal form) or ``id@MAJOR.MINOR`` (exact); files always carry the full
``MAJOR.MINOR``.

What a ``check`` may reference (decision C-C): an existing doctor finding
code (validated against ``doctor.CHECK_CODES``), or a simple field
predicate — ``{class, field, requires = "present"|"absent"|"one_of",
one_of?, message}`` — evaluated over the class's pages. No expression
language, ever.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from . import pages as pages_mod
from .registry import flip_home

# Discipline ids share the kind/slug shape: lowercase, hyphenated,
# starting with a letter — filesystem- and TOML-key-safe.
DISCIPLINE_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# The closed taxonomy (design-composition-0.14.md anatomy).
DISCIPLINE_KINDS = ("regime", "overlay", "frame", "frame-regime")

GATE_KINDS = ("enforced", "attested")

# The three field-predicate tests (decision C-C, Form B). Nothing else.
PREDICATE_REQUIRES = ("present", "absent", "one_of")

# A discipline version is always MAJOR.MINOR on disk.
VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")

# A manifest pin: id@MAJOR (any minor) or id@MAJOR.MINOR (exact).
PIN_RE = re.compile(r"^([a-z][a-z0-9-]*)@(\d+)(?:\.(\d+))?$")

ORIGINS = ("built-in", "user", "notebook")


@dataclass
class Slot:
    """One ``[[slot]]`` entry: a named policy area — the unit of ownership
    in composition. Two declared disciplines both owning one slot is a
    conflict the manifest must resolve; slots are open strings (C-B)."""

    id: str
    owns: bool = True


@dataclass
class Gate:
    """One ``[[gate]]`` entry. ``kind = "enforced"`` blocks (the owner's
    gates error); ``kind = "attested"`` records that a third party already
    ran a verification — never blocking, labeled when its check fails.
    ``check`` is a doctor finding code (str) or a field predicate (dict)."""

    id: str
    slot: str = ""
    kind: str = "enforced"
    check: str | dict = ""


@dataclass
class Discipline:
    id: str
    version: str = "0.1"
    summary: str = ""
    aka: list[str] = field(default_factory=list)
    kind: str = "regime"  # regime | overlay | frame | frame-regime
    governs: list[str] = field(default_factory=list)  # class ownership, coarse default
    slots: list[Slot] = field(default_factory=list)
    gates: list[Gate] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)  # advisory rubric entries
    vocabulary: dict = field(default_factory=dict)  # namespaced badges/terms
    depends_on: list[str] = field(default_factory=list)  # absent partner => WARN
    conflicts: list[dict] = field(default_factory=list)  # [{with, slot}]
    # Reserved (deferred round): parsed and carried, never enforced — so an
    # authored discipline isn't blocked from stating its corrections policy.
    corrections: dict = field(default_factory=dict)
    extends: str | None = None  # reserved for the monotone substrate case only
    origin: str = "built-in"  # "built-in" | "user" | "notebook"
    source_path: Path | None = None
    raw: dict = field(default_factory=dict)  # the full parsed TOML

    def claimed_codes(self) -> set[str]:
        """Every doctor finding code this discipline claims via a Form A
        gate or check — the codes whose findings get the owner label."""
        out: set[str] = set()
        for gate in self.gates:
            if isinstance(gate.check, str) and gate.check:
                out.add(gate.check)
        for entry in self.checks:
            code = entry.get("check")
            if isinstance(code, str) and code:
                out.add(code)
        return out


# --- versions & pins ----------------------------------------------------------


def parse_version(version: str) -> tuple[int, int] | None:
    """(major, minor) for a MAJOR.MINOR string, else None."""
    m = VERSION_RE.match(str(version or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_pin(pin: str) -> tuple[str, int, int | None] | None:
    """(id, major, minor|None) for an ``id@MAJOR[.MINOR]`` pin, else None."""
    m = PIN_RE.match(str(pin or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3)) if m.group(3) is not None else None


def pick_version(versions: list[str], major: int, minor: int | None) -> str | None:
    """The version string a pin lands on, from the available candidates.

    Major must match. A bare-major pin (minor None) takes any minor and
    prefers the highest. An exact pin takes its minor **or any newer minor**
    (the standard moved — doctor WARNs discipline-moved, never silently
    refuses a strictly-newer file); an older-only minor does not satisfy an
    exact pin.
    """
    parsed = sorted(
        (v for v in ((parse_version(s), s) for s in versions) if v[0] is not None),
        key=lambda pair: pair[0],
    )
    best: str | None = None
    for (maj, mino), raw in parsed:
        if maj != major:
            continue
        if minor is not None and mino < minor:
            continue
        best = raw  # sorted ascending: the last hit is the highest minor
    return best


# --- parsing -----------------------------------------------------------------


def _as_str_list(value) -> list[str]:
    return [str(v) for v in (value or []) if str(v).strip()]


def _discipline_from_toml(text: str, source_path: Path | None, origin: str) -> Discipline:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{source_path}: invalid discipline TOML: {e}") from None
    disc_id = data.get("id")
    if not disc_id:
        raise SystemExit(f"{source_path}: discipline file is missing required key 'id'")
    slots = [
        Slot(id=str(e.get("id", "")), owns=bool(e.get("owns", True)))
        for e in data.get("slot", [])
        if isinstance(e, dict) and e.get("id")
    ]
    gates = [
        Gate(
            id=str(e.get("id", "")),
            slot=str(e.get("slot", "")),
            kind=str(e.get("kind", "enforced")),
            check=e.get("check") if isinstance(e.get("check"), dict) else str(e.get("check") or ""),
        )
        for e in data.get("gate", [])
        if isinstance(e, dict)
    ]
    checks = [dict(e) for e in data.get("check", []) if isinstance(e, dict)]
    return Discipline(
        id=str(disc_id),
        version=str(data.get("version", "0.1")),
        summary=str(data.get("summary") or "").strip(),
        aka=_as_str_list(data.get("aka")),
        kind=str(data.get("kind", "regime")),
        governs=_as_str_list(data.get("governs")),
        slots=slots,
        gates=gates,
        checks=checks,
        vocabulary=dict(data.get("vocabulary") or {}),
        depends_on=_as_str_list(data.get("depends_on")),
        conflicts=[dict(e) for e in data.get("conflicts", []) if isinstance(e, dict)],
        corrections=dict(data.get("corrections") or {}),
        extends=str(data["extends"]) if data.get("extends") else None,
        origin=origin,
        source_path=source_path,
        raw=data,
    )


def _scan_source(directory, origin: str) -> dict[str, Discipline]:
    """Load every discipline from one directory-like root (a Path or an
    importlib.resources Traversable): single-file (<id>.toml) and directory
    (<id>/discipline.toml) forms, treated identically."""
    out: dict[str, Discipline] = {}
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
            d = _discipline_from_toml(text, source, origin)
            out[d.id] = d
        elif entry.is_dir():
            disc_toml = entry / "discipline.toml"
            if disc_toml.is_file():
                text = disc_toml.read_text(encoding="utf-8")
                source = disc_toml if isinstance(disc_toml, Path) else Path(str(disc_toml))
                d = _discipline_from_toml(text, source, origin)
                out[d.id] = d
    return out


def _builtin_dir():
    return resources.files("flip") / "disciplines_builtin"


def _user_dir() -> Path:
    return flip_home() / "disciplines"


def _notebook_dir(root: Path) -> Path:
    return root / ".flip" / "disciplines"


def _load_all(root: Path | None) -> dict[str, Discipline]:
    merged: dict[str, Discipline] = {}
    merged.update(_scan_source(_builtin_dir(), "built-in"))
    merged.update(_scan_source(_user_dir(), "user"))
    if root is not None:
        merged.update(_scan_source(_notebook_dir(root), "notebook"))
    return merged


# --- lookup ------------------------------------------------------------------


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().replace("-", " ").replace("_", " ").split())


def resolve_discipline_id(text: str, root: Path | None = None) -> str | None:
    """The canonical discipline id for a stated name, or None. Matches the
    id itself, then `aka` phrases, both normalized (case, hyphens, spacing)."""
    disciplines = _load_all(root)
    wanted = _normalize(text)
    if not wanted:
        return None
    for d in disciplines.values():
        if _normalize(d.id) == wanted:
            return d.id
    for d in disciplines.values():
        if any(_normalize(a) == wanted for a in d.aka):
            return d.id
    return None


def list_disciplines(root: Path | None = None) -> list[Discipline]:
    """Every discipline visible from `root` (or just built-ins/user when
    root is None), sorted by id."""
    return sorted(_load_all(root).values(), key=lambda d: d.id)


def load_discipline(disc_id: str, root: Path | None = None) -> Discipline:
    """Resolve one discipline — by id or by any stated `aka` phrase — or
    refuse with the list of known ids."""
    disciplines = _load_all(root)
    if disc_id not in disciplines:
        canonical = resolve_discipline_id(disc_id, root)
        if canonical is not None:
            return disciplines[canonical]
        raise SystemExit(
            f"unknown discipline '{disc_id}'; known: "
            f"{', '.join(sorted(disciplines)) or '(none)'} "
            "(`flip discipline list` shows plain-language names too; "
            "`flip discipline new <id>` scaffolds your own)"
        )
    return disciplines[disc_id]


def discipline_exists(disc_id: str, root: Path | None = None) -> bool:
    return disc_id in _load_all(root)


def resolve_pin(pin: str, root: Path | None = None) -> tuple[Discipline | None, str | None]:
    """The discipline a manifest pin lands on: (Discipline, None) on success,
    (None, reason) when it can't resolve — the reason is doctor's
    unknown-discipline finding message."""
    parsed = parse_pin(pin)
    if parsed is None:
        return None, (
            f"discipline pin '{pin}' is malformed — pins are id@MAJOR or "
            "id@MAJOR.MINOR (e.g. lineage@1, systematic-screening@0.1)"
        )
    disc_id, major, minor = parsed
    available = _load_all(root)
    d = available.get(disc_id)
    if d is None:
        return None, (
            f"pin '{pin}' names no known discipline; known: "
            f"{', '.join(sorted(available)) or '(none)'} (`flip discipline list`)"
        )
    if pick_version([d.version], major, minor) is None:
        return None, (
            f"pin '{pin}' matches no available version of '{disc_id}' "
            f"(available: {d.version}); re-pin or update the discipline file"
        )
    return d, None


# --- the effective set (dormancy, the anti-J2EE rule) -------------------------


def effective_pins(root: Path, declared: list | None) -> tuple[list[str], bool]:
    """(pins, explicitly_declared) for a notebook.

    A manifest with no `disciplines:` key behaves exactly as today: the
    implicit set is `lineage@1` (+ `forecasting@1` iff forecasts/ exists) —
    self-description only. Doctor adds **no** findings and **no** labels in
    implicit mode; the machinery wakes only when someone declares.
    """
    pins = [str(p) for p in (declared or []) if str(p).strip()]
    if pins:
        return pins, True
    implicit = ["lineage@1"]
    if (root / "forecasts").is_dir():
        implicit.append("forecasting@1")
    return implicit, False


# --- validation (doctor's bad-discipline surface) -----------------------------


def _validate_predicate(pred: dict, where: str, problems: list[str]) -> None:
    cls = pred.get("class")
    if cls not in pages_mod.ENTITY_DIRS:
        problems.append(
            f"{where}: field predicate has unknown class '{cls}' "
            f"(one of: {', '.join(pages_mod.ENTITY_DIRS)})"
        )
    if not str(pred.get("field") or "").strip():
        problems.append(f"{where}: field predicate is missing 'field'")
    requires = pred.get("requires")
    if requires not in PREDICATE_REQUIRES:
        problems.append(
            f"{where}: field predicate 'requires' must be one of "
            f"{', '.join(PREDICATE_REQUIRES)} (got {requires!r})"
        )
    elif requires == "one_of" and not _as_str_list(pred.get("one_of")):
        problems.append(f"{where}: requires = \"one_of\" needs a non-empty one_of list")


def validate_discipline(d: Discipline) -> list[str]:
    """Problems doctor reports as ERROR bad-discipline. A gate referencing a
    check code doctor cannot emit is the load-bearing one: the trip-wire
    only exists if it's enforced (L11)."""
    from .doctor import CHECK_CODES  # local: doctor imports disciplines lazily too

    problems: list[str] = []
    if parse_version(d.version) is None:
        problems.append(
            f"version '{d.version}' is not MAJOR.MINOR (files always carry the "
            "full form, e.g. \"1.0\" or \"0.1\")"
        )
    if d.kind not in DISCIPLINE_KINDS:
        problems.append(
            f"kind '{d.kind}' invalid (one of: {', '.join(DISCIPLINE_KINDS)})"
        )
    for gate in d.gates:
        where = f"gate '{gate.id or '?'}'"
        if gate.kind not in GATE_KINDS:
            problems.append(
                f"{where}: kind '{gate.kind}' invalid (one of: {', '.join(GATE_KINDS)})"
            )
        if isinstance(gate.check, dict):
            _validate_predicate(gate.check, where, problems)
        elif not gate.check:
            problems.append(f"{where}: has no check — a gate must reference one")
        elif gate.check not in CHECK_CODES:
            problems.append(
                f"{where}: references unknown check code '{gate.check}' — not a "
                "code doctor can emit; use a real code (`flip doctor` prints them) "
                "or a field predicate"
            )
    for i, entry in enumerate(d.checks):
        where = f"check entry {entry.get('id') or i + 1}"
        code = entry.get("check")
        if code is not None:
            if str(code) not in CHECK_CODES:
                problems.append(
                    f"{where}: references unknown check code '{code}'"
                )
        elif "class" in entry or "field" in entry or "requires" in entry:
            _validate_predicate(entry, where, problems)
        else:
            problems.append(
                f"{where}: is neither a check code ({{check = \"…\"}}) nor a "
                "field predicate ({class, field, requires, …})"
            )
    return problems


# --- field predicates (decision C-C, Form B) ----------------------------------


def _dotted_get(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def evaluate_predicate(root: Path, pred: dict) -> list[tuple[str, str]]:
    """(rel_path, detail) for every page of the predicate's class that fails
    it. A malformed predicate evaluates to no failures — validate_discipline
    is the surface that reports it."""
    cls = pred.get("class")
    field_path = str(pred.get("field") or "")
    requires = pred.get("requires")
    if cls not in pages_mod.ENTITY_DIRS or not field_path or requires not in PREDICATE_REQUIRES:
        return []
    one_of = _as_str_list(pred.get("one_of"))
    if requires == "one_of" and not one_of:
        return []
    failures: list[tuple[str, str]] = []
    found, _errors = pages_mod.iter_pages_tolerant(root, cls)
    for page in found:
        value = _dotted_get(page.fm, field_path)
        empty = value in (None, "", "?")
        name = page.id or page.path.stem
        detail: str | None = None
        if requires == "present" and empty:
            detail = f"{name}: field '{field_path}' is missing or empty"
        elif requires == "absent" and not empty:
            detail = f"{name}: field '{field_path}' is present (must be absent)"
        elif requires == "one_of":
            if empty:
                detail = f"{name}: field '{field_path}' is missing or empty"
            elif str(value) not in one_of:
                detail = (
                    f"{name}: field '{field_path}' is '{value}' "
                    f"(one of: {', '.join(one_of)})"
                )
        if detail is not None:
            failures.append((page.path.relative_to(root).as_posix(), detail))
    return failures


# --- flip discipline new: scaffold a user discipline file ---------------------

DISCIPLINE_TEMPLATE = '''\
# {id} — a flip discipline: the standard the work is held to.
#
# A discipline is NOT a kind. A kind says what you're making ("a lit
# review"); a discipline says the standard it's held to ("systematic
# screening"). This file IS the documentation: every key below is explained
# in place. Loaded from $FLIP_HOME/disciplines/{id}.toml (or a
# {id}/discipline.toml directory — same schema, either way).

id      = "{id}"

# Versions are MAJOR.MINOR. Start authored disciplines at "0.1": 0.x marks
# content still earning its stability; 1.x is reserved for self-descriptions
# of enforcement flip itself guarantees (lineage, forecasting). Manifests pin
# "{id}@0" (any minor) or "{id}@0.1" (exact — doctor WARNs when a newer
# minor appears, so a moved standard is reviewed, never silently adopted).
version = "0.1"

# The closed taxonomy: "regime" (a full policy standard over its classes) |
# "overlay" (adds policy atop another regime) | "frame" (an analytical
# framing) | "frame-regime" (both at once).
kind = "regime"

# Plain-language names people actually say; `flip discipline show` resolves
# them. Delete if the id is what everyone says.
aka = []

# One paragraph, outcome-first, in the field's own words: what does work
# held to this standard let a reader do that unheld work doesn't?
summary = """
Describe the standard here: what it guarantees, and what failure it
defends against.
"""

# The classes this discipline governs — the coarse default. The real
# partition is the slots below.
governs = ["sources"]

# A slot is a named policy area — the unit of ownership in composition.
# Slot names are open strings; reuse existing names (custody, grading,
# corroboration, release, resolution, calibration, screening, …) so genuine
# collisions actually collide. owns = true (the default) means this
# discipline's gates block on that area; two declared disciplines both
# owning one slot is a conflict the manifest resolves ([discipline_resolve]).
[[slot]]
id   = "example-slot"
owns = true

# Gates: the bars. kind = "enforced" blocks (doctor ERROR when this
# discipline owns the slot); kind = "attested" records that a third party
# already ran a verification flip cannot re-run (peer review, an audit) —
# attested gates never block, they label. `check` is either a doctor
# finding code (e.g. check = "under-verified") or a field predicate:
[[gate]]
id   = "example-gate"
slot = "example-slot"
kind = "enforced"
[gate.check]
class    = "references"          # references|claims|questions|decisions|forecasts|sessions
field    = "example.field"       # dotted frontmatter path on each page
requires = "present"             # present | absent | one_of (+ one_of = [...])
message  = "say, in outcome language, what a passing corpus can show"

# Advisory rubric entries: run on everything the discipline can see, never
# blocking — non-owner findings are labeled "advisory ({id}): …".
# Either form works here too:
# [[check]]
# check = "stale-freshness"      # an existing doctor code
# [[check]]
# class    = "references"
# field    = "example.reason"
# requires = "present"
# message  = "…"

# Namespaced badges/terms this discipline defines, e.g.
# "{id}:screened" = "what earning that badge means". Delete if none.
# [vocabulary]

# Graceful partnership: a discipline this one works best alongside. An
# absent partner is a doctor WARN, never a conflict. Pins allowed.
# depends_on = ["lineage@1"]

# Genuine collisions, declared: this discipline cannot compose with `with`
# on `slot`; the manifest must resolve. Never silently merged.
# conflicts = [{{with = "other-discipline", slot = "example-slot"}}]

# Reserved: your corrections policy, parsed and carried with the discipline
# but not yet enforced (the propagation round comes after the first real
# correction event). State it anyway — the standard should say what happens
# when the work turns out wrong.
# [corrections]
# policy = "…"
'''


def scaffold_discipline(disc_id: str, force: bool = False) -> Path:
    """Write $FLIP_HOME/disciplines/<id>.toml from the commented template."""
    if not DISCIPLINE_ID_RE.match(disc_id or ""):
        raise SystemExit(
            f"invalid discipline id {disc_id!r}: use lowercase letters, digits, and "
            "hyphens, starting with a letter (e.g. systematic-screening)"
        )
    path = _user_dir() / f"{disc_id}.toml"
    if path.exists() and not force:
        raise SystemExit(
            f"{path} already exists — edit it directly, or pass --force to overwrite"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DISCIPLINE_TEMPLATE.format(id=disc_id), encoding="utf-8")
    return path
