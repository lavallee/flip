#!/usr/bin/env python3
"""Make custody the default path, instead of a thing someone has to remember.

flip's rule is already written down: a source you didn't capture is a source
you don't have, and improvising a fetch outside flip leaves no custody, no
hash, and no row saying what was tried. The rule is not the problem. The
problem is WHERE it is written — an agent doing research reads it only after
it has already decided to use flip, which is exactly the decision that went
wrong. So this hook puts the rule at the moment of the act.

Three events, all no-ops outside a flip notebook:

  PreToolUse  WebFetch  — once per session, name the notebook and the command.
  PostToolUse WebFetch  — record the URL as read-but-not-yet-in-custody.
  Stop                  — once per session, if any URL was read and never
                          captured, say so and hold the turn open.

Deliberately NOT hooked: WebSearch. Discovery is capture-free by doctrine
(SPEC §5) — a search returns leads, and a lead is not evidence. Nagging on
search is how a custody reminder becomes noise and stops being read.

The Stop report is conservative by construction: a URL counts as captured on a
loose substring match against the notebook's provenance and reference pages,
so the hook under-reports rather than over-reports. A false "you didn't
capture this" is what would make an operator turn the hook off, and a hook
that is off enforces nothing.

Exit 0 always, except the single deliberate Stop block. Any internal error is
swallowed: a custody reminder must never be the reason a session breaks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

STATE_VERSION = 1


def notebook_root(start: Path) -> Path | None:
    """Nearest ancestor holding an index.md with flip frontmatter.

    Matches flip's own resolution: the manifest is the root marker, and the
    `flip:` key is what distinguishes a flip notebook from any other directory
    with an index.md in it.
    """
    for d in [start, *start.parents]:
        index = d / "index.md"
        try:
            if not index.is_file():
                continue
            head = index.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if head.startswith("---") and re.search(r"^flip:\s*['\"]?[\d.]+", head, re.M):
            return d
    return None


def state_path(session_id: str, root: Path) -> Path:
    key = hashlib.sha256(f"{session_id}:{root}".encode()).hexdigest()[:16]
    d = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "flip" / "custody"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path(tempfile.gettempdir())
    return d / f"{key}.json"


def load_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("v") == STATE_VERSION:
            return state
    except (OSError, ValueError):
        pass
    return {"v": STATE_VERSION, "fetched": [], "told": False, "reported": False}


def save_state(path: Path, state: dict) -> None:
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def identity_tokens(url: str) -> list[str]:
    """Distinctive strings any honest record of this document would contain.

    An arXiv id or DOI survives the abs/pdf/html rewrites that make raw URL
    equality useless — the abstract page, the PDF, and the ar5iv mirror are one
    document and three URLs.
    """
    tokens = []
    if m := re.search(r"(\d{4}\.\d{4,5})(v\d+)?", url):
        tokens.append(m.group(1))
    if m := re.search(r"(10\.\d{4,9}/[^\s?#]+)", url):
        tokens.append(m.group(1).rstrip(").,"))
    clean = re.sub(r"^https?://(www\.)?", "", url).split("?")[0].split("#")[0].rstrip("/")
    if clean:
        tokens.append(clean)
    return tokens


def custody_haystack(root: Path) -> str:
    """Everything the notebook says it holds — provenance rows and reference
    pages both, because a source can be recorded without bytes (`--record`)
    and that is still a custody decision, not a gap."""
    parts = []
    prov = root / "sources" / "_provenance.jsonl"
    try:
        parts.append(prov.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        pass
    refs = root / "references"
    if refs.is_dir():
        for page in sorted(refs.glob("*.md"))[:500]:
            try:
                parts.append(page.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    passes = root / "passes"
    if passes.is_dir():
        for page in sorted(passes.glob("*.md"))[:500]:
            try:
                parts.append(page.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(parts)


def uncaptured(root: Path, urls: list[str]) -> list[str]:
    haystack = custody_haystack(root)
    out = []
    for url in urls:
        if not any(tok and tok in haystack for tok in identity_tokens(url)):
            out.append(url)
    return out


def emit(event: str, context: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": context}
    }))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0

    cwd = Path(payload.get("cwd") or os.getcwd())
    root = notebook_root(cwd)
    if root is None:
        return 0                                   # silent everywhere else

    event = payload.get("hook_event_name", "")
    tool = payload.get("tool_name", "")
    session = str(payload.get("session_id", "nosession"))
    sp = state_path(session, root)
    state = load_state(sp)
    name = root.name

    if event == "PreToolUse" and tool == "WebFetch":
        if state["told"]:
            return 0                               # once a session, not once a call
        state["told"] = True
        save_state(sp, state)
        emit("PreToolUse", (
            f"You are working inside the flip notebook '{name}'. Fetching is fine — "
            f"discovery is capture-free. But anything you go on to RELY on has to enter "
            f"the notebook through flip, or it has no custody, no hash, and no row saying "
            f"what was tried:\n"
            f"  flip add-source <url|doi:…|arXiv:…> --note \"why this matters\"\n"
            f"  flip add-source <url> --record --note \"<rungs tried>\"   # out of reach but citable\n"
            f"  flip pass <url> --reason \"<why not>\"                     # searched, rejected\n"
            f"Quoting a fetched page in a claim without one of these is the failure this "
            f"notice exists to prevent. A summary of a document is not the document: when a "
            f"number is load-bearing, capture, extract, and read the source text — fetch "
            f"summaries paraphrase and occasionally invent. You will be shown any gaps "
            f"before this turn ends."
        ))
        return 0

    if event == "PostToolUse" and tool == "WebFetch":
        url = (payload.get("tool_input") or {}).get("url")
        if url and url not in state["fetched"]:
            state["fetched"].append(url)
            save_state(sp, state)
        return 0

    if event == "Stop":
        if state["reported"] or not state["fetched"]:
            return 0
        gaps = uncaptured(root, state["fetched"])
        if not gaps:
            return 0
        state["reported"] = True                   # report once; never a loop
        save_state(sp, state)
        listed = "\n".join(f"  - {u}" for u in gaps[:20])
        more = f"\n  … and {len(gaps) - 20} more" if len(gaps) > 20 else ""
        print(json.dumps({"decision": "block", "reason": (
            f"Custody gap in flip notebook '{name}'. These were fetched this session and "
            f"do not appear in the notebook's provenance or reference pages:\n{listed}{more}\n\n"
            f"For each one, do the right thing and then finish your reply:\n"
            f"  - it backs something you asserted  -> flip add-source <url> --note \"…\", "
            f"then grade it after reading\n"
            f"  - you tried and could not get it   -> flip add-source <url> --record "
            f"--note \"<rungs tried>\"\n"
            f"  - you looked and rejected it       -> flip pass <url> --reason \"…\"\n"
            f"  - it was background, cited nowhere -> nothing to do; say so and move on\n\n"
            f"This is reported once per session and will not fire again."
        )}))
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                              # never break a session
        sys.exit(0)
