"""Integration roles — flip's deployment-neutral plugin layer (SPEC §15–16).

flip shells out to external tools through a small set of *roles*, each a
namespaced table in ``$FLIP_HOME/config.toml`` and a thin command protocol.
flip defines the protocol; the tools that fill each role live only in user
configuration, never in this package.

Roles:
  ``[fetchers]``   capture: a target (url/id/file) → local bytes + custody
  ``[research]``   acquire: a query → candidate leads / cited synthesis
  ``[knowledge]``  recall:  a query → what the deployment already holds locally

All three share one runner. Placeholders substituted into a command template:
``{url}`` the target as given · ``{id}`` the target with a leading ``doi:``
stripped · ``{query}`` a research/recall question · ``{dest}`` the capture
directory. A command that writes files uses ``{dest}``; a stdout-only command
may omit it and flip preserves stdout. Every failure is a one-line SystemExit.

Config forms per key (all back-compat with the bare-string 0.6 form):
  ``web = "your-fetcher {url} {dest}"``            bare string
  ``web = { cmd = "…", needs = ["cookies"] }``     inline table (advisory needs)
  ``[fetchers.web]`` with named sub-keys           variants selectable via --via
      ``default = "…"`` / ``browser = { cmd = "…" }``  (a table with a ``cmd``
      key is a single fetcher, not a variant map)

Return envelope (optional, capture only): if a captured ``flip.json`` — or a
JSON stdout capture — carries a top-level ``flip`` object, its neutral,
all-optional keys are harvested by the caller. Absence changes nothing.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Neutral return-envelope keys a tool may hand back (all optional). Kept small
# and deployment-agnostic; unknown keys are ignored, so tools/adapters can carry
# extra fields without coupling flip to them.
ENVELOPE_KEYS = (
    "title",             # human name for the capture
    "canonical_url",     # resolved/canonical location (after redirects)
    "retrieved_at",      # ISO-8601 UTC instant the tool fetched it
    "strategy",          # which internal strategy/provider succeeded
    "status",            # success | paywalled | failed | …
    "mime",              # content type of the primary artifact
    "from_cache",        # True when served from a shared store, not a fresh fetch
    "independence_hint", # tool's guess; a lead for grading, never the grade
    "freshness_hint",    # tool's guess; a lead for grading, never the grade
    "sub_resources",     # [{local, url}] accepted-and-recorded, not acted on
    "backend_ref",       # opaque store/corpus id, passed through to provenance
)

# Per-role guidance used to build actionable "not configured" errors. The
# example tool name is always a schematic placeholder — flip never names a
# deployment's real tools.
_ROLE_TOOL = {
    "fetchers": "your-fetcher",
    "research": "your-research-tool",
    "knowledge": "your-knowledge-tool",
}


def config_path() -> Path:
    return Path(os.environ.get("FLIP_HOME", "~/.flip")).expanduser() / "config.toml"


def _load_config() -> dict | None:
    """Parse ``$FLIP_HOME/config.toml`` → dict, or None when it doesn't exist."""
    config = config_path()
    if not config.is_file():
        return None
    try:
        return tomllib.loads(config.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{config}: invalid TOML: {e}") from None


def _example(role: str, key: str) -> str:
    """A schematic stanza a user can paste and adapt for `role.key`."""
    tool = _ROLE_TOOL.get(role, "your-tool")
    if role == "fetchers":
        placeholder = "{id}" if key == "paper" else "{url}"
        example = f"{tool} {placeholder} {{dest}}"
    else:
        example = f"{tool} {{query}}"
    return f'[{role}]\n{key} = "{example}"'


def _guidance(role: str, key: str) -> str:
    stanza = _example(role, key)
    return f"{stanza}\n(replace '{_ROLE_TOOL.get(role, 'your-tool')}' with your command)"


@dataclass
class Resolved:
    """A configured command chosen for one (role, key[, variant])."""

    role: str
    key: str
    template: str
    name: str | None = None          # variant name, when --via selected one
    needs: list[str] = field(default_factory=list)  # advisory capabilities


def _normalize_entry(role: str, key: str, entry, via: str | None) -> Resolved:
    """Turn a config value (string / inline table / variant map) into a Resolved."""
    if isinstance(entry, str):
        if via:
            raise SystemExit(
                f"--via {via!r} given, but [{role}].{key} is a single command, not "
                f"named variants; drop --via or define variants under [{role}.{key}]"
            )
        return Resolved(role=role, key=key, template=entry.strip())
    if isinstance(entry, dict):
        if "cmd" in entry:  # inline table: one fetcher with options
            if via:
                raise SystemExit(
                    f"--via {via!r} given, but [{role}].{key} is a single command, not "
                    f"named variants; drop --via or define variants under [{role}.{key}]"
                )
            cmd = entry.get("cmd")
            if not isinstance(cmd, str) or not cmd.strip():
                raise SystemExit(f"[{role}].{key}.cmd must be a non-empty string")
            needs = [str(n) for n in entry.get("needs", [])]
            return Resolved(role=role, key=key, template=cmd.strip(), needs=needs)
        # variant map: pick by name (--via), else "default", else the only/first
        if not entry:
            raise SystemExit(f"[{role}].{key} is empty — configure a command")
        name = via or ("default" if "default" in entry else next(iter(entry)))
        if name not in entry:
            avail = ", ".join(entry)
            raise SystemExit(
                f"no variant {name!r} under [{role}].{key} (have: {avail}) — "
                f"pass --via with one of them"
            )
        chosen = _normalize_entry(role, key, entry[name], via=None)
        chosen.name = name
        return chosen
    raise SystemExit(f"[{role}].{key} must be a string or table, not {type(entry).__name__}")


def resolve(role: str, key: str, via: str | None = None) -> Resolved:
    """Resolve (role, key) to a configured command; actionable error if absent.

    `key` is a fetcher kind ("web", "paper", …) or a research/knowledge verb
    ("find", "ask", "recall").
    """
    data = _load_config()
    if data is None:
        raise SystemExit(
            f"no {role} command configured for '{key}' ({config_path()} does not "
            f"exist) — create it with a stanza like:\n{_guidance(role, key)}"
        )
    entry = data.get(role, {}).get(key)
    if entry is None or (isinstance(entry, str) and not entry.strip()):
        raise SystemExit(
            f"no {role} command configured for '{key}' in {config_path()} — add a "
            f"stanza like:\n{_guidance(role, key)}"
        )
    return _normalize_entry(role, key, entry, via)


def _tokenize_template(template: str) -> list[str]:
    """Split a command template into argv tokens.

    posix mode everywhere except Windows: posix-mode shlex treats backslashes
    as escapes, which mangles paths like C:\\Tools\\fetch.exe in a Windows
    user's config.toml.
    """
    return shlex.split(template, posix=(os.name != "nt"))


def _build_argv(template: str, placeholders: dict[str, str]) -> list[str]:
    argv = []
    for tok in _tokenize_template(template):
        for name, value in placeholders.items():
            tok = tok.replace("{" + name + "}", value)
        argv.append(tok)
    return argv


def tool_version(tool: str) -> str | None:
    """Best effort ``<tool> --version``: first output line on success, else None."""
    try:
        proc = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip() or proc.stderr.strip()
    return out.splitlines()[0] if out else None


def _exec(argv: list[str], cwd: Path, noun: str, key: str) -> subprocess.CompletedProcess:
    """Run a resolved command; uniform SystemExit on missing-binary / nonzero."""
    try:
        proc = subprocess.run(argv, capture_output=True, cwd=cwd)
    except FileNotFoundError:
        raise SystemExit(
            f"{noun} '{argv[0]}' for '{key}' not found on PATH — install it or fix "
            f"the command in {config_path()}"
        ) from None
    if proc.returncode != 0:
        output = proc.stderr or proc.stdout
        lines = output.decode("utf-8", errors="replace").strip().splitlines()
        detail = lines[-1] if lines else "no output"
        raise SystemExit(
            f"{noun} for '{key}' failed (exit {proc.returncode}): {shlex.join(argv)} — {detail}"
        )
    return proc


def _harvest_envelope(files: list[Path], stdout: bytes) -> dict | None:
    """Pull the neutral ``flip`` envelope from a captured flip.json or JSON stdout.

    Returns only the whitelisted ENVELOPE_KEYS (all optional); None when no
    envelope is present. Malformed JSON is ignored, never fatal — a tool that
    doesn't opt in behaves exactly as before.
    """
    blobs: list[bytes] = [f.read_bytes() for f in files if f.name == "flip.json"]
    if not blobs and stdout:
        blobs.append(stdout)
    for raw in blobs:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("flip"), dict):
            env = data["flip"]
            return {k: env[k] for k in ENVELOPE_KEYS if k in env}
    return None


@dataclass
class CaptureRun:
    files: list[Path]
    tool: str
    tool_version: str | None
    strategy: str
    envelope: dict | None


def run_capture(resolved: Resolved, root: Path, source_id: str, target: str) -> CaptureRun:
    """Run a capture command into ``sources/raw/<source_id>/``.

    Files the command writes under ``{dest}`` are the capture; if it wrote
    nothing and its template omits ``{dest}``, its stdout is preserved as
    ``capture.json`` / ``capture.txt``. Returns the new files plus the tool's
    identity and any harvested return envelope.
    """
    dest = root / "sources" / "raw" / source_id
    dest.mkdir(parents=True, exist_ok=True)
    before = {p for p in dest.rglob("*") if p.is_file()}
    template = resolved.template
    captures_stdout = "{dest}" not in template
    bare = target[4:] if target.lower().startswith("doi:") else target
    argv = _build_argv(template, {"url": target, "id": bare, "query": target, "dest": str(dest)})
    proc = _exec(argv, root, "fetcher", resolved.key)

    new = [p for p in dest.rglob("*") if p.is_file() and p not in before]
    if not new and captures_stdout and proc.stdout:
        suffix = ".json" if proc.stdout.lstrip().startswith((b"{", b"[")) else ".txt"
        captured = dest / f"capture{suffix}"
        captured.write_bytes(proc.stdout)
        new = [captured]
    if not new:
        raise SystemExit(
            f"fetcher for '{resolved.key}' wrote nothing to {dest} and emitted no "
            f"stdout — make sure its command in {config_path()} uses the {{dest}} "
            "placeholder or emits the captured artifact on stdout"
        )
    envelope = _harvest_envelope(new, proc.stdout)
    strategy = "config"
    if envelope and isinstance(envelope.get("strategy"), str):
        strategy = envelope["strategy"]
    return CaptureRun(
        files=new, tool=argv[0], tool_version=tool_version(argv[0]),
        strategy=strategy, envelope=envelope,
    )


@dataclass
class QueryRun:
    raw: str                 # the tool's stdout, verbatim (custody of the answer)
    data: object             # parsed JSON, or None when stdout wasn't JSON
    tool: str
    tool_version: str | None


def run_query(resolved: Resolved, root: Path, query: str) -> QueryRun:
    """Run a research/knowledge command with ``{query}``; capture its stdout.

    Query tools emit to stdout (no capture dir). Returns the raw text plus a
    best-effort JSON parse; the caller normalizes and decides where it lands.
    """
    noun = "research tool" if resolved.role == "research" else "knowledge tool"
    argv = _build_argv(resolved.template, {"query": query, "url": query, "id": query})
    proc = _exec(argv, root, noun, resolved.key)
    text = proc.stdout.decode("utf-8", errors="replace")
    try:
        data = json.loads(text) if text.strip() else None
    except (json.JSONDecodeError, ValueError):
        data = None
    return QueryRun(raw=text, data=data, tool=argv[0], tool_version=tool_version(argv[0]))
