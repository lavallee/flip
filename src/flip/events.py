"""Write events: one row in log/events.jsonl for every change to a notebook (SPEC §8).

The work log (log/log.jsonl) is what a person or agent chose to say about the
work. This ledger is what the commands did: `<entity>.<verb>`, the entity id,
who, when, and a few flat op-specific keys. It exists so another tool — a live
interface, a second agent, a script — can follow a notebook by watching one
file instead of diffing every page.

Rules this module holds for every caller:

- `emit` is called by the library function that performed the write, after the
  write and its generated views are on disk, so a watcher that reacts to a row
  reads finished state. The click layer never emits.
- A row is a plain append. Nothing is recounted, re-read or regenerated, so
  following a notebook costs its writers nothing that grows with its size.
- Text payloads (`text`, `reason`, `url`, `title`) are carried whole.
- There is no backfill: a notebook's event history starts at its next write.

`COMMAND_OPS`, `READ_ONLY` and `EXEMPT` classify every leaf command of the
CLI. A test walks the live command tree against them, so a new command cannot
ship without saying which ops it emits or why it emits none.
"""

from __future__ import annotations

from pathlib import Path

from . import util

EVENTS = Path("log") / "events.jsonl"
SCHEMA = "flip-events/1"

# Keys every row carries; an op's own detail may not shadow them.
_RESERVED = ("ts", "actor", "op", "id")


def emit(root: Path, op: str, id: str | None = None, **detail) -> dict:  # noqa: A002
    """Append one event row and return it.

    `op` is `<entity>.<verb>`; `id` is the entity id when the entity has one.
    `detail` keys are op-specific and flat; a value that is None, an empty
    string or an empty list is left out rather than written as a placeholder.
    """
    clash = [key for key in detail if key in _RESERVED]
    if clash:
        raise ValueError(f"event detail may not redefine {', '.join(clash)}")
    row: dict = {"ts": util.utc_now(), "actor": util.detect_actor(), "op": op}
    if id:
        row["id"] = str(id)
    for key, value in detail.items():
        if value is None or value == "" or value == [] or value == ():
            continue
        row[key] = list(value) if isinstance(value, tuple) else value
    util.append_jsonl(root / EVENTS, row)
    return row


def read_events(
    root: Path,
    since: str | None = None,
    op: str | None = None,
    entity_id: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Event rows, oldest first.

    `since` keeps rows whose `ts` is at or after it (ISO-8601 UTC timestamps
    compare as strings, so a date alone works too). `op` is a prefix: `claim`
    matches every claim op, `claim.status` only that one. `entity_id` matches
    `id` exactly. `limit` keeps the newest N of what is left, still oldest
    first — the tail is what a follower wants.
    """
    if limit is not None and limit < 1:
        raise SystemExit("--limit takes a positive number of events")
    try:
        rows = util.read_jsonl(root / EVENTS)
    except ValueError as e:
        raise SystemExit(f"{e}; fix or remove that line (flip doctor pinpoints it)") from None
    if since:
        rows = [r for r in rows if str(r.get("ts") or "") >= since]
    if op:
        rows = [r for r in rows if str(r.get("op") or "").startswith(op)]
    if entity_id:
        rows = [r for r in rows if str(r.get("id") or "") == entity_id]
    if limit is not None:
        rows = rows[-limit:]
    return rows


def events_view(root: Path, **filters) -> dict:
    """The `flip events --json` document."""
    return {"schema": SCHEMA, "events": read_events(root, **filters)}


def render_row(row: dict) -> str:
    """One event as a line of text: ts · actor · op · id · key=value …"""
    head = [str(row.get("ts", "")), str(row.get("actor", "")), str(row.get("op", ""))]
    if row.get("id"):
        head.append(str(row["id"]))
    rest = []
    for key, value in row.items():
        if key in _RESERVED:
            continue
        if isinstance(value, list):
            value = ",".join(str(v) for v in value)
        rest.append(f"{key}={' '.join(str(value).split())}")
    return " · ".join(head) + ("  " + " ".join(rest) if rest else "")


# --- the command → op table ------------------------------------------------------
#
# Keys are command paths as `flip cli` prints them, without the leading `flip`.

# Commands that change a notebook, and the ops they can emit. A command emits
# at least one of its ops on every successful run that wrote something.
COMMAND_OPS: dict[str, tuple[str, ...]] = {
    "add-source": ("source.add", "source.extract"),
    "extract": ("source.extract",),
    "grade": ("source.grade",),
    "source retitle": ("source.retitle",),
    "source recheck": ("source.recheck",),
    "source provenance": ("source.provenance",),
    "source pipeline": ("source.pipeline",),
    "source read": ("source.read",),
    "claim add": ("claim.add",),
    "claim status": ("claim.status",),
    "claim stance": ("claim.stance",),
    "claim verify": ("claim.verify",),
    "claim test": ("claim.test",),
    "claim rival": ("claim.rival",),
    "claim source add": ("claim.cite",),
    "claim source rm": ("claim.uncite",),
    "claim derives add": ("claim.derive",),
    "claim derives rm": ("claim.underive",),
    "claim supersede": ("claim.supersede", "claim.status", "claim.rival"),
    "question add": ("question.add",),
    "question note": ("question.note",),
    "draft save": ("draft.save",),
    "question assign": ("question.assign",),
    "question report": ("question.report",),
    "question revise": ("question.revise",),
    "question answer": ("question.answer",),
    "question close": ("question.close",),
    "question dormant": ("question.dormant",),
    "question reopen": ("question.reopen",),
    "question repose": ("question.repose",),
    "decide": ("decision.add",),
    "pass": ("pass.add",),
    "lead add": ("lead.add",),
    "lead dismiss": ("lead.dismiss",),
    # find keeps each new candidate as a lead; --capture also captures one.
    "find": ("lead.add", "source.add"),
    "directive add": ("directive.add",),
    "directive withdraw": ("directive.withdraw",),
    "session start": ("session.start",),
    "session end": ("session.end",),
    "session transcript": ("session.transcript", "source.add", "source.retitle"),
    "forecast add": ("forecast.add",),
    "forecast update": ("forecast.update",),
    "forecast resolve": ("forecast.resolve",),
    "forecast decline": ("forecast.decline",),
    "commission add": ("commission.add",),
    "commission status": ("commission.status",),
    "kind adopt": ("kind.adopt",),
    "workflow use": ("workflow.use",),
    "rename": ("rename",),
    "log": ("log.add",),
    # ask always lands its raw synthesis and a work-log line; recall does so
    # only with --record, and is a pure read without it.
    "ask": ("log.add",),
    "recall": ("log.add",),
    "transcript excerpt": ("transcript.excerpt",),
    "transcript unpin": ("transcript.unpin",),
}

# Commands that only read.
READ_ONLY: frozenset[str] = frozenset({
    "cli", "next", "show", "open", "resolve", "events", "snapshot",
    "source list", "claim list", "claim exposure", "question list",
    "commission list", "forecast list", "forecast due", "transcript list", "transcript read",
    "lead list", "directive list", "kind list", "kind show", "profiles",
    "discipline list", "discipline show", "workflow list", "workflow show",
    "workflow check", "workflow next", "hook list", "hook show",
    "filter list", "filter show", "filter test", "extension list",
    "plugin list", "plugin show", "plugin doctor", "config show",
    "export csl", "export json", "export bag", "export okf",
})

# Commands that write, but not as a research act inside one notebook's
# record, with the reason each is out of scope for this version of the ledger.
EXEMPT: dict[str, str] = {
    "new": "creates the notebook; a kind that seeds an entity emits that entity's row",
    "doctor": "a lint; --fix only regenerates derived views and backfills metadata",
    "migrate": "a one-time format migration of a whole notebook",
    "obsidian": "writes editor settings beside the notebook, not its record",
    "import": "workspace-level: copies a bundle in and binds it",
    "index": "rebuilds the machine-wide registry",
    "config init": "writes the machine's integration config",
    "kind new": "scaffolds a kind definition file",
    "discipline new": "scaffolds a discipline definition file",
    "workflow new": "scaffolds a workflow definition file",
    "plugin link": "edits the machine's plugin registry",
    "plugin unlink": "edits the machine's plugin registry",
    "plugin enable": "edits a scope's plugin pins",
    "plugin disable": "edits a scope's plugin pins",
    "beat new": "beat-level",
    "beat graduate": "beat-level",
    "beat log": "beat-level",
    "beat next": "beat-level",
    "beat show": "beat-level",
    "beat thread add": "beat-level",
    "beat thread update": "beat-level",
    "beat thread drop": "beat-level",
    "ws init": "workspace-level",
    "ws add": "workspace-level",
    "ws list": "workspace-level",
    "ws rename": "workspace-level",
    "ws rm": "workspace-level",
    "ws show": "workspace-level",
}

__all__ = [
    "COMMAND_OPS", "EVENTS", "EXEMPT", "READ_ONLY", "SCHEMA",
    "emit", "events_view", "read_events", "render_row",
]
