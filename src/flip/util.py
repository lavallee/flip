"""Shared primitives: time, hashing, JSONL io, actor detection, id allocation.

Everything in flip that touches disk goes through here so conventions stay
uniform: ISO-8601 UTC timestamps, append-only JSONL with one object per line,
sha256 fixity, and compact per-notebook ids.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import random
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT_FILE = "index.md"

# Workspace marker: a vault/repo root that binds notebooks to handles (SPEC §18).
WORKSPACE_FILE = Path(".flip") / "workspace.toml"

# Notebook uid: stable machine-generated identity that travels with the bundle
# (SPEC §4). Metadata only — never appears in links or filenames. Crockford
# base32 lowercased, minus vowels, so uids are compact and unpronounceable-safe.
UID_ALPHABET = "0123456789bcdfghjkmnpqrstvwxyz"
UID_RE = re.compile(r"^nb-[0-9bcdfghjkmnpqrstvwxyz]{8}$")

# Workspace handles are importer-owned petnames (SPEC §18). Deliberately
# narrower than SLUG_RE: no dots/underscores, no leading digit, so a handle is
# always a TOML bare key and reads unambiguously before ':' in a ref.
HANDLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Cross-notebook reference grammar (SPEC §9): "A3" or "handle:A3".
# '#' is a deprecated synonym for ':' (removed in 0.10).
REF_RE = re.compile(r"^(?:(?P<handle>[a-z][a-z0-9-]*)(?P<sep>[:#]))?(?P<id>[A-Z]+\d+)$")


def new_uid(rng: random.Random | None = None) -> str:
    """Mint a notebook uid like nb-7k3m9p2x. Pass a seeded Random in tests."""
    pick = rng.choice if rng is not None else secrets.SystemRandom().choice
    return "nb-" + "".join(pick(UID_ALPHABET) for _ in range(8))


def parse_ref(ref: str) -> tuple[str | None, str, bool]:
    """Parse an entity reference into (handle, id, used_deprecated_hash).

    "A3" -> (None, "A3", False); "recipes:A3" -> ("recipes", "A3", False);
    "recipes#A3" -> ("recipes", "A3", True). Anything else exits with the
    grammar in the message.
    """
    m = REF_RE.match(ref or "")
    if not m:
        raise SystemExit(
            f"invalid reference {ref!r}: expected a compact id like A3 or a "
            "qualified form like recipes:A3 (handle = lowercase letters, "
            "digits, hyphens; id = PREFIX + number)"
        )
    return m.group("handle"), m.group("id"), m.group("sep") == "#"


def format_ref(handle: str | None, entity_id: str) -> str:
    """"A3" or "recipes:A3" — the canonical textual form of a reference."""
    return f"{handle}:{entity_id}" if handle else entity_id


def is_notebook_root(directory: Path) -> bool:
    """A flip notebook root is a directory whose index.md opens with a
    frontmatter block declaring a `flip:` profile version (SPEC §4). Cheap
    textual sniff — no YAML parse — so root discovery stays dependency-light;
    doctor does the strict validation. Plain OKF bundles (okf_version but no
    flip key) and generated sub-indexes (no frontmatter) don't match.
    """
    path = directory / ROOT_FILE
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return False
    if not head.startswith("---\n"):
        return False
    block = head.split("\n---", 1)[0]
    return any(line.startswith("flip:") for line in block.splitlines())


def utc_now() -> str:
    """ISO-8601 UTC timestamp with seconds precision, e.g. 2026-07-10T14:31:02Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def stamp_slug() -> str:
    """Timestamp prefix for session/log filenames: 2026-07-10T1431."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")


_LEDGER_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")


def age_months(date_str: object, today_date) -> int | None:
    """Whole months between a ledger date ("2025-11-23", "2025-11", "2025")
    and `today_date` (a datetime.date); None when the date doesn't parse.
    Shared by views (stale/dated projections) and doctor (stale-freshness)."""
    m = _LEDGER_DATE_RE.match(str(date_str or ""))
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    months = (today_date.year - year) * 12 + (today_date.month - month)
    if today_date.day < day:
        months -= 1
    return months


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def append_jsonl(path: Path, obj: dict) -> None:
    """Append one object to a JSONL file, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file tolerantly: blank lines skipped, bad lines raise."""
    if not path.exists():
        return []
    out: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{i}: invalid JSONL line") from e
    return out


def write_jsonl(path: Path, objs: list[dict]) -> None:
    """Rewrite a whole JSONL file (only for current-state ledgers, never logs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for obj in objs:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def detect_actor() -> str:
    """Who is acting: FLIP_ACTOR env wins; known agent harnesses next; else git/OS user.

    Returns strings like "human:marc-lavallee" or "agent:claude" (SPEC §8).
    """
    explicit = os.environ.get("FLIP_ACTOR")
    if explicit:
        return explicit
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE"):
        return "agent:claude"
    if os.environ.get("CODEX_SANDBOX") or os.environ.get("CODEX_HOME_ACTIVE"):
        return "agent:codex"
    name = ""
    try:
        name = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        pass
    if not name:
        name = getpass.getuser()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"
    return f"human:{slug}"


def next_id(prefix: str, existing: list[str]) -> str:
    """Allocate the next compact id for a prefix: next_id("C", ["C1","C7"]) == "C8".

    Ids are never reused (SPEC §9); callers pass every id ever issued,
    including retracted ones.
    """
    top = 0
    pat = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for s in existing:
        m = pat.match(s)
        if m:
            top = max(top, int(m.group(1)))
    return f"{prefix}{top + 1}"


def find_notebook_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default cwd) to the nearest flip notebook root
    (an index.md carrying flip manifest frontmatter — see is_notebook_root)."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if is_notebook_root(candidate):
            return candidate
    return None


def require_notebook_root(start: Path | None = None) -> Path:
    root = find_notebook_root(start)
    if root is None:
        raise SystemExit(
            "not inside a flip notebook (no index.md with flip manifest frontmatter "
            "found here or above); run `flip new <slug>` to create one, or "
            "`flip migrate` inside a v0.3 notebook"
        )
    return root


def is_workspace_root(directory: Path) -> bool:
    """A workspace root is any directory carrying .flip/workspace.toml (SPEC §18)."""
    return (directory / WORKSPACE_FILE).is_file()


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default cwd) to the nearest workspace root."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if is_workspace_root(candidate):
            return candidate
    return None
