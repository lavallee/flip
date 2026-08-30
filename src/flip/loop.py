"""The scope-aware read side of Flip's core lifecycle.

The lifecycle is orient -> select -> open -> work -> check -> close -> decide.
This module owns only the bounded orient/select view. Sessions and canonical
commands own the writes; a harness or human owns cadence and the stop decision.
"""

from __future__ import annotations

from pathlib import Path

from . import auto, beat, extensions, pages, workspace
from .manifest import load_manifest
from .util import find_notebook_root_pinned, find_workspace_root


def resolve_scope(start: Path | None = None) -> tuple[str, Path]:
    start = (start or Path.cwd()).resolve()
    notebook = find_notebook_root_pinned(start)
    if notebook is not None:
        return "notebook", notebook
    beat_root = beat.find_beat_root(start)
    if beat_root is not None:
        return "beat", beat_root
    workspace_root = find_workspace_root(start)
    if workspace_root is not None:
        return "workspace", workspace_root
    raise SystemExit(
        "not inside a Flip notebook, beat, or workspace; run `flip new`, "
        "`flip beat new`, or `flip ws init` first"
    )


def _latest_session(root: Path) -> dict | None:
    directory = root / "sessions"
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.md"), reverse=True):
        try:
            page = pages.read_page(path)
        except Exception:
            continue
        return {
            "path": path.relative_to(root).as_posix(),
            "started": page.fm.get("started"), "ended": page.fm.get("ended"),
            "workflow": page.fm.get("workflow"), "phase": page.fm.get("phase"),
            "item": page.fm.get("item"), "receipt": page.fm.get("receipt"),
        }
    return None


def _notebook_context(root: Path) -> dict:
    manifest = load_manifest(root)
    context = {
        "kind": manifest.kind,
        "disciplines": list(manifest.disciplines),
        "workflow": manifest.workflow or None,
        "plugins": list(manifest.plugins),
        "latest_session": _latest_session(root),
    }
    if manifest.workflow:
        from . import workflows
        try:
            context["workflow_next"] = workflows.next_phase(root)
        except SystemExit as exc:
            context["workflow_error"] = str(exc)
    return context


def _workspace_frontier(root: Path) -> dict:
    items: list[dict] = []
    unreadable: list[dict] = []
    for row in workspace.ws_rows(root):
        if row["status"] != "ok":
            unreadable.append({"notebook": row["handle"], "lane": "-",
                               "error": row["status"]})
            continue
        notebook = root / row["path"]
        try:
            data = auto.notebook_frontier(notebook)
        except SystemExit as exc:
            unreadable.append({"notebook": row["handle"], "lane": "-",
                               "error": str(exc)})
            continue
        for item in data["items"]:
            item = dict(item)
            item["notebook"] = row["handle"]
            items.append(item)
    lane_order = {lane: n for n, lane in enumerate(auto.LANES)}
    items.sort(key=lambda row: (
        lane_order.get(row["lane"], len(lane_order)), row["notebook"],
        auto._id_key(row["id"]),  # one shared deterministic id order
    ))
    data = {
        "scope": "workspace", "workspace": str(root),
        "selection": list(auto.LANES[:-1]), "items": items, "total": len(items),
    }
    if unreadable:
        data["unreadable"] = unreadable
    return data


def next_view(root: Path | None = None, scope: str | None = None,
              limit: int | None = None, explain: bool = False) -> dict:
    if limit is not None and limit < 1:
        raise SystemExit("--limit takes a positive number of items")
    if root is None:
        detected, root = resolve_scope()
    else:
        root = root.resolve()
        detected = scope or resolve_scope(root)[0]
    if detected == "notebook":
        data = auto.notebook_frontier(root)
        data["context"] = _notebook_context(root)
    elif detected == "beat":
        data = auto.frontier(root)
        data["scope"] = "beat"
        data["context"] = {"auto_policy": bool(auto.load_auto(beat.load_beat(root)))}
    elif detected == "workspace":
        data = _workspace_frontier(root)
        data["context"] = {"notebooks": len(workspace.ws_rows(root))}
    else:
        raise SystemExit(f"unknown loop scope '{detected}'")

    data = extensions.apply_frontier(root, data)
    selected = data["items"][0] if data["items"] else None
    supplied, context_trace = extensions.provide_context(root, selected)
    if supplied:
        data["context"]["extensions"] = supplied
    data["trace"].extend(context_trace)
    data["total"] = len(data["items"])
    if limit is not None:
        data["items"] = data["items"][:limit]
    if not explain:
        data.pop("trace", None)
    return data


def render(data: dict) -> str:
    label = data.get("beat") or data.get("notebook") or data.get("workspace") or data["scope"]
    lines = [f"{label} · {data['scope']} · next {len(data['items'])} of {data['total']}"]
    if data.get("mission"):
        lines.append(f"  mission: {data['mission']}")
    for key in ("stop", "authority", "materiality"):
        if data.get(key):
            lines.append(f"  {key}: {data[key]}")
    workflow_next = (data.get("context") or {}).get("workflow_next")
    if workflow_next:
        phase = workflow_next.get("phase") or "complete"
        lines.append(f"  workflow: {workflow_next['workflow']} -> {phase}")
    lines.append("")
    if not data["items"]:
        lines.append("nothing on the frontier — the recorded stop condition decides "
                     "whether that means done or blocked")
    for n, row in enumerate(data["items"], 1):
        where = f"{row.get('notebook')}:" if row.get("notebook") else ""
        lines.append(f"{n:>3}. [{row['lane']}] {where}{row['id']} · {auto._trunc(row['text'])}")
        lines.append(f"     {row['why']}")
    for bad in data.get("unreadable", []):
        lines.append(f"  ! {bad['notebook']} ({bad['lane']}): {bad['error']}")
    if data.get("trace"):
        lines.extend(["", "explain:"])
        for step in data["trace"]:
            detail = step.get("reason") or step.get("error") or ""
            count = step.get("items")
            suffix = f" · {count} item(s)" if count is not None else ""
            if detail:
                suffix += f" · {detail}"
            lines.append(f"  {step['hook']} · {step['handler']} · {step['result']}{suffix}")
    return "\n".join(lines)


__all__ = ["next_view", "render", "resolve_scope"]
