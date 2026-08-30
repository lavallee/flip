"""Local plugin registry and typed subprocess hooks.

Plugins are distribution bundles. Linking records where an already-materialized
bundle lives; enabling opts one scope into its executable handlers. Definition
exports are discoverable when linked. Nothing here downloads code, imports a
plugin into the Flip process, or grants a write path around canonical commands.

Executable plugins are trusted local programs, not sandboxed programs. The
protocol limits time/output and validates returned JSON, but it cannot prevent
a command from using the operating-system permissions of the current user.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .registry import flip_home

PLUGIN_FILE = "flip-plugin.toml"
REGISTRY_FILE = "plugins.json"
LOCK_FILE = Path(".flip") / "extensions.lock"
WORKSPACE_PINS = Path(".flip") / "plugins.json"
HOOKS: dict[str, dict] = {
    "context.provide@1": {"strategy": "provide-all", "failure": "skip-and-report"},
    "frontier.provide@1": {"strategy": "provide-all", "failure": "skip-and-report"},
    "frontier.filter@1": {"strategy": "filter-chain", "failure": "skip-and-report"},
    "check.provide@1": {"strategy": "provide-all", "failure": "warn"},
    "receipt.filter@1": {"strategy": "filter-chain", "failure": "skip-and-report"},
}
PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9-]*(?:/[a-z][a-z0-9-]*)+$")
LOCAL_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")
REQUIREMENT_RE = re.compile(r"^(>=|<=|==|>|<)\s*(\d+(?:\.\d+){1,2})$")
PROTOCOL = "flip-filter/1"
DEFAULT_TIMEOUT = 5.0
MAX_OUTPUT = 1024 * 1024


@dataclass
class Handler:
    id: str
    hook: str
    command: list[str]
    protocol: str = PROTOCOL
    needs: list[str] = field(default_factory=list)
    before: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    timeout: float = DEFAULT_TIMEOUT
    plugin_id: str = ""
    plugin_root: Path | None = None

    @property
    def qualified_id(self) -> str:
        return f"{self.plugin_id}/{self.id}"


@dataclass
class Plugin:
    id: str
    version: str
    root: Path
    summary: str = ""
    license: str = ""
    requires_flip: str = ""
    capabilities: list[str] = field(default_factory=list)
    exports: dict[str, list[str]] = field(default_factory=dict)
    handlers: list[Handler] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def pin(self) -> str:
        return f"{self.id}@{self.version}"


def _strings(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    raise SystemExit(f"expected a string or list of strings, got {type(value).__name__}")


def load_plugin(path: Path) -> Plugin:
    root = path.resolve()
    manifest_path = root / PLUGIN_FILE if root.is_dir() else root
    if manifest_path.name != PLUGIN_FILE or not manifest_path.is_file():
        raise SystemExit(f"{path}: no {PLUGIN_FILE} found")
    root = manifest_path.parent
    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"{manifest_path}: invalid TOML: {exc}") from None
    meta = data.get("plugin")
    if not isinstance(meta, dict):
        raise SystemExit(f"{manifest_path}: missing [plugin] table")
    plugin_id = str(meta.get("id") or "")
    version = str(meta.get("version") or "")
    if not PLUGIN_ID_RE.match(plugin_id):
        raise SystemExit(
            f"{manifest_path}: plugin id {plugin_id!r} must be qualified, e.g. team/name"
        )
    if not VERSION_RE.match(version):
        raise SystemExit(f"{manifest_path}: plugin needs version MAJOR.MINOR[.PATCH]")
    exports = data.get("exports") or {}
    if not isinstance(exports, dict):
        raise SystemExit(f"{manifest_path}: [exports] must be a table")
    parsed_exports: dict[str, list[str]] = {}
    for noun, values in exports.items():
        if noun not in ("kinds", "disciplines", "workflows", "skills", "examples", "docs"):
            raise SystemExit(f"{manifest_path}: unknown export noun '{noun}'")
        parsed_exports[str(noun)] = _strings(values)
    handlers: list[Handler] = []
    for raw in data.get("filters", []):
        if not isinstance(raw, dict):
            raise SystemExit(f"{manifest_path}: each [[filters]] entry must be a table")
        handler_id = str(raw.get("id") or "")
        hook = str(raw.get("hook") or "")
        if not LOCAL_ID_RE.match(handler_id):
            raise SystemExit(f"{manifest_path}: invalid filter id {handler_id!r}")
        if hook not in HOOKS:
            raise SystemExit(
                f"{manifest_path}: filter '{handler_id}' uses unknown hook '{hook}' "
                f"(known: {', '.join(HOOKS)})"
            )
        command = raw.get("command")
        if isinstance(command, str):
            command_parts = shlex.split(command)
        elif isinstance(command, list):
            command_parts = [str(part) for part in command]
        else:
            command_parts = []
        if not command_parts:
            raise SystemExit(f"{manifest_path}: filter '{handler_id}' needs command")
        protocol = str(raw.get("protocol") or PROTOCOL)
        if protocol != PROTOCOL:
            raise SystemExit(
                f"{manifest_path}: filter '{handler_id}' protocol {protocol!r} is unsupported"
            )
        try:
            timeout = float(raw.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            raise SystemExit(f"{manifest_path}: filter '{handler_id}' timeout must be numeric") from None
        if not 0 < timeout <= 60:
            raise SystemExit(f"{manifest_path}: filter '{handler_id}' timeout must be >0 and <=60")
        handlers.append(Handler(
            id=handler_id, hook=hook, command=command_parts, protocol=protocol,
            needs=_strings(raw.get("needs")), before=_strings(raw.get("before")),
            after=_strings(raw.get("after")), timeout=timeout,
            plugin_id=plugin_id, plugin_root=root,
        ))
    plugin = Plugin(
        id=plugin_id, version=version, root=root,
        summary=str(meta.get("summary") or "").strip(),
        license=str(meta.get("license") or "").strip(),
        requires_flip=str(meta.get("requires_flip") or "").strip(),
        capabilities=_strings(meta.get("capabilities")),
        exports=parsed_exports, handlers=handlers, raw=data,
    )
    validate_plugin(plugin)
    return plugin


def _inside(plugin: Plugin, rel: str) -> Path:
    path = (plugin.root / rel).resolve()
    try:
        path.relative_to(plugin.root)
    except ValueError:
        raise SystemExit(f"plugin '{plugin.id}' export escapes its bundle: {rel}") from None
    return path


def validate_plugin(plugin: Plugin) -> None:
    if plugin.requires_flip:
        from . import __version__

        current = tuple(int(part) for part in __version__.split(".")[:3])
        for raw in plugin.requires_flip.split(","):
            match = REQUIREMENT_RE.match(raw.strip())
            if not match:
                raise SystemExit(
                    f"plugin '{plugin.id}' has unsupported requires_flip constraint {raw!r}; "
                    "use comma-separated >=, <=, ==, >, or < versions"
                )
            operator, wanted_text = match.groups()
            wanted_parts = [int(part) for part in wanted_text.split(".")]
            wanted = tuple(wanted_parts + [0] * (3 - len(wanted_parts)))
            satisfied = {
                ">=": current >= wanted, "<=": current <= wanted, "==": current == wanted,
                ">": current > wanted, "<": current < wanted,
            }[operator]
            if not satisfied:
                raise SystemExit(
                    f"plugin '{plugin.id}' requires Flip {plugin.requires_flip}; "
                    f"this process is {__version__}"
                )
    for noun, rels in plugin.exports.items():
        for rel in rels:
            path = _inside(plugin, rel)
            if not path.exists():
                raise SystemExit(f"plugin '{plugin.id}' {noun} export does not exist: {rel}")
    declared = set(plugin.capabilities)
    for handler in plugin.handlers:
        missing = set(handler.needs) - declared
        if missing:
            raise SystemExit(
                f"plugin '{plugin.id}' filter '{handler.id}' needs undeclared capabilities: "
                f"{', '.join(sorted(missing))}"
            )
        first = handler.command[0]
        if first.startswith(".") or "/" in first:
            executable = _inside(plugin, first)
            if not executable.is_file():
                raise SystemExit(
                    f"plugin '{plugin.id}' filter '{handler.id}' command does not exist: {first}"
                )


def deep_validate_plugin(plugin: Plugin) -> None:
    """Validate exported definition contents as well as manifest paths."""
    from . import disciplines, kinds, workflows

    for rel in plugin.exports.get("kinds", []):
        path = _inside(plugin, rel)
        candidate = path / "kind.toml" if path.is_dir() else path
        kinds._kind_from_toml(candidate.read_text(encoding="utf-8"), candidate, "plugin")
    for rel in plugin.exports.get("disciplines", []):
        path = _inside(plugin, rel)
        candidate = path / "discipline.toml" if path.is_dir() else path
        definition = disciplines._discipline_from_toml(
            candidate.read_text(encoding="utf-8"), candidate, "plugin"
        )
        problems = disciplines.validate_discipline(definition)
        if problems:
            raise SystemExit(
                f"plugin '{plugin.id}' discipline '{definition.id}' is invalid: "
                + "; ".join(problems)
            )
    for rel in plugin.exports.get("workflows", []):
        path = _inside(plugin, rel)
        candidate = path / "workflow.toml" if path.is_dir() else path
        workflows._parse(candidate.read_text(encoding="utf-8"), candidate, "plugin", plugin.id)


def _registry_path() -> Path:
    return flip_home() / REGISTRY_FILE


def _read_registry() -> dict[str, dict]:
    path = _registry_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{path}: invalid plugin registry: {exc}") from None
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: plugin registry must be a JSON object")
    return data


def _write_registry(data: dict[str, dict]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def link_plugin(path: Path) -> Plugin:
    plugin = load_plugin(path)
    deep_validate_plugin(plugin)
    data = _read_registry()
    data[plugin.id] = {"path": str(plugin.root), "version": plugin.version}
    _write_registry(data)
    return plugin


def unlink_plugin(plugin_id: str) -> bool:
    data = _read_registry()
    if plugin_id not in data:
        return False
    del data[plugin_id]
    _write_registry(data)
    return True


def linked_plugins(tolerant: bool = False) -> list[Plugin]:
    out: list[Plugin] = []
    for plugin_id, row in sorted(_read_registry().items()):
        try:
            if not isinstance(row, dict) or not row.get("path"):
                raise SystemExit(f"registry entry '{plugin_id}' has no path")
            plugin = load_plugin(Path(str(row["path"])))
            if plugin.id != plugin_id:
                raise SystemExit(
                    f"registry key '{plugin_id}' points to plugin declaring '{plugin.id}'"
                )
            out.append(plugin)
        except SystemExit:
            if not tolerant:
                raise
    return out


def resolve_plugin(value: str) -> Plugin:
    plugin_id, marker, version = value.rpartition("@")
    wanted = plugin_id if marker and VERSION_RE.match(version) else value
    required = version if wanted != value else ""
    matches = [plugin for plugin in linked_plugins() if plugin.id == wanted]
    if not matches:
        known = ", ".join(plugin.id for plugin in linked_plugins()) or "(none)"
        raise SystemExit(f"unknown linked plugin '{wanted}'; linked: {known}")
    plugin = matches[0]
    if required and plugin.version != required:
        raise SystemExit(f"plugin '{wanted}' is {plugin.version}, not requested {required}")
    return plugin


def definition_exports(noun: str) -> list[tuple[Plugin, Path]]:
    out: list[tuple[Plugin, Path]] = []
    for plugin in linked_plugins():
        for rel in plugin.exports.get(noun, []):
            path = _inside(plugin, rel)
            if path.is_dir():
                filename = {"kinds": "kind.toml", "disciplines": "discipline.toml",
                            "workflows": "workflow.toml"}.get(noun)
                if filename:
                    path = path / filename
            out.append((plugin, path))
    return out


def _scope_pins(root: Path) -> list[str]:
    from . import beat, workspace
    from .manifest import load_manifest
    from .util import is_notebook_root

    if is_notebook_root(root):
        return [str(pin) for pin in load_manifest(root).plugins]
    if beat.is_beat_root(root):
        return [str(pin) for pin in (beat.load_beat(root).extras.get("plugins") or [])]
    if workspace.is_workspace_root(root):
        path = root / WORKSPACE_PINS
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}: invalid JSON: {exc}") from None
        return [str(pin) for pin in data.get("plugins", [])]
    raise SystemExit(f"{root}: not a Flip notebook, beat, or workspace root")


def _save_scope_pins(root: Path, pins: list[str]) -> None:
    from . import beat, views, workspace
    from .manifest import load_manifest, save_manifest, touch_updated
    from .util import is_notebook_root

    if is_notebook_root(root):
        manifest = load_manifest(root)
        manifest.plugins = pins
        save_manifest(root, manifest)
        touch_updated(root)
        views.regenerate(root)
        return
    if beat.is_beat_root(root):
        manifest = beat.load_beat(root)
        manifest.extras["plugins"] = pins
        beat.save_beat(root, manifest)
        beat.touch_updated(root)
        beat.regenerate(root)
        return
    if workspace.is_workspace_root(root):
        path = root / WORKSPACE_PINS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"plugins": pins}, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        return
    raise SystemExit(f"{root}: not a Flip notebook, beat, or workspace root")


def _bundle_hash(plugin: Plugin) -> str:
    digest = hashlib.sha256()
    for path in sorted(plugin.root.rglob("*")):
        if not path.is_file() or any(part in (".git", "__pycache__") for part in path.parts):
            continue
        digest.update(path.relative_to(plugin.root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_lock(root: Path, plugins: list[Plugin]) -> None:
    path = root / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "format": "flip-extensions-lock/1",
        "plugins": [
            {"id": plugin.id, "version": plugin.version, "path": str(plugin.root),
             "sha256": _bundle_hash(plugin)}
            for plugin in sorted(plugins, key=lambda item: item.id)
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def validate_lock(root: Path) -> list[str]:
    """Return exact-version/path/content drift in this scope's lock."""
    plugins = enabled_plugins(root)
    path = root / LOCK_FILE
    if not path.is_file():
        return ["enabled plugins have no .flip/extensions.lock"] if plugins else []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: invalid extension lock: {exc}"]
    if data.get("format") != "flip-extensions-lock/1" or not isinstance(data.get("plugins"), list):
        return [f"{path}: unsupported or malformed extension lock"]
    locked = {str(row.get("id")): row for row in data["plugins"] if isinstance(row, dict)}
    messages: list[str] = []
    expected_ids = {plugin.id for plugin in plugins}
    extra = set(locked) - expected_ids
    if extra:
        messages.append("extension lock names disabled plugin(s): " + ", ".join(sorted(extra)))
    for plugin in plugins:
        row = locked.get(plugin.id)
        if row is None:
            messages.append(f"extension lock is missing enabled plugin {plugin.id}")
            continue
        if row.get("version") != plugin.version:
            messages.append(
                f"extension lock pins {plugin.id}@{row.get('version')}, linked bundle is {plugin.version}"
            )
        if row.get("path") != str(plugin.root):
            messages.append(f"extension lock path drift for {plugin.id}")
        if row.get("sha256") != _bundle_hash(plugin):
            messages.append(
                f"extension bundle content drift for {plugin.id}; review changes, then re-enable"
            )
    return messages


def enabled_plugins(root: Path) -> list[Plugin]:
    return [resolve_plugin(pin) for pin in _scope_pins(root)]


def enable_plugin(root: Path, value: str) -> Plugin:
    plugin = resolve_plugin(value)
    pins = [pin for pin in _scope_pins(root) if pin.rpartition("@")[0] != plugin.id]
    pins.append(plugin.pin)
    pins.sort()
    _save_scope_pins(root, pins)
    _write_lock(root, enabled_plugins(root))
    return plugin


def disable_plugin(root: Path, plugin_id: str) -> bool:
    old = _scope_pins(root)
    new = [pin for pin in old if pin.rpartition("@")[0] != plugin_id]
    if new == old:
        return False
    _save_scope_pins(root, new)
    _write_lock(root, enabled_plugins(root))
    return True


def plugin_data(plugin: Plugin, root: Path | None = None) -> dict:
    enabled = root is not None and plugin.id in {
        pin.rpartition("@")[0] for pin in _scope_pins(root)
    }
    return {
        "id": plugin.id, "version": plugin.version, "pin": plugin.pin,
        "summary": plugin.summary, "license": plugin.license,
        "requires_flip": plugin.requires_flip, "capabilities": plugin.capabilities,
        "path": str(plugin.root),
        "cataloged": False,  # core has no network catalog in this release
        "materialized": True, "linked": True, "valid": True, "enabled": enabled,
        "exercised": False,  # `filter test` is a receipt, not a sticky assertion
        "exports": plugin.exports,
        "filters": [handler_data(handler) for handler in plugin.handlers],
    }


def registry_rows(root: Path | None = None) -> list[dict]:
    """Every registry entry, including broken materialization/validation."""
    enabled_ids = set()
    if root is not None:
        enabled_ids = {pin.rpartition("@")[0] for pin in _scope_pins(root)}
    rows: list[dict] = []
    for plugin_id, entry in sorted(_read_registry().items()):
        raw_path = entry.get("path") if isinstance(entry, dict) else None
        path = Path(str(raw_path)).resolve() if raw_path else None
        try:
            if path is None:
                raise SystemExit("registry entry has no path")
            plugin = load_plugin(path)
            deep_validate_plugin(plugin)
            row = plugin_data(plugin, root)
        except SystemExit as exc:
            row = {
                "id": plugin_id, "version": entry.get("version") if isinstance(entry, dict) else None,
                "pin": f"{plugin_id}@{entry.get('version')}" if isinstance(entry, dict) else plugin_id,
                "summary": "", "path": str(path) if path else str(raw_path or ""),
                "cataloged": False, "materialized": bool(path and path.exists()),
                "linked": True, "valid": False, "enabled": plugin_id in enabled_ids,
                "exercised": False, "exports": {}, "filters": [], "error": str(exc),
            }
        rows.append(row)
    return rows


def handler_data(handler: Handler) -> dict:
    return {
        "id": handler.qualified_id, "hook": handler.hook,
        "protocol": handler.protocol, "command": handler.command,
        "needs": handler.needs, "before": handler.before, "after": handler.after,
        "timeout": handler.timeout,
    }


def _ordered(handlers: list[Handler]) -> list[Handler]:
    by_id = {handler.qualified_id: handler for handler in handlers}
    short = {handler.id: handler.qualified_id for handler in handlers
             if sum(other.id == handler.id for other in handlers) == 1}
    edges: dict[str, set[str]] = {name: set() for name in by_id}

    def resolve(name: str) -> str | None:
        return name if name in by_id else short.get(name)

    for handler in handlers:
        here = handler.qualified_id
        for name in handler.after:
            target = resolve(name)
            if target:
                edges[here].add(target)
        for name in handler.before:
            target = resolve(name)
            if target:
                edges[target].add(here)
    ordered: list[Handler] = []
    remaining = set(by_id)
    while remaining:
        ready = sorted(name for name in remaining if not (edges[name] & remaining))
        if not ready:
            raise SystemExit(
                "extension handler ordering cycle: " + ", ".join(sorted(remaining))
            )
        for name in ready:
            ordered.append(by_id[name])
            remaining.remove(name)
    return ordered


def handlers(root: Path, hook: str | None = None) -> list[Handler]:
    found = [handler for plugin in enabled_plugins(root) for handler in plugin.handlers
             if hook is None or handler.hook == hook]
    return _ordered(found)


def _command(handler: Handler) -> list[str]:
    command = list(handler.command)
    first = command[0]
    if first.startswith(".") or "/" in first:
        command[0] = str(_inside(resolve_plugin(handler.plugin_id), first))
    return command


def run_handler(handler: Handler, payload: dict) -> dict:
    envelope = {"protocol": PROTOCOL, "hook": handler.hook,
                "handler": handler.qualified_id, "input": payload}
    env = dict(os.environ)
    env["FLIP_PLUGIN_ID"] = handler.plugin_id
    try:
        completed = subprocess.run(
            _command(handler), input=json.dumps(envelope, ensure_ascii=False), text=True,
            capture_output=True, cwd=handler.plugin_root, env=env,
            timeout=handler.timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from None
    if completed.returncode != 0:
        detail = " ".join(completed.stderr.strip().split())[:300]
        raise RuntimeError(f"exit {completed.returncode}" + (f": {detail}" if detail else ""))
    if len(completed.stdout.encode()) > MAX_OUTPUT:
        raise RuntimeError(f"output exceeds {MAX_OUTPUT} bytes")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON output: {exc}") from None
    if not isinstance(result, dict):
        raise RuntimeError("output must be one JSON object")
    if result.get("protocol", PROTOCOL) != PROTOCOL:
        raise RuntimeError("output protocol does not match flip-filter/1")
    return result


def _scope_payload(root: Path) -> dict:
    return {"root": str(root.resolve()), "kind": _scope_kind(root)}


def _scope_kind(root: Path) -> str:
    from . import beat, workspace
    from .util import is_notebook_root
    if is_notebook_root(root):
        return "notebook"
    if beat.is_beat_root(root):
        return "beat"
    if workspace.is_workspace_root(root):
        return "workspace"
    return "unknown"


def _candidate(row: object, handler: Handler) -> dict:
    if not isinstance(row, dict):
        raise RuntimeError("frontier item must be an object")
    required = ("lane", "id", "text", "why")
    missing = [key for key in required if not str(row.get(key) or "").strip()]
    if missing:
        raise RuntimeError("frontier item missing " + ", ".join(missing))
    out = dict(row)
    out.setdefault("notebook", "")
    out["extension"] = handler.qualified_id
    return out


def apply_frontier(root: Path, data: dict) -> dict:
    items = list(data.get("items", []))
    trace: list[dict] = [{"handler": "flip/core", "hook": "frontier.provide@1",
                          "result": "provided", "items": len(items)}]
    base = {"scope": _scope_payload(root), "policy": data.get("selection", [])}
    for handler in handlers(root, "frontier.provide@1"):
        try:
            result = run_handler(handler, base | {"items": items})
            if result.get("decline"):
                trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                              "result": "declined", "reason": result.get("reason", "")})
                continue
            added = [_candidate(row, handler) for row in result.get("items", [])]
            items.extend(added)
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "provided", "items": len(added)})
        except (RuntimeError, SystemExit) as exc:
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "error-skipped", "error": str(exc)})
    for handler in handlers(root, "frontier.filter@1"):
        before = len(items)
        try:
            result = run_handler(handler, base | {"items": items})
            if result.get("decline"):
                trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                              "result": "declined", "reason": result.get("reason", "")})
                continue
            raw_items = result.get("items")
            if not isinstance(raw_items, list):
                raise RuntimeError("frontier filter output needs an items list")
            items = [_candidate(row, handler) for row in raw_items]
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "filtered", "before": before, "after": len(items),
                          "reasons": _strings(result.get("reasons"))})
        except (RuntimeError, SystemExit) as exc:
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "error-skipped", "error": str(exc)})
    out = dict(data)
    out["items"] = items
    out["total"] = len(items)
    out["trace"] = trace
    return out


def provide_context(root: Path, selected: dict | None = None) -> tuple[list[dict], list[dict]]:
    context: list[dict] = []
    trace: list[dict] = []
    for handler in handlers(root, "context.provide@1"):
        try:
            result = run_handler(handler, {"scope": _scope_payload(root), "selected": selected})
            refs = result.get("context", [])
            if not isinstance(refs, list):
                raise RuntimeError("context provider output needs a context list")
            context.extend(dict(ref) for ref in refs if isinstance(ref, dict))
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "provided", "items": len(refs)})
        except (RuntimeError, SystemExit) as exc:
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "error-skipped", "error": str(exc)})
    return context, trace


def filter_receipt(root: Path, receipt: dict) -> tuple[dict, list[dict]]:
    current = dict(receipt)
    trace: list[dict] = []
    for handler in handlers(root, "receipt.filter@1"):
        try:
            result = run_handler(handler, {"scope": _scope_payload(root), "receipt": current})
            value = result.get("receipt")
            if not isinstance(value, dict):
                raise RuntimeError("receipt filter output needs a receipt object")
            current = value
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "filtered"})
        except (RuntimeError, SystemExit) as exc:
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "error-skipped", "error": str(exc)})
    return current, trace


def run_checks(root: Path) -> tuple[list[dict], list[dict]]:
    findings: list[dict] = []
    trace: list[dict] = []
    for handler in handlers(root, "check.provide@1"):
        try:
            result = run_handler(handler, {"scope": _scope_payload(root)})
            rows = result.get("findings", [])
            if not isinstance(rows, list):
                raise RuntimeError("check provider output needs a findings list")
            for row in rows:
                if not isinstance(row, dict) or not row.get("message"):
                    raise RuntimeError("each extension finding needs message")
                findings.append(dict(row) | {"handler": handler.qualified_id})
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "provided", "items": len(rows)})
        except (RuntimeError, SystemExit) as exc:
            trace.append({"handler": handler.qualified_id, "hook": handler.hook,
                          "result": "error", "error": str(exc)})
    return findings, trace


def inventory(root: Path | None = None) -> list[dict]:
    rows: list[dict] = []
    enabled = {plugin.id for plugin in enabled_plugins(root)} if root is not None else set()
    for plugin in linked_plugins():
        for noun, rels in sorted(plugin.exports.items()):
            for rel in rels:
                rows.append({"type": noun.rstrip("s"), "id": f"{plugin.id}/{Path(rel).stem}",
                             "plugin": plugin.id, "path": rel, "enabled": plugin.id in enabled})
        for handler in plugin.handlers:
            rows.append({"type": "filter", "id": handler.qualified_id,
                         "plugin": plugin.id, "hook": handler.hook,
                         "enabled": plugin.id in enabled})
    return rows


def find_handler(value: str, root: Path | None = None) -> Handler:
    pool = handlers(root) if root is not None else [h for p in linked_plugins() for h in p.handlers]
    exact = [handler for handler in pool if handler.qualified_id == value]
    if not exact:
        exact = [handler for handler in pool if handler.id == value]
    if len(exact) != 1:
        known = ", ".join(handler.qualified_id for handler in pool) or "(none)"
        raise SystemExit(f"filter '{value}' is unknown or ambiguous; known: {known}")
    return exact[0]


def test_handler(handler: Handler, fixture: Path) -> dict:
    try:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{fixture}: invalid JSON fixture: {exc}") from None
    if not isinstance(payload, dict):
        raise SystemExit(f"{fixture}: fixture must be one JSON object")
    return run_handler(handler, payload)


__all__ = [
    "HOOKS", "Plugin", "Handler", "apply_frontier", "definition_exports",
    "deep_validate_plugin", "disable_plugin", "enable_plugin", "enabled_plugins", "filter_receipt",
    "find_handler", "handler_data", "handlers", "inventory", "link_plugin",
    "linked_plugins", "load_plugin", "plugin_data", "provide_context", "resolve_plugin",
    "registry_rows", "run_checks", "run_handler", "test_handler", "unlink_plugin",
    "validate_plugin",
    "validate_lock",
]
