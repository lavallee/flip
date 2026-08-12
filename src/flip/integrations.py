"""Integration roles — flip's deployment-neutral plugin layer (SPEC §15–16).

flip shells out to external tools through a small set of *roles*, each a
namespaced table in ``$FLIP_HOME/config.toml`` and a thin command protocol.
flip defines the protocol; the tools that fill each role live only in user
configuration, never in this package.

Roles:
  ``[fetchers]``   capture: a target (url/id/file) → local bytes + custody
  ``[extractors]`` extract: raw bytes → a readable text derivative
  ``[research]``   acquire: a query → candidate leads / cited synthesis
  ``[knowledge]``  recall:  a query → what the deployment already holds locally

All four share one runner. Placeholders substituted into a command template:
``{url}`` the target as given · ``{id}`` the target with a leading identifier
scheme stripped (``doi:``, ``arxiv:``, ``pmid:``, ``pmcid:``, ``hdl:``,
``isbn:``, ``urn:``) · ``{query}`` a research/recall question · ``{dest}`` the capture
directory · ``{src}`` the raw artifact to extract from · ``{out}`` the text
derivative's destination. A command that writes files uses ``{dest}``/``{out}``;
a stdout-only command may omit it and flip preserves stdout. A command that
cannot run, or fails, is a one-line SystemExit; a command that *succeeds* and
brings nothing back is an ``EmptyCapture`` (or, one layer down, an
``EmptyExtraction``) — a finding about the target, not a defect in the config.

``[extractors]`` is keyed by **media family** (``pdf``, ``html``, ``docx``,
``audio``), not by source kind: the input format is what picks the tool, and a
PDF is a PDF whether it was captured as a paper, a file, or a dataset.

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

# Identifier schemes stripped from ``{id}``. A resolver is handed the bare
# identifier because that is the form every one of them accepts; the schemed
# form is what a human writes and what several resolvers silently miss (given
# "arXiv:2606.15136", paperboy title-searches the string and returns unrelated
# papers, then exits 0 — a clean run that captures nothing, which flip reports
# as EmptyCapture, i.e. as a finding about the document rather than the bug it
# actually is). {url} still carries the target exactly as given.
ID_SCHEMES = ("doi:", "arxiv:", "pmid:", "pmcid:", "hdl:", "isbn:", "urn:")


def bare_id(target: str) -> str:
    """``target`` with a known identifier scheme stripped, for ``{id}``.

    Case-insensitive, and only for the schemes in ``ID_SCHEMES`` — an unknown
    prefix is left alone rather than guessed at, since ``{id}`` is also how a
    bare accession or a local key reaches a resolver.
    """
    lowered = target.lower()
    for scheme in ID_SCHEMES:
        if lowered.startswith(scheme):
            return target[len(scheme):].lstrip()
    return target


# Neutral return-envelope keys a tool may hand back (all optional). Kept small
# and deployment-agnostic; unknown keys are ignored, so tools/adapters can carry
# extra fields without coupling flip to them.
ENVELOPE_KEYS = (
    "title",             # human name for the capture
    "canonical_url",     # resolved/canonical location (after redirects)
    "retrieved_at",      # ISO-8601 UTC instant the tool fetched it
    "strategy",          # the capture METHOD used (SPEC §5.1), not the tool's name
    "user_agent",        # what the fetcher presented itself as, verbatim — the
                         #   record must never lie about the technique (SPEC §5.1)
    "attempts",          # >1 when a transient failure had to be retried through
    "archived_at",       # for archive-replay: WHEN the captured copy is from,
                         #   which is not when we retrieved it (SPEC §5.1)
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
    "extractors": "your-extractor",
    "research": "your-research-tool",
    "knowledge": "your-knowledge-tool",
}


ROLES = ("fetchers", "extractors", "research", "knowledge")


def config_path() -> Path:
    return Path(os.environ.get("FLIP_HOME", "~/.flip")).expanduser() / "config.toml"


# A starter config `flip config init` writes. The web lane defaults to the
# bundled `flip-fetch` helper so capture works out of the box with no external
# tool; everything else is commented, ready to uncomment and adapt. flip never
# ships a deployment's tools — only this schematic scaffold.
STARTER_CONFIG = '''\
# flip integration config — commands flip runs to capture sources and answer
# research queries. Placeholders: {url} target · {id} doi-stripped · {query}
# question · {dest} capture directory. See docs/quickstart.md.

[fetchers]
# Out-of-the-box web capture via the bundled zero-dependency helper. It climbs
# the first two rungs of the capture ladder (SPEC §5.1): a GET, and
# backoff-retry on 429/502/503/504 and timeouts.
web = "flip-fetch {url} {dest}"

# flip-fetch's defaults are an opinion for the common case — directed capture
# of one named document — not a rule (SPEC §5.1). Set your own policy here and
# it applies to every capture on this lane; the ledger records what was
# actually used either way. `flip-fetch --help` lists the knobs.
#
# web = "flip-fetch --user-agent identify {url} {dest}"   # announce ourselves
# web = "flip-fetch --user-agent 'AcmeResearchBot/1.0 (+https://acme.example/bot)' {url} {dest}"
# web = "flip-fetch --min-interval 10 {url} {dest}"       # gentler on a fragile host
# web = "flip-fetch --min-interval 0 {url} {dest}"        # no pacing (your own infra)
# ...or swap in a ubiquitous tool, or a purpose-built fetcher:
# web = "curl --fail --location --silent --show-error {url} --output {dest}/capture.html"
# web = "wget --quiet --output-document {dest}/capture.html {url}"
# media = "yt-dlp {url} --output {dest}/%(title)s.%(ext)s"
# social = "your-x-fetcher {url} {dest}"

# Scholarly capture, no external tool needed. Crossref for metadata, then
# Unpaywall for a legal open-access full text, then arXiv for arXiv ids.
# Unpaywall REQUIRES a real address and refuses without one; it also opts you
# into Crossref's polite pool. Put yours in and uncomment:
# paper = "flip-fetch --method publisher-api --email you@example.com {id} {dest}"

# Named lanes for the higher rungs, reachable with `--via <name>`. A 403 on the
# live URL is a decision about that request, not a verdict on the source —
# these are the methods that get past it.
#
# [fetchers.web]
# archive  = "flip-fetch --method archive-replay {url} {dest}"   # bundled: a web
#                                                 #   archive's copy, raw bytes
# render   = "your-render-fetcher {url} {dest}"   # headless browser, executes JS
# faithful = "your-archiver {url} {dest}"         # assets inlined into one file
#                                                 #   (monolith is CC0; SingleFile CLI is AGPL —
#                                                 #    both are invoked as subprocesses here)
#
# Have a fetcher report `strategy` in its flip.json envelope as a capture
# METHOD from SPEC §5.1 (`archive-replay`, `browser-render`,
# `self-contained-archive`, …), never as its own name. Methods travel between
# deployments; tool names don't, and `tool`/`tool_version` already record the
# actor. `flip doctor` flags a strategy that reads like a tool name.

# --- [extractors] — raw bytes -> a readable text derivative (SPEC §5.5) ---
#
# Keyed by MEDIA FAMILY, not by source kind: the input format picks the tool,
# so a PDF is a PDF whether it was captured as a paper, a file, or a dataset.
# Placeholders: {src} the raw artifact · {out} the destination text file (omit
# it and flip captures stdout, exactly like {dest} on a fetcher) · {id} the
# source id. `flip extract <ID>` writes sources/text/<ID>.txt and appends one
# row to derived/_derivations.jsonl.
#
# flip ships NO extractor and defines no default lane. flip-fetch can be
# bundled because it is stdlib-only; a PDF/OCR extractor cannot, and flip must
# not carry an opinion about PDF libraries in its package (§16). Everything
# below is commented on purpose — pick your own and uncomment.
#
# [extractors]
# pdf   = "your-extractor {src} {out}"
# html  = "your-extractor {src} {out}"
# docx  = "your-extractor {src} {out}"
# audio = "your-transcriber {src} {out}"
#
# Named lanes, reachable with `flip extract <ID> --via <name>`. Name a lane
# after the extraction METHOD it uses (`text-layer`, `layout-text`, `ocr`,
# `markup-strip`, `structured`, `transcript` — SPEC §5.5) and flip records the
# method for you; otherwise pass `--method` yourself. A quotation recovered by
# OCR is not the same evidence as one lifted from a publisher's text layer, and
# the ledger row is the only place that difference can be written down.
#
# [extractors.pdf]
# text-layer = "pdftotext -layout {src} {out}"     # the document's own text
# ocr        = "your-ocr-tool {src} {out}"         # rendered and recognized
#
# Two field notes from choosing one of these, because they are the failures
# that exit 0:
#
#  - An OCR tool that downloads its language model on first use can race its
#    own workers on a cold cache. One measured run lost 9 of 94 pages and
#    exited 0; pointing it at the system tessdata (a `--tessdata-path`-shaped
#    flag) fixed it and cut a 94-page scan from 129s to 28s. Pin the model path
#    in the lane, then check the page count in the derivation row.
#  - Check what your extractor talks to. Some OCR wrappers have an opt-in
#    "OCR server URL" that POSTs rendered page images to an arbitrary endpoint.
#    Default-off is not the same as absent — a captured source may be
#    confidential, and this lane is the one place bytes leave the machine.
#  - A classifier is not an extractor. A library that answers "is this scanned,
#    which pages need OCR?" in milliseconds may still return 7 words from a
#    44-page document when asked for the text. Useful upstream; disqualifying
#    here. `flip extract` refuses at 0 words and warns under 25 words/page.

# [research]                     # a question -> candidate leads / cited synthesis
# find = "your-research-tool {query}"
# ask = "your-research-tool {query}"

# [knowledge]                    # a question -> what you already hold locally
# recall = "your-knowledge-tool {query}"
'''


def write_starter_config(force: bool = False) -> tuple[Path, bool]:
    """Write STARTER_CONFIG to $FLIP_HOME/config.toml. Returns (path, written).

    Refuses to clobber an existing config unless `force`; then `written` is
    False and the caller reports that the file was left as-is.
    """
    path = config_path()
    if path.exists() and not force:
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STARTER_CONFIG, encoding="utf-8")
    return path, True


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
    elif role == "extractors":
        example = f"{tool} {{src}} {{out}}"
    else:
        example = f"{tool} {{query}}"
    return f'[{role}]\n{key} = "{example}"'


def _guidance(role: str, key: str) -> str:
    stanza = _example(role, key)
    tail = f"(replace '{_ROLE_TOOL.get(role, 'your-tool')}' with your command)"
    if role == "fetchers":
        # the fetchers lane has a batteries-included path; point there first
        tail = ("(run `flip config init` for a starter config with a bundled "
                "web fetcher, or replace 'your-fetcher' with your own command)")
    elif role == "extractors":
        # And this one deliberately does NOT. flip ships `flip-fetch` because it
        # is stdlib-only; a PDF/OCR extractor is not, and flip must not acquire
        # an opinion about PDF libraries inside its own package (§16). So the
        # error names the operator's file and the placeholders, and stops.
        tail = ("(flip ships no extractor and has no default lane — the tool is "
                "yours to choose. Placeholders: {src} the raw artifact · {out} the "
                "destination text file, omit it and stdout is captured · {id} the "
                "source id. `flip config init` writes a commented [extractors] "
                "stanza to start from.)")
    return f"{stanza}\n{tail}"


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


def configured_lanes() -> list[dict]:
    """Every (role, key, variant) lane the operator has configured, in order.

    Read-only introspection of `$FLIP_HOME/config.toml`: one row per lane with
    ``role``, ``key``, ``variant`` (None for a single command), ``command``
    (the template verbatim) and ``needs``. Never raises — a missing or
    unparseable config is simply no lanes — because every caller is either
    *reporting* what exists (`flip config show`) or building an error message,
    and neither may fail on top of the failure it is describing.

    This is how flip names what IS available on a machine without knowing what
    fills a role (SPEC §16): the command it prints is the operator's own.
    """
    try:
        data = _load_config() or {}
    except SystemExit:
        return []
    rows: list[dict] = []
    for role in ROLES:
        table = data.get(role)
        if not isinstance(table, dict):
            continue
        for key, entry in table.items():
            try:
                if isinstance(entry, dict) and "cmd" not in entry:
                    for variant in entry:
                        r = _normalize_entry(role, key, entry, via=variant)
                        rows.append({"role": role, "key": key, "variant": variant,
                                     "command": r.template, "needs": r.needs})
                    continue
                r = _normalize_entry(role, key, entry, via=None)
                rows.append({"role": role, "key": key, "variant": None,
                             "command": r.template, "needs": r.needs})
            except SystemExit:
                continue  # a malformed lane is `flip doctor`'s problem, not this one
    return rows


def capture_lanes() -> dict[str, list[str]]:
    """`[fetchers]` as {kind: [variant names]} — the capture lanes on this
    machine. A kind configured as a single command maps to an empty list."""
    lanes: dict[str, list[str]] = {}
    for row in configured_lanes():
        if row["role"] != "fetchers":
            continue
        names = lanes.setdefault(row["key"], [])
        if row["variant"]:
            names.append(row["variant"])
    return lanes


def extraction_lanes() -> dict[str, list[str]]:
    """`[extractors]` as {media family: [variant names]} — the derivation lanes
    on this machine. A family configured as a single command maps to an empty
    list. The twin of `capture_lanes`, and the only way flip knows whether a
    captured PDF *could* have a text derivative (doctor's `missing-derivative`)
    without knowing what tool would make it."""
    lanes: dict[str, list[str]] = {}
    for row in configured_lanes():
        if row["role"] != "extractors":
            continue
        names = lanes.setdefault(row["key"], [])
        if row["variant"]:
            names.append(row["variant"])
    return lanes


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


class EmptyCapture(SystemExit):
    """A capture command that ran clean (exit 0) and brought nothing back.

    Deliberately NOT the same event as a failure. A tool that exits 0 having
    written no files and printed nothing has *reported a finding*: at this rung,
    for this target, there was nothing to capture — gated, withdrawn, or simply
    not served to us. Until 0.17 flip called this a configuration error and sent
    the reader to debug a config that was fine, which is the one reading that
    makes the ladder (SPEC §5.1) invisible at the exact moment it is needed.

    A SystemExit subclass so every existing caller — and the CLI's exit code —
    behaves exactly as before; callers that can say something useful about
    *what to do next* catch it specifically and enrich the message.
    """

    def __init__(self, message: str, *, key: str, dest: Path, tool: str,
                 template: str, captures_stdout: bool) -> None:
        super().__init__(message)
        self.key = key
        self.dest = dest
        self.tool = tool
        self.template = template
        self.captures_stdout = captures_stdout


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

    Raises ``EmptyCapture`` when the command succeeded and produced nothing —
    a finding about the target, distinct from the ``SystemExit`` raised when
    the command could not run or failed.
    """
    dest = root / "sources" / "raw" / source_id
    dest.mkdir(parents=True, exist_ok=True)
    before = {p for p in dest.rglob("*") if p.is_file()}
    template = resolved.template
    captures_stdout = "{dest}" not in template
    argv = _build_argv(template, {"url": target, "id": bare_id(target), "query": target,
                                  "dest": str(dest)})
    proc = _exec(argv, root, "fetcher", resolved.key)

    new = [p for p in dest.rglob("*") if p.is_file() and p not in before]
    if not new and captures_stdout and proc.stdout:
        suffix = ".json" if proc.stdout.lstrip().startswith((b"{", b"[")) else ".txt"
        captured = dest / f"capture{suffix}"
        captured.write_bytes(proc.stdout)
        new = [captured]
    if not new:
        raise EmptyCapture(
            f"fetcher for '{resolved.key}' ran clean (exit 0) and brought nothing back "
            f"for {target!r} — it looked, and there was nothing here to capture",
            key=resolved.key, dest=dest, tool=argv[0], template=template,
            captures_stdout=captures_stdout,
        )
    envelope = _harvest_envelope(new, proc.stdout)
    strategy = "config"
    if envelope and isinstance(envelope.get("strategy"), str):
        strategy = envelope["strategy"]
    return CaptureRun(
        files=new, tool=argv[0], tool_version=tool_version(argv[0]),
        strategy=strategy, envelope=envelope,
    )


class EmptyExtraction(SystemExit):
    """An extract command that ran clean (exit 0) and produced no text.

    The exact sibling of ``EmptyCapture``, one layer down. A tool that exits 0
    having written no words has *reported a finding about the document*: this
    PDF has no text layer, this scan is images all the way down, this form is
    boxes. That is not a defect in the config, and presenting it as one sends
    the reader to debug a lane that is fine — after which they hand-roll a
    render-and-recognize loop with no derivation row, no hashes, and no record
    of which method produced the words they are about to quote.

    A SystemExit subclass so the CLI's exit code and every existing caller
    behave as before; callers that can say what to do next catch it
    specifically and enrich the message with the operator's own lanes (§16).
    """

    def __init__(self, message: str, *, key: str, src: Path, out: Path, tool: str,
                 template: str, captures_stdout: bool) -> None:
        super().__init__(message)
        self.key = key
        self.src = src
        self.out = out
        self.tool = tool
        self.template = template
        self.captures_stdout = captures_stdout


@dataclass
class ExtractionRun:
    out: Path
    text: str
    words: int
    tool: str
    tool_version: str | None
    captures_stdout: bool


def run_extraction(
    resolved: Resolved, root: Path, source_id: str, src: Path, out: Path
) -> ExtractionRun:
    """Run an extract command over one raw artifact into ``out``.

    Mirrors ``run_capture`` exactly, including the stdout rule: a template that
    names ``{out}`` is expected to write that file; a template that omits it is
    a stdout-only tool and flip preserves its stdout as ``out``.

    Raises ``EmptyExtraction`` when the command succeeded and produced no text —
    a finding about the document, distinct from the ``SystemExit`` raised when
    the command could not run or failed. **No file is left behind in that
    case**: whatever was on disk before the run is restored, because a
    zero-byte derivative is the one artifact that would read on disk as though
    the extraction had worked.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    template = resolved.template
    captures_stdout = "{out}" not in template
    argv = _build_argv(template, {"src": str(src), "out": str(out), "id": source_id})
    before = out.read_bytes() if out.is_file() else None

    # Clear the destination first, the same way run_capture only counts files
    # that were not in {dest} before. Without this, a command that promises
    # {out} and quietly writes nothing leaves the PREVIOUS derivative on disk,
    # and flip reads last week's words back as this run's output — a silent
    # failure wearing a fresh derivation row, which is the exact class of thing
    # this lane exists to catch.
    if not captures_stdout:
        out.unlink(missing_ok=True)
    try:
        proc = _exec(argv, root, "extractor", resolved.key)
    except SystemExit:
        if before is not None:
            out.write_bytes(before)
        raise
    if captures_stdout:
        out.write_bytes(proc.stdout)

    text = out.read_text(encoding="utf-8", errors="replace") if out.is_file() else ""
    words = len(text.split())
    if words == 0:
        if before is None:
            out.unlink(missing_ok=True)
        else:
            out.write_bytes(before)
        raise EmptyExtraction(
            f"extractor for '{resolved.key}' ran clean (exit 0) and produced no text "
            f"from {src.name} — it looked, and there was nothing here to read",
            key=resolved.key, src=src, out=out, tool=argv[0], template=template,
            captures_stdout=captures_stdout,
        )
    return ExtractionRun(
        out=out, text=text, words=words, tool=argv[0],
        tool_version=tool_version(argv[0]), captures_stdout=captures_stdout,
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
