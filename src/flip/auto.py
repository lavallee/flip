"""The loop frontier: what a standing mission should pick up next (SPEC §14.1).

An autonomous pass over a research corpus spends most of its budget before it
does any research, re-reading a notebook to work out where it left off. That
cost was measured: orienting cold in a 507-page notebook ran ~40K tokens of
generated views, and the loops that motivated this module each re-derived
their own priorities from prose on every pass.

`frontier(beat_root)` computes that answer instead — a ranked list of items
already recorded in the beat and its notebooks, each carrying the reason it is
on the list. Nothing here is stored: the frontier is a view, recomputed like
beat triage, and it goes stale the moment the ledgers move.

flip does not run the loop. A harness (a cron job, an agent runtime, a person
with a terminal) decides when to wake and what authority a pass carries; the
beat's `auto:` block records the standing policy in one place both can read,
and this module answers the one question that policy needs computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import beat as beat_mod
from . import commissions as commissions_mod
from . import forecast as forecast_mod
from . import pages, views
from .manifest import load_manifest
from .util import ROOT_FILE, is_notebook_root

# The lanes a frontier can draw from, in the order a pass should prefer them
# when the mission says nothing. Finishing beats starting: an item already in
# flight is cheaper to advance than one that has to be understood first, and a
# contract someone dispatched is a promise already made.
LANES = (
    "in-flight",       # load-bearing claims whose verification bar is unmet
    "commissioned",    # commission contracts dispatched and not yet returned
    "due",             # forecasts at their resolution date; questions off dormancy
    "open-question",   # questions on the working roster
    "thread",          # beat threads not yet graduated, by triage score
)

# Keys the `auto:` block understands. Everything here is POLICY the harness and
# the agent read — flip validates the shape, never the judgment.
AUTO_KEYS = ("selection", "stop", "authority", "materiality", "surfaces", "cadence")


@dataclass
class Auto:
    """A beat's standing loop policy, as written in its manifest."""

    selection: tuple[str, ...] = LANES
    stop: str = ""
    authority: str = ""
    materiality: str = ""
    surfaces: tuple[str, ...] = ()
    cadence: str = ""
    extras: dict = field(default_factory=dict)


def load_auto(b: beat_mod.Beat) -> Auto | None:
    """The beat's `auto:` block, or None when it declares no loop policy.

    A malformed block is an error, not a silent default: a mission whose stop
    condition was mistyped into a key flip ignores would run a loop nobody
    wrote, which is the one failure mode an autonomous pass cannot notice
    from the inside.
    """
    raw = (b.extras or {}).get("auto")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SystemExit(
            "the beat manifest's `auto:` must be a block of keys "
            f"({', '.join(AUTO_KEYS)}), not a {type(raw).__name__}"
        )
    auto = Auto(extras={k: v for k, v in raw.items() if k not in AUTO_KEYS})
    selection = raw.get("selection")
    if selection is not None:
        lanes = [str(s).strip() for s in pages.as_list(selection) if str(s).strip()]
        unknown = [lane for lane in lanes if lane not in LANES]
        if unknown:
            raise SystemExit(
                f"unknown selection lane(s) {', '.join(unknown)} in the beat's `auto:` "
                f"block (one of: {', '.join(LANES)}). A lane flip cannot compute is a "
                "priority nobody applies — fix index.md `auto: selection:`"
            )
        auto.selection = tuple(lanes) or LANES
    for key in ("stop", "authority", "materiality", "cadence"):
        if raw.get(key) is not None:
            setattr(auto, key, str(raw[key]).strip())
    if raw.get("surfaces") is not None:
        auto.surfaces = tuple(
            str(s).strip() for s in pages.as_list(raw["surfaces"]) if str(s).strip()
        )
    return auto


def beat_notebooks(root: Path) -> tuple[list[tuple[str, Path]], list[dict]]:
    """(readable notebooks, unreadable directories) under the beat.

    Read off the directory rather than the thread pages: a notebook that was
    imported, or whose thread page was hand-edited, is still the beat's to
    work on, and a frontier that quietly skipped it would send a pass past
    work it was standing in front of.

    A directory that is not a readable notebook is RETURNED, not dropped, for
    the same reason: to a caller, "skipped it" and "found nothing in it" look
    identical, and only one of them is a reason to go look.
    """
    out: list[tuple[str, Path]] = []
    bad: list[dict] = []
    holder = root / "notebooks"
    if not holder.is_dir():
        return out, bad
    for path in sorted(p for p in holder.iterdir() if p.is_dir()):
        if not is_notebook_root(path):
            bad.append({
                "notebook": path.name,
                "lane": "-",
                "error": f"{path.name}/ is under the beat's notebooks/ but is not a "
                         "readable notebook root (no manifest in its index.md)",
            })
            continue
        try:
            slug = load_manifest(path).slug
        except SystemExit as exc:
            bad.append({"notebook": path.name, "lane": "-", "error": str(exc)})
            continue
        out.append((slug, path))
    return out, bad


def _rows_in_flight(slug: str, nb: Path) -> list[dict]:
    return [
        {
            "lane": "in-flight",
            "notebook": slug,
            "id": str(c.get("id") or "?"),
            "text": str(c.get("description") or ""),
            "why": f"load-bearing claim at '{c.get('status')}' with its bar unmet",
        }
        for c in views._load_bearing_needing_work(nb)
    ]


def _rows_commissioned(slug: str, nb: Path) -> list[dict]:
    return [
        {
            "lane": "commissioned",
            "notebook": slug,
            "id": str(k.get("id") or "?"),
            "text": str(k.get("deliverable") or ""),
            "why": "commission dispatched and not yet returned"
                   + (f"; stops when {k['stop']}" if k.get("stop") else ""),
        }
        for k in commissions_mod.list_commissions(nb, status="dispatched")
    ]


def _rows_due(slug: str, nb: Path) -> list[dict]:
    rows = []
    for f in forecast_mod.due_forecasts(nb, within_days=0):
        days = f.get("days_left")
        overdue = f"overdue {-days}d" if isinstance(days, int) and days < 0 else "due"
        rows.append({
            "lane": "due",
            "notebook": slug,
            "id": str(f.get("id") or "?"),
            "text": str(f.get("description") or ""),
            "why": f"forecast resolves {f.get('resolves_by', '?')} ({overdue})",
        })
    for q in views._open_questions(nb):
        if q.get("status") != "dormant":
            continue
        rows.append({
            "lane": "due",
            "notebook": slug,
            "id": q["id"],
            "text": q["text"],
            "why": f"parked question came due {q.get('review_by', '')}".rstrip(),
        })
    return rows


def _rows_open_question(slug: str, nb: Path) -> list[dict]:
    return [
        {
            "lane": "open-question",
            "notebook": slug,
            "id": q["id"],
            "text": q["text"],
            "why": "open question"
            + ("" if q.get("resolves_via") else " with no resolves_via surface"),
        }
        for q in views._open_questions(nb)
        if q.get("status") != "dormant"
    ]


_NOTEBOOK_LANES = {
    "in-flight": _rows_in_flight,
    "commissioned": _rows_commissioned,
    "due": _rows_due,
    "open-question": _rows_open_question,
}


def frontier(root: Path, limit: int | None = None) -> dict:
    """What this beat should pick up next, ranked, with reasons.

    Lanes come in the order the beat's `auto: selection:` declares (or the
    default in `LANES`); inside a lane, order is deterministic — notebook slug
    then id — so two agents reading the same corpus choose the same item.
    Threads that have not graduated ride the beat's own triage score.

    A broken notebook does not sink the frontier: whatever cannot be read is
    reported alongside the items, because a pass that silently skipped a
    notebook would look exactly like a pass that found nothing there.
    """
    root = beat_mod.require_beat_root(root)
    b = beat_mod.load_beat(root)
    auto = load_auto(b)
    selection = auto.selection if auto else LANES

    items: list[dict] = []
    readable, unreadable = beat_notebooks(root)
    for slug, nb in readable:
        for lane in selection:
            builder = _NOTEBOOK_LANES.get(lane)
            if builder is None:
                continue
            try:
                items.extend(builder(slug, nb))
            except SystemExit as exc:
                unreadable.append({"notebook": slug, "lane": lane, "error": str(exc)})

    if "thread" in selection:
        for score, page in beat_mod.rank_threads(root):
            if page.fm.get("notebook"):
                continue  # already a notebook; its own items are on the roster
            items.append({
                "lane": "thread",
                "notebook": "",
                "id": page.id or "?",
                "text": str(page.fm.get("description") or page.fm.get("title") or ""),
                "why": f"beat thread, triage {score}",
                "score": score,
            })

    order = {lane: n for n, lane in enumerate(selection)}
    items.sort(key=lambda r: (
        order.get(r["lane"], len(order)),
        -float(r.get("score", 0.0)),
        r["notebook"],
        _id_key(r["id"]),
    ))
    data = {
        "beat": b.slug,
        "mission": b.mission,
        "selection": list(selection),
        "items": items if limit is None else items[:limit],
        "total": len(items),
    }
    if auto:
        for key in ("stop", "authority", "materiality", "cadence"):
            if getattr(auto, key):
                data[key] = getattr(auto, key)
        if auto.surfaces:
            data["surfaces"] = list(auto.surfaces)
    if unreadable:
        data["unreadable"] = unreadable
    return data


def _id_key(entity_id: str) -> tuple:
    prefix = str(entity_id).rstrip("0123456789")
    digits = str(entity_id)[len(prefix):]
    return (prefix, int(digits) if digits.isdigit() else 0)


def render(data: dict) -> str:
    """The frontier as the agent reads it: the policy, then the ranked items."""
    lines = [f"{data['beat']} · next {len(data['items'])} of {data['total']}"]
    if data.get("mission"):
        lines.append(f"  mission: {data['mission']}")
    for key in ("stop", "authority", "materiality"):
        if data.get(key):
            lines.append(f"  {key}: {data[key]}")
    if data.get("surfaces"):
        lines.append(f"  surfaces: {', '.join(data['surfaces'])}")
    if not data["items"]:
        lines.append("")
        lines.append("nothing on the frontier — the stop condition is what decides "
                     "whether that means done or blocked")
        return "\n".join(lines)
    lines.append("")
    for n, row in enumerate(data["items"], 1):
        where = f"{row['notebook']}:" if row["notebook"] else ""
        lines.append(f"{n:>3}. [{row['lane']}] {where}{row['id']} · {_trunc(row['text'])}")
        lines.append(f"     {row['why']}")
    if data.get("unreadable"):
        lines.append("")
        for bad in data["unreadable"]:
            lines.append(f"  ! {bad['notebook']} ({bad['lane']}): {bad['error']}")
    return "\n".join(lines)


def _trunc(text: object, width: int = 76) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= width else s[: width - 1].rstrip() + "…"


__all__ = ["Auto", "AUTO_KEYS", "LANES", "beat_notebooks", "frontier", "load_auto",
           "render", "ROOT_FILE"]
