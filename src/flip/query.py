"""Research and knowledge roles — query-shaped integrations (SPEC §15–16).

Two roles that take a *question*, not a target, and never mint a source page on
their own:

- **research** (`[research]` config, verbs `find` / `ask`): acquire external
  material. `find` returns candidate leads to triage; `ask` returns cited
  synthesis. Synthesis is a **lead, grade C, not evidence** — its raw output
  lands under ``sessions/raw/`` for custody and a log breadcrumb is written, but
  the URLs it cites become sources only when you run `flip add-source` on them.
- **knowledge** (`[knowledge]` config, verb `recall`): recall what the
  deployment already holds locally. Read-only; lands nothing by default.

Tool output is normalized tolerantly into a neutral shape (url/title/snippet
for leads and hits, answer/citations for synthesis). Any backend-native ids a
tool carries stay in the verbatim raw capture; flip's normalized shape never
promotes them to fields of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import integrations, ledgers, pages, util

RAW = Path("sessions") / "raw"

# Field-name aliases a tool might use, in preference order. Kept tolerant so a
# range of tools bind without an adapter; unknown containers just yield nothing.
_LIST_KEYS = ("results", "candidates", "hits", "citations", "notes", "items")
_URL_KEYS = ("url", "link", "href")
_TITLE_KEYS = ("title", "name", "heading")
_SNIPPET_KEYS = ("snippet", "summary", "excerpt", "description", "text")
_PATH_KEYS = ("path", "file", "note", "local")
_ANSWER_KEYS = ("answer", "text", "response", "summary")


def _first(item: dict, keys) -> str | None:
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _as_items(data: object) -> list[dict]:
    """Pull a list of dict items from a tool's JSON: a bare list, or the first
    recognized list-valued container key."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in _LIST_KEYS:
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _candidate(item: dict) -> dict:
    """Neutral lead: url + optional title/snippet (backend ids dropped)."""
    out = {"url": _first(item, _URL_KEYS) or ""}
    title = _first(item, _TITLE_KEYS)
    snippet = _first(item, _SNIPPET_KEYS)
    if title:
        out["title"] = title
    if snippet:
        out["snippet"] = snippet
    return out


def _hit(item: dict) -> dict:
    """Neutral local-recall hit: path and/or title, optional excerpt."""
    out: dict = {}
    path = _first(item, _PATH_KEYS)
    title = _first(item, _TITLE_KEYS)
    snippet = _first(item, _SNIPPET_KEYS)
    if path:
        out["path"] = path
    if title:
        out["title"] = title
    if snippet:
        out["excerpt"] = snippet
    return out


@dataclass
class FindResult:
    query: str
    candidates: list[dict] = field(default_factory=list)
    tool: str = ""
    raw: str = ""


@dataclass
class AskResult:
    query: str
    answer: str
    citations: list[dict] = field(default_factory=list)
    raw_path: Path | None = None
    tool: str = ""


@dataclass
class RecallResult:
    query: str
    hits: list[dict] = field(default_factory=list)
    tool: str = ""


def _land_raw(root: Path, verb: str, query: str, raw: str) -> Path:
    """Preserve a tool's verbatim stdout under sessions/raw/ (custody, SPEC §16)."""
    slug = pages.slugify(query, fallback=verb)
    path = root / RAW / f"{util.stamp_slug()}-{verb}-{slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw.endswith("\n") else raw + "\n", encoding="utf-8")
    return path


def research_find(root: Path, query: str, via: str | None = None) -> FindResult:
    """Run [research].find; return normalized candidate leads (captures nothing)."""
    root = util.require_notebook_root(root)
    resolved = integrations.resolve("research", "find", via=via)
    run = integrations.run_query(resolved, root, query)
    candidates = [c for c in (_candidate(i) for i in _as_items(run.data)) if c["url"]]
    return FindResult(query=query, candidates=candidates, tool=run.tool, raw=run.raw)


def research_ask(root: Path, query: str, via: str | None = None) -> AskResult:
    """Run [research].ask; land the raw synthesis under sessions/raw/ + log it.

    Returns the cited answer and citation URLs as *leads* — this never opens a
    references/ page. Promote a lead by running `flip add-source` on its URL,
    then grading it.
    """
    root = util.require_notebook_root(root)
    resolved = integrations.resolve("research", "ask", via=via)
    run = integrations.run_query(resolved, root, query)
    data = run.data if isinstance(run.data, dict) else {}
    answer = _first(data, _ANSWER_KEYS) or run.raw.strip()
    citations = [c for c in (_candidate(i) for i in _as_items(data)) if c["url"]]
    raw_path = _land_raw(root, "ask", query, run.raw)
    rel = raw_path.relative_to(root).as_posix()
    ledgers.log_event(
        root,
        f"research ask '{query}' via {run.tool} → {rel} "
        f"({len(citations)} citation(s), lead only — not yet captured)",
    )
    return AskResult(query=query, answer=answer, citations=citations,
                     raw_path=raw_path, tool=run.tool)


def knowledge_recall(
    root: Path, query: str, via: str | None = None, record: bool = False
) -> RecallResult:
    """Run [knowledge].recall; return normalized local hits (lands nothing).

    With `record=True`, preserve the tool's raw output under sessions/raw/ and
    log a breadcrumb — otherwise recall is a pure read of what we already hold.
    """
    root = util.require_notebook_root(root)
    resolved = integrations.resolve("knowledge", "recall", via=via)
    run = integrations.run_query(resolved, root, query)
    hits = [h for h in (_hit(i) for i in _as_items(run.data)) if h]
    if record:
        raw_path = _land_raw(root, "recall", query, run.raw)
        rel = raw_path.relative_to(root).as_posix()
        ledgers.log_event(root, f"knowledge recall '{query}' via {run.tool} → {rel}")
    return RecallResult(query=query, hits=hits, tool=run.tool)
