"""Reusable workflow definitions and phase suggestions.

A workflow names a sequence of work, not the thing being made. Definitions
are plain TOML and load from built-ins, linked plugins, ``$FLIP_HOME``, and the
notebook. The registry is deliberately advisory: phase state is derived from
Work Session receipts and ``next_phase`` only suggests what follows.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from . import events, pages
from .manifest import load_manifest, save_manifest
from .registry import flip_home

WORKFLOW_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PHASE_ID_RE = WORKFLOW_ID_RE
VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
PIN_VERSION_RE = re.compile(r"^\d+(?:\.\d+(?:\.\d+)?)?$")


@dataclass
class Phase:
    id: str
    guide: str = ""
    produces: list[str] = field(default_factory=list)
    next: str = ""


@dataclass
class Workflow:
    id: str
    version: str
    summary: str = ""
    applies_to: list[str] = field(default_factory=list)
    entry: str = ""
    phases: list[Phase] = field(default_factory=list)
    origin: str = "built-in"
    source_path: Path | None = None
    provider: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def qualified_id(self) -> str:
        if self.provider == "kind":
            return f"kind:{self.id}"
        return f"{self.provider}/{self.id}" if self.provider else self.id

    @property
    def pin(self) -> str:
        return f"{self.qualified_id}@{self.version}"


def _parse(text: str, path: Path | None, origin: str, provider: str = "") -> Workflow:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"{path}: invalid workflow TOML: {exc}") from None
    workflow_id = str(data.get("id") or "")
    version = str(data.get("version") or "")
    if not WORKFLOW_ID_RE.match(workflow_id):
        raise SystemExit(
            f"{path}: workflow id {workflow_id!r} must start with a letter and use "
            "lowercase letters, digits, and dashes"
        )
    if not VERSION_RE.match(version):
        raise SystemExit(f"{path}: workflow '{workflow_id}' needs version MAJOR.MINOR[.PATCH]")
    raw_phases = data.get("phase")
    if not isinstance(raw_phases, list) or not raw_phases:
        raise SystemExit(f"{path}: workflow '{workflow_id}' needs at least one [[phase]]")
    phases: list[Phase] = []
    seen: set[str] = set()
    for raw in raw_phases:
        if not isinstance(raw, dict):
            raise SystemExit(f"{path}: every [[phase]] must be a table")
        phase_id = str(raw.get("id") or "")
        if not PHASE_ID_RE.match(phase_id):
            raise SystemExit(f"{path}: invalid or missing workflow phase id {phase_id!r}")
        if phase_id in seen:
            raise SystemExit(f"{path}: duplicate workflow phase '{phase_id}'")
        seen.add(phase_id)
        produces_raw = raw.get("produces", [])
        if isinstance(produces_raw, str):
            produces = [produces_raw] if produces_raw.strip() else []
        elif isinstance(produces_raw, list):
            produces = [str(v) for v in produces_raw if str(v).strip()]
        else:
            raise SystemExit(f"{path}: phase '{phase_id}' produces must be a string or list")
        phases.append(Phase(
            id=phase_id,
            guide=str(raw.get("guide") or raw.get("does") or "").strip(),
            produces=produces,
            next=str(raw.get("next") or "").strip(),
        ))
    entry = str(data.get("entry") or phases[0].id)
    if entry not in seen:
        raise SystemExit(f"{path}: entry phase '{entry}' is not declared")
    for phase in phases:
        if phase.next and phase.next not in seen:
            raise SystemExit(
                f"{path}: phase '{phase.id}' points to unknown next phase '{phase.next}'"
            )
    return Workflow(
        id=workflow_id,
        version=version,
        summary=str(data.get("summary") or "").strip(),
        applies_to=[str(v) for v in data.get("applies_to", []) if str(v).strip()],
        entry=entry,
        phases=phases,
        origin=origin,
        source_path=path,
        provider=provider,
        raw=data,
    )


def _scan_dir(directory, origin: str) -> list[Workflow]:
    out: list[Workflow] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return out
    for entry in entries:
        candidate = entry / "workflow.toml" if entry.is_dir() else entry
        if not candidate.is_file() or candidate.suffix != ".toml":
            continue
        path = candidate if isinstance(candidate, Path) else Path(str(candidate))
        out.append(_parse(candidate.read_text(encoding="utf-8"), path, origin))
    return out


def _kind_adapter(root: Path | None) -> Workflow | None:
    if root is None:
        return None
    from . import kinds

    manifest = load_manifest(root)
    kind = kinds.load_kind(manifest.kind, root)
    if not kind.workflow:
        return None
    phase_rows = []
    for n, row in enumerate(kind.workflow):
        row = dict(row)
        row.setdefault("id", f"phase-{n + 1}")
        if not row.get("next") and n + 1 < len(kind.workflow):
            row["next"] = str(kind.workflow[n + 1].get("id") or f"phase-{n + 2}")
        phase_rows.append(row)
    data = {
        "id": manifest.kind,
        "version": kind.version if VERSION_RE.match(kind.version or "") else "0.1",
        "summary": f"Compatibility workflow embedded in kind {manifest.kind}",
        "entry": phase_rows[0]["id"],
        "phase": phase_rows,
    }
    # json string quoting is also valid for the values emitted below, but the
    # adapter can bypass TOML serialization and use the same structural rules.
    lines = [f"id = {json.dumps(data['id'])}", f"version = {json.dumps(data['version'])}",
             f"summary = {json.dumps(data['summary'])}", f"entry = {json.dumps(data['entry'])}"]
    for row in phase_rows:
        lines.extend(["", "[[phase]]", f"id = {json.dumps(str(row['id']))}"])
        if row.get("does") or row.get("guide"):
            lines.append(f"guide = {json.dumps(str(row.get('guide') or row.get('does')))}")
        if row.get("produces"):
            lines.append(f"produces = {json.dumps(row['produces'])}")
        if row.get("next"):
            lines.append(f"next = {json.dumps(str(row['next']))}")
    workflow = _parse("\n".join(lines) + "\n", kind.source_path, "kind")
    workflow.provider = "kind"
    return workflow


def list_workflows(root: Path | None = None) -> list[Workflow]:
    """Return visible workflows without silent id replacement."""
    found: dict[str, Workflow] = {}

    def add(workflow: Workflow) -> None:
        key = workflow.qualified_id
        if key in found:
            other = found[key]
            raise SystemExit(
                f"workflow id collision '{key}' between {other.source_path} and "
                f"{workflow.source_path}; rename one definition (registry never uses last-wins)"
            )
        found[key] = workflow

    for workflow in _scan_dir(resources.files("flip") / "workflows_builtin", "built-in"):
        add(workflow)
    # A linked bundle is discoverable, but executable handlers remain dormant
    # until the scope explicitly enables the plugin.
    from . import extensions

    for plugin, path in extensions.definition_exports("workflows"):
        add(_parse(path.read_text(encoding="utf-8"), path, "plugin", plugin.id))
    for workflow in _scan_dir(flip_home() / "workflows", "user"):
        add(workflow)
    if root is not None:
        for workflow in _scan_dir(root / ".flip" / "workflows", "notebook"):
            add(workflow)
        adapter = _kind_adapter(root)
        if adapter is not None and adapter.qualified_id not in found:
            add(adapter)
    return sorted(found.values(), key=lambda workflow: workflow.qualified_id)


def _split_pin(value: str) -> tuple[str, str]:
    name, marker, version = str(value).rpartition("@")
    return (name, version) if marker and PIN_VERSION_RE.match(version) else (str(value), "")


def load_workflow(value: str, root: Path | None = None) -> Workflow:
    wanted, version = _split_pin(value)
    workflows = list_workflows(root)
    exact = [workflow for workflow in workflows if workflow.qualified_id == wanted]
    if not exact and "/" not in wanted:
        exact = [workflow for workflow in workflows if workflow.id == wanted]
        if len(exact) > 1:
            choices = ", ".join(workflow.qualified_id for workflow in exact)
            raise SystemExit(f"workflow '{wanted}' is ambiguous; use one of: {choices}")
    if not exact:
        known = ", ".join(workflow.qualified_id for workflow in workflows) or "(none)"
        raise SystemExit(f"unknown workflow '{wanted}'; known: {known}")
    workflow = exact[0]
    if version:
        requested = version.split(".")
        actual = workflow.version.split(".")
        if requested[0] != actual[0] or (len(requested) > 1 and version != workflow.version):
            raise SystemExit(
                f"workflow '{wanted}' is {workflow.version}, which does not satisfy @{version}"
            )
    return workflow


def workflow_data(workflow: Workflow) -> dict:
    return {
        "id": workflow.qualified_id,
        "version": workflow.version,
        "pin": workflow.pin,
        "summary": workflow.summary,
        "applies_to": workflow.applies_to,
        "entry": workflow.entry,
        "origin": workflow.origin,
        "provider": workflow.provider or None,
        "source": str(workflow.source_path) if workflow.source_path else None,
        "phases": [
            {"id": phase.id, "guide": phase.guide, "produces": phase.produces,
             "next": phase.next or None}
            for phase in workflow.phases
        ],
    }


def use_workflow(root: Path, value: str) -> Workflow:
    workflow = load_workflow(value, root)
    manifest = load_manifest(root)
    manifest.workflow = workflow.pin
    save_manifest(root, manifest)
    from . import views
    from .manifest import touch_updated
    touch_updated(root)
    views.regenerate(root)
    events.emit(root, "workflow.use", workflow=workflow.pin)
    return workflow


def _session_order(page: pages.Page) -> tuple[int, str]:
    """Order sessions by their opening time, with a stable legacy fallback.

    Filenames have minute precision and their slugs are not chronological.
    The opening nanoseconds move into the receipt when a session closes.
    """
    receipt = page.fm.get("receipt")
    receipt = receipt if isinstance(receipt, dict) else {}
    for value in (page.fm.get("receipt_opened_ns"), receipt.get("observed_since_ns")):
        if isinstance(value, bool):
            continue
        if isinstance(value, int) or (isinstance(value, str) and value.isdecimal()):
            if int(value) > 0:
                return int(value), page.path.name
    for value in (page.fm.get("started"), receipt.get("observed_since"),
                  page.fm.get("ended"), page.path.name[:15]):
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        elapsed = stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)
        ns = ((elapsed.days * 86400 + elapsed.seconds) * 1_000_000_000
              + elapsed.microseconds * 1000)
        return ns, page.path.name
    return 0, page.path.name


def next_phase(root: Path, value: str | None = None) -> dict:
    manifest = load_manifest(root)
    selected = value or manifest.workflow
    if not selected:
        adapter = _kind_adapter(root)
        if adapter is None:
            raise SystemExit(
                "this notebook has no workflow pin; run `flip workflow list` then "
                "`flip workflow use <id>`"
            )
        workflow = adapter
    else:
        workflow = load_workflow(selected, root)
    last = None
    sessions_dir = root / "sessions"
    if sessions_dir.is_dir():
        for path in sessions_dir.glob("*.md"):
            try:
                page = pages.read_page(path)
            except Exception:
                continue
            session_workflow, _ = _split_pin(str(page.fm.get("workflow") or ""))
            if session_workflow in (workflow.qualified_id, workflow.id):
                if last is None or _session_order(page) > _session_order(last):
                    last = page
    phase_id = workflow.entry
    reason = "entry phase; no earlier session receipt for this workflow"
    if last is not None:
        recorded = str(last.fm.get("phase") or workflow.entry)
        by_id = {phase.id: phase for phase in workflow.phases}
        if recorded not in by_id:
            raise SystemExit(
                f"latest workflow session records unknown phase '{recorded}' for "
                f"{workflow.qualified_id}; repair that session receipt or choose --workflow"
            )
        if not last.fm.get("ended"):
            phase_id = recorded
            reason = f"resume open session {last.path.name}"
        elif by_id[recorded].next:
            phase_id = by_id[recorded].next
            reason = f"phase after closed {recorded} session {last.path.name}"
        else:
            return {
                "workflow": workflow.pin,
                "phase": None,
                "complete": True,
                "reason": f"closed terminal phase {recorded} in {last.path.name}",
            }
    phase = next(phase for phase in workflow.phases if phase.id == phase_id)
    return {
        "workflow": workflow.pin,
        "phase": phase.id,
        "complete": False,
        "guide": phase.guide,
        "produces": phase.produces,
        "reason": reason,
    }


def _render(workflow_id: str, version: str, summary: str, phases: list[Phase]) -> str:
    lines = [f"id = {json.dumps(workflow_id)}", f"version = {json.dumps(version)}",
             f"summary = {json.dumps(summary)}", f"entry = {json.dumps(phases[0].id)}"]
    for phase in phases:
        lines.extend(["", "[[phase]]", f"id = {json.dumps(phase.id)}"])
        if phase.guide:
            lines.append(f"guide = {json.dumps(phase.guide)}")
        if phase.produces:
            lines.append(f"produces = {json.dumps(phase.produces)}")
        if phase.next:
            lines.append(f"next = {json.dumps(phase.next)}")
    return "\n".join(lines) + "\n"


def create_workflow(workflow_id: str, root: Path | None = None,
                    from_id: str | None = None, user: bool = False) -> Path:
    if not WORKFLOW_ID_RE.match(workflow_id):
        raise SystemExit("workflow id must start with a letter and use lowercase/digits/dashes")
    directory = flip_home() / "workflows" if user or root is None else root / ".flip" / "workflows"
    path = directory / f"{workflow_id}.toml"
    if path.exists():
        raise SystemExit(f"workflow already exists: {path}")
    if from_id:
        source = load_workflow(from_id, root)
        phases = [Phase(p.id, p.guide, list(p.produces), p.next) for p in source.phases]
        summary = f"Fork of {source.qualified_id}: {source.summary}"
    else:
        phases = [Phase("orient", "Read the bounded context and choose one item.",
                        ["selected-item"], "work"),
                  Phase("work", "Use canonical Flip commands; keep judgment explicit.",
                        ["durable-artifact"], "audit"),
                  Phase("audit", "Run checks and close the Work Session receipt.",
                        ["doctor-run", "session-receipt"], "")]
        summary = "Describe when this reusable sequence is useful."
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(workflow_id, "0.1", summary, phases), encoding="utf-8")
    return path


__all__ = [
    "Phase", "Workflow", "create_workflow", "list_workflows", "load_workflow",
    "next_phase", "use_workflow", "workflow_data",
]
