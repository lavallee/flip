"""Source capture: fetcher routing, custody, provenance, the ledger (SPEC §5).

`add_source` is the write path for `flip add-source`: classify the target,
allocate a kind-prefixed id, capture bytes into sources/raw/ (builtin copy for
local files, a configured external fetcher for everything else), hash every
captured file into sources/_provenance.jsonl (append-only), and open a ledger
row graded "?". `grade_source` is the write path for `flip grade`: update the
judgment fields on an existing row — sources/ledger.jsonl is current-state,
git history is the temporal record.

Fetcher templates live in $FLIP_HOME/config.toml under [fetchers] (SPEC §14).
Placeholders: {url} = the target as given, {id} = the target with a leading
"doi:" stripped (for `doi-fetch {id}`-style tools), {dest} = the capture
directory sources/raw/<source id>/.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

from . import manifest
from .util import (
    append_jsonl,
    detect_actor,
    next_id,
    read_jsonl,
    require_notebook_root,
    sha256_file,
    utc_now,
    write_jsonl,
)

GRADES = ("A", "B", "C", "?")
INDEPENDENCE = ("original", "republisher", "derivative", "self-interested")
FRESHNESS = ("fresh", "dated")

# SPEC §3 naming rules: P papers · A articles/web · F files/datasets/documents ·
# T talks/transcripts · S when unkinded/unknown. D is reserved for decisions —
# source ids never use it, so a bare [F3]/[D2] cite is unambiguous (SPEC §9).
_ID_PREFIXES = {
    "paper": "P",
    "web": "A",
    "article": "A",
    "file": "F",
    "dataset": "F",
    "document": "F",
    "talk": "T",
    "transcript": "T",
}

_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")
_ARXIV_RE = re.compile(r"^(arxiv:)?\d{4}\.\d{4,5}(v\d+)?$", re.IGNORECASE)

_EXAMPLE_TEMPLATES = {
    "web": "single-file {url} --output {dest}",
    "paper": "doi-fetch {id} --dir {dest}",
}


def _classify(target: str) -> str:
    """Infer a source kind from the target when the caller didn't name one."""
    if Path(target).expanduser().exists():
        return "file"
    if target.startswith(("http://", "https://")):
        return "web"
    if target.lower().startswith("doi:") or _DOI_RE.match(target) or _ARXIV_RE.match(target):
        return "paper"
    raise SystemExit(
        f"can't classify '{target}' (not an existing file, http(s) URL, DOI, or arXiv id) — "
        "pass the kind explicitly, e.g. --kind web|paper|file|dataset|talk"
    )


def _config_path() -> Path:
    return Path(os.environ.get("FLIP_HOME", "~/.flip")).expanduser() / "config.toml"


def _fetcher_template(kind: str) -> str:
    """Look up the [fetchers] command template for a kind; actionable error if absent."""
    config = _config_path()
    example = _EXAMPLE_TEMPLATES.get(kind, "fetch-cmd {url} --output {dest}")
    stanza = f'[fetchers]\n{kind} = "{example}"'
    if not config.is_file():
        raise SystemExit(
            f"no fetcher configured for kind '{kind}' ({config} does not exist) — "
            f"create it with a stanza like:\n{stanza}"
        )
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"{config}: invalid TOML: {e}") from None
    template = data.get("fetchers", {}).get(kind)
    if not isinstance(template, str) or not template.strip():
        raise SystemExit(
            f"no fetcher configured for kind '{kind}' in {config} — add a stanza like:\n{stanza}"
        )
    return template.strip()


def _all_source_ids(root: Path) -> list[str]:
    """Every source id ever seen — ledger rows plus provenance events (ids never reused)."""
    ids = [r.get("id", "") for r in read_jsonl(root / "sources" / "ledger.jsonl")]
    ids += [e.get("source_id", "") for e in read_jsonl(root / "sources" / "_provenance.jsonl")]
    return [i for i in ids if i]


def _tool_version(tool: str) -> str | None:
    """Best effort `<tool> --version`: first output line on success, else None."""
    try:
        proc = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip() or proc.stderr.strip()
    return out.splitlines()[0] if out else None


def _capture_copy(root: Path, source_id: str, target: str) -> tuple[list[Path], str]:
    """builtin:copy — copy one local file verbatim into sources/raw/<id><suffix>.

    Returns ([copied path], origin file:// URI).
    """
    src = Path(target).expanduser()
    if src.is_dir():
        raise SystemExit(
            f"'{target}' is a directory — point at a single file, or configure a "
            f"[fetchers] command in {_config_path()} for multi-file captures"
        )
    if not src.is_file():
        raise SystemExit(f"no such file '{target}' — check the path, or pass a URL/DOI instead")
    raw_dir = root / "sources" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{source_id}{src.suffix}"
    shutil.copy2(src, dest)
    return [dest], src.resolve().as_uri()


def _tokenize_template(template: str) -> list[str]:
    """Split a fetcher template into argv tokens.

    posix mode everywhere except Windows: posix-mode shlex treats backslashes
    as escapes, which mangles paths like C:\\Tools\\fetch.exe in a Windows
    user's config.toml.
    """
    return shlex.split(template, posix=(os.name != "nt"))


def _run_fetcher(
    root: Path, source_id: str, kind: str, target: str, template: str
) -> tuple[list[Path], str]:
    """Run a configured fetcher into sources/raw/<id>/; return (new files, argv[0])."""
    dest = root / "sources" / "raw" / source_id
    dest.mkdir(parents=True, exist_ok=True)
    before = {p for p in dest.rglob("*") if p.is_file()}
    bare = target[4:] if target.lower().startswith("doi:") else target
    argv = [
        tok.replace("{url}", target).replace("{id}", bare).replace("{dest}", str(dest))
        for tok in _tokenize_template(template)
    ]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=root)
    except FileNotFoundError:
        raise SystemExit(
            f"fetcher '{argv[0]}' for kind '{kind}' not found on PATH — "
            f"install it or fix [fetchers] in {_config_path()}"
        ) from None
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout).strip().splitlines()
        detail = lines[-1] if lines else "no output"
        raise SystemExit(
            f"fetcher for kind '{kind}' failed (exit {proc.returncode}): "
            f"{shlex.join(argv)} — {detail}"
        )
    new = [p for p in dest.rglob("*") if p.is_file() and p not in before]
    if not new:
        raise SystemExit(
            f"fetcher for kind '{kind}' wrote nothing to {dest} — "
            f"make sure its template in {_config_path()} uses the {{dest}} placeholder"
        )
    return new, argv[0]


def add_source(root: Path, target: str, kind: str | None = None, note: str | None = None) -> dict:
    """Capture a source into the notebook; returns the new ledger row.

    Routes by kind: "file" (or any kind whose configured fetcher is
    "builtin:copy") copies the file verbatim; everything else runs the
    [fetchers] command from $FLIP_HOME/config.toml. Appends one provenance
    event per captured file, opens a grade-"?" ledger row, touches the
    manifest.
    """
    root = require_notebook_root(root)
    kind = kind or _classify(target)
    source_id = next_id(_ID_PREFIXES.get(kind, "S"), _all_source_ids(root))

    template = None if kind == "file" else _fetcher_template(kind)
    if template is None or template == "builtin:copy":
        files, origin = _capture_copy(root, source_id, target)
        tool, tool_version, strategy, url = "builtin:copy", None, "copy", origin
    else:
        files, tool = _run_fetcher(root, source_id, kind, target, template)
        tool_version, strategy, url = _tool_version(tool), "config", target

    ts = utc_now()
    actor = detect_actor()
    prov_path = root / "sources" / "_provenance.jsonl"
    for f in sorted(files):
        event: dict = {
            "ts": ts,
            "source_id": source_id,
            "url": url,
            "local_path": f.relative_to(root).as_posix(),
            "sha256": sha256_file(f),
            "bytes": f.stat().st_size,
            "tool": tool,
        }
        if tool_version:
            event["tool_version"] = tool_version
        event["strategy"] = strategy
        event["actor"] = actor
        if note:
            event["note"] = note
        append_jsonl(prov_path, event)

    largest = max(files, key=lambda p: p.stat().st_size)
    row: dict = {"id": source_id, "kind": kind}
    if strategy == "config":
        row["url"] = url  # for copies the origin path lives in provenance, not the ledger
    row.update(
        {
            "local": largest.relative_to(root).as_posix(),
            "grade": "?",
            "independence": "original",
            "freshness": "fresh",
            "status": "captured",
            "supports": [],
        }
    )
    if note:
        row["notes"] = note

    ledger_path = root / "sources" / "ledger.jsonl"
    rows = read_jsonl(ledger_path)
    rows.append(row)
    write_jsonl(ledger_path, rows)
    manifest.touch_updated(root)
    return row


def list_sources(root: Path) -> list[dict]:
    """All source ledger rows, in ledger order. Read-only (backs `flip source list`)."""
    root = require_notebook_root(root)
    return read_jsonl(root / "sources" / "ledger.jsonl")


def grade_source(
    root: Path,
    source_id: str,
    grade: str | None = None,
    independence: str | None = None,
    freshness: str | None = None,
    notes: str | None = None,
) -> dict:
    """Record source-quality judgments on an existing ledger row; returns the row."""
    root = require_notebook_root(root)
    for name, value, allowed in (
        ("grade", grade, GRADES),
        ("independence", independence, INDEPENDENCE),
        ("freshness", freshness, FRESHNESS),
    ):
        if value is not None and value not in allowed:
            raise SystemExit(f"invalid {name} '{value}' (one of: {', '.join(allowed)})")
    ledger_path = root / "sources" / "ledger.jsonl"
    rows = read_jsonl(ledger_path)
    updates = {"grade": grade, "independence": independence, "freshness": freshness, "notes": notes}
    for row in rows:
        if row.get("id") == source_id:
            for key, value in updates.items():
                if value is not None:
                    row[key] = value
            write_jsonl(ledger_path, rows)
            manifest.touch_updated(root)
            return row
    known = ", ".join(r.get("id", "?") for r in rows) or "none yet"
    raise SystemExit(
        f"unknown source id '{source_id}' in sources/ledger.jsonl (have: {known}) — "
        "run `flip add-source` first"
    )
