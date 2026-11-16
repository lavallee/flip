"""Directives: standing guidance from a person to whoever works the notebook next (SPEC §8).

A decision resolves a fork in the work and stays resolved. A directive
constrains the MANNER of the work — "primary sources only", "do not contact
the company", "stop at ten sources" — and is meant to be withdrawn when it no
longer applies. That difference is why a directive is a ledger row and not a
decision page.

log/directives.jsonl is append-only and holds two row shapes:

    {ts, id: "DR1", text, actor}                              the directive
    {ts, event: "withdraw", id: "DR1", because?, actor}       its withdrawal

A withdrawn directive stays on record; nothing is rewritten. Active directives
are printed first by `flip next` and `flip show` and carried in their JSON, so
any session that orients the usual way sees them without a new habit.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import events, manifest, pages, util

DIRECTIVES = Path("log") / "directives.jsonl"
PREFIX = "DR"
ID_RE = re.compile(r"^DR\d+$")

HEADING = "DIRECTIVES — standing instructions; follow every one until it is withdrawn"


def _rows(root: Path) -> list[dict]:
    try:
        return util.read_jsonl(root / DIRECTIVES)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line (flip doctor pinpoints it)") from None


def _id_num(directive_id: str) -> int:
    return int(directive_id[len(PREFIX):]) if ID_RE.match(directive_id) else 0


def list_directives(root: Path, include_all: bool = False) -> list[dict]:
    """Directives in the order they were set.

    Each row: {id, text, state, ts, actor, withdrawn_ts, withdrawn_actor,
    because} — `state` is `active` or `withdrawn`, and the three withdrawal
    keys are null while it is active. Active only unless `include_all`.
    """
    out: dict[str, dict] = {}
    for row in _rows(root):
        directive_id = str(row.get("id") or "")
        if str(row.get("event") or "") == "withdraw":
            target = out.get(directive_id)
            if target is not None and target["state"] == "active":
                target.update(
                    state="withdrawn", withdrawn_ts=row.get("ts"),
                    withdrawn_actor=row.get("actor"), because=row.get("because"),
                )
            continue
        if not directive_id or directive_id in out:
            continue
        out[directive_id] = {
            "id": directive_id,
            "text": str(row.get("text") or ""),
            "state": "active",
            "ts": row.get("ts"),
            "actor": row.get("actor"),
            "withdrawn_ts": None,
            "withdrawn_actor": None,
            "because": None,
        }
    rows = sorted(out.values(), key=lambda r: _id_num(r["id"]))
    return rows if include_all else [r for r in rows if r["state"] == "active"]


def active_directives(root: Path) -> list[dict]:
    """The directives in force. Tolerant: an unreadable ledger yields none
    rather than taking `flip next` down with it — doctor names the bad line."""
    try:
        return list_directives(root)
    except SystemExit:
        return []


def add_directive(root: Path, text: str) -> dict:
    """Set a directive, allocating the next DR#. Returns the row written."""
    root = util.require_notebook_root(root)
    text = (text or "").strip()
    if not text:
        raise SystemExit("empty directive; say how the work is to be done")
    directive_id = pages.allocate_id(root, PREFIX)
    row = {"ts": util.utc_now(), "id": directive_id, "text": text,
           "actor": util.detect_actor()}
    util.append_jsonl(root / DIRECTIVES, row)
    manifest.touch_updated(root)
    events.emit(root, "directive.add", directive_id, text=text)
    return row


def withdraw_directive(root: Path, directive_id: str, because: str | None = None) -> dict:
    """Withdraw a directive: it stops applying and stays on record."""
    root = util.require_notebook_root(root)
    known = {row["id"]: row for row in list_directives(root, include_all=True)}
    target = known.get(directive_id)
    if target is None:
        hint = (f"known: {', '.join(known)}" if known
                else 'none set yet; set one with `flip directive add "<text>"`')
        raise SystemExit(f"no directive '{directive_id}' in this notebook ({hint})")
    if target["state"] == "withdrawn":
        raise SystemExit(
            f"directive {directive_id} was already withdrawn "
            f"({target['withdrawn_ts']} · {target['withdrawn_actor']}); nothing to do"
        )
    row: dict = {"ts": util.utc_now(), "event": "withdraw", "id": directive_id}
    because = (because or "").strip()
    if because:
        row["because"] = because
    row["actor"] = util.detect_actor()
    util.append_jsonl(root / DIRECTIVES, row)
    manifest.touch_updated(root)
    events.emit(root, "directive.withdraw", directive_id, because=because)
    return row


def describe(root: Path, directive_id: str) -> str | None:
    """One line naming a directive and its state, or None when there is none."""
    for row in list_directives(root, include_all=True):
        if row["id"] == directive_id:
            return f'{row["id"]} ({row["state"]}, set by {row["actor"]}): "{row["text"]}"'
    return None


def render_block(rows: list[dict]) -> list[str]:
    """The lines `flip next` and `flip show` open with when directives are in
    force. The text is printed whole: a clipped instruction is a different one."""
    if not rows:
        return []
    lines = [HEADING]
    for row in rows:
        when = str(row.get("ts") or "")[:10]
        text = " ".join(str(row.get("text") or "").split())
        lines.append(f"  {row['id']} · {row.get('actor') or '?'} · {when} · {text}")
    lines.append("")
    return lines


__all__ = [
    "DIRECTIVES", "HEADING", "ID_RE", "PREFIX", "active_directives", "add_directive",
    "describe", "list_directives", "render_block", "withdraw_directive",
]
