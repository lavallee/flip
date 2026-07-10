"""OKF export — project a notebook as an Open Knowledge Format v0.1 bundle.

Design: docs/wiki-alignment.md. The bundle is a *render* (SPEC §11): generated
deterministically from the ledgers, never edited in place, safe to delete.
Sources become `references/` concepts carrying custody frontmatter, claims
cite them via `# Citations`, decisions get their own concepts, and the work
log renders as OKF's reserved `log.md`. Consumers that know nothing about
flip can traverse all of it; consumers that do get the custody metadata as
extension frontmatter keys (OKF consumers must preserve unknown keys).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import __version__
from .manifest import load_manifest
from .util import read_jsonl, utc_now

MARKER_START = "<!-- FLIP:START -->"
MARKER_END = "<!-- FLIP:END -->"
STATE_FILE = ".last-export.json"


def _yaml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_yaml_value(x) for x in v) + "]"
    s = str(v)
    # Quote anything YAML could misread (specials, or scalars that would
    # coerce to numbers/booleans); json.dumps is a valid YAML scalar.
    looks_typed = s.lower() in ("true", "false", "null", "~") or _is_numberish(s)
    if s == "" or any(c in s for c in ':#[]{}"\'\n') or s.strip() != s or looks_typed:
        return json.dumps(s, ensure_ascii=False)
    return s


def _is_numberish(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is None or v == "" or v == []:
            continue
        lines.append(f"{k}: {_yaml_value(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _id_sort_key(row: dict) -> tuple:
    rid = row.get("id", "")
    head = rid.rstrip("0123456789")
    tail = rid[len(head):]
    return (head, int(tail) if tail.isdigit() else 0)


def _git_head(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _latest_provenance(root: Path) -> dict[str, dict]:
    """source_id → most recent capture event."""
    events: dict[str, dict] = {}
    for ev in read_jsonl(root / "sources" / "_provenance.jsonl"):
        sid = ev.get("source_id")
        if sid:
            events[sid] = ev  # file is chronological; last write wins
    return events


def _reference_page(row: dict, prov: dict | None, full_trail: bool) -> str:
    title = row.get("title") or row.get("id", "")
    fm: dict = {
        "type": "Source",
        "title": title,
        "description": row.get("notes") or f"{row.get('kind', 'source')} source",
        "grade": row.get("grade"),
        "independence": row.get("independence"),
        "freshness": row.get("freshness"),
    }
    body = [f"# {title}", ""]
    if full_trail:
        fm["resource"] = row.get("url")
        fm["timestamp"] = row.get("date") or (prov or {}).get("ts")
        if prov:
            fm["sha256"] = prov.get("sha256")
            fm["retrieved_at"] = prov.get("ts")
            fm["captured_with"] = prov.get("tool")
        if row.get("url"):
            body.append(f"Canonical: <{row['url']}>")
        if row.get("local"):
            body.append(f"Archived copy: `{row['local']}` (in the source notebook)")
        if row.get("authors"):
            body.append("Authors: " + ", ".join(row["authors"]))
    else:
        body.append(
            "_Source trail withheld by notebook policy; grading judgment shown above._"
        )
    if row.get("notes"):
        body += ["", row["notes"]]
    return _frontmatter(fm) + "\n" + "\n".join(body) + "\n"


def _claim_page(row: dict, ledger_by_id: dict[str, dict]) -> str:
    cid = row.get("id", "")
    fm = {
        "type": "Claim",
        "title": cid,
        "description": (row.get("text") or "")[:160],
        "status": row.get("status"),
        "load_bearing": bool(row.get("load_bearing")),
        "timestamp": row.get("first_asserted"),
        "supports": [f"/references/{sid}" for sid in row.get("sources", [])],
    }
    body = [row.get("text", ""), ""]
    if row.get("notes"):
        body += [f"_{row['notes']}_", ""]
    srcs = row.get("sources", [])
    if srcs:
        body.append("# Citations")
        for n, sid in enumerate(srcs, 1):
            label = ledger_by_id.get(sid, {}).get("title") or sid
            body.append(f"[{n}] [{label}](/references/{sid}.md)")
    return _frontmatter(fm) + "\n" + "\n".join(body) + "\n"


def _decision_page(row: dict) -> str:
    fm = {
        "type": "Decision",
        "title": row.get("id", ""),
        "description": (row.get("decision") or "")[:160],
        "timestamp": row.get("ts"),
        "question": row.get("question"),
    }
    body = [
        f"**Question.** {row.get('question', '')}",
        "",
        f"**Decision.** {row.get('decision', '')}",
        "",
        f"**Why.** {row.get('why', '')}",
    ]
    rejected = row.get("alternatives_rejected") or []
    if rejected:
        body += ["", "**Rejected.** " + "; ".join(map(str, rejected))]
    return _frontmatter(fm) + "\n" + "\n".join(body) + "\n"


def _log_md(root: Path) -> str:
    events = read_jsonl(root / "log" / "log.jsonl")
    by_day: dict[str, list[dict]] = {}
    for ev in events:
        day = str(ev.get("ts", ""))[:10]
        by_day.setdefault(day, []).append(ev)
    lines = ["# Update Log", ""]
    for day in sorted(by_day, reverse=True):
        lines.append(f"## {day}")
        for ev in reversed(by_day[day]):
            actor = ev.get("actor", "")
            lines.append(f"* **Update**: {ev.get('text', '')} _({actor})_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _dir_index(title: str, entries: list[tuple[str, str, str]]) -> str:
    lines = [f"# {title}", ""]
    for fname, label, desc in entries:
        lines.append(f"* [{label}]({fname}) - {desc}")
    return "\n".join(lines) + "\n"


def export_okf(
    root: Path,
    dest: Path,
    include_private: bool = False,
    announce: Path | None = None,
) -> Path:
    m = load_manifest(root)
    visibility = m.policy.get("visibility", "internal")
    if visibility != "public" and not include_private:
        raise SystemExit(
            f"notebook visibility is '{visibility}'; OKF export is a render for outside "
            "consumption — set [policy] visibility = \"public\" or pass --include-private"
        )
    full_trail = include_private or bool(m.policy.get("source_trail_public", False))

    if dest.exists():
        if not (dest / STATE_FILE).is_file():
            raise SystemExit(
                f"{dest} exists and is not a previous flip OKF export; "
                "pick a fresh destination or remove it"
            )
        shutil.rmtree(dest)  # regenerate: the bundle is a render, never precious
    dest.mkdir(parents=True)

    ledger = sorted(read_jsonl(root / "sources" / "ledger.jsonl"), key=_id_sort_key)
    claims = sorted(read_jsonl(root / "analysis" / "claims.jsonl"), key=_id_sort_key)
    decisions = sorted(read_jsonl(root / "log" / "decisions.jsonl"), key=_id_sort_key)
    prov = _latest_provenance(root)
    ledger_by_id = {r["id"]: r for r in ledger if "id" in r}

    sections: list[tuple[str, str, str]] = []

    if ledger:
        refs = dest / "references"
        refs.mkdir()
        entries = []
        for row in ledger:
            rid = row["id"]
            (refs / f"{rid}.md").write_text(
                _reference_page(row, prov.get(rid), full_trail), encoding="utf-8"
            )
            entries.append(
                (f"{rid}.md", row.get("title") or rid,
                 row.get("notes") or f"{row.get('kind', 'source')} · grade {row.get('grade', '?')}")
            )
        (refs / "index.md").write_text(_dir_index("References", entries), encoding="utf-8")
        sections.append(("references/", "References",
                         f"{len(ledger)} captured source(s) with custody and grading"))

    if claims:
        cdir = dest / "claims"
        cdir.mkdir()
        entries = [
            (f"{row['id']}.md", row["id"], (row.get("text") or "")[:100])
            for row in claims if "id" in row
        ]
        for row in claims:
            if "id" in row:
                (cdir / f"{row['id']}.md").write_text(
                    _claim_page(row, ledger_by_id), encoding="utf-8"
                )
        (cdir / "index.md").write_text(_dir_index("Claims", entries), encoding="utf-8")
        sections.append(("claims/", "Claims",
                         f"{len(claims)} claim(s) with status and citations"))

    if decisions:
        ddir = dest / "decisions"
        ddir.mkdir()
        entries = [
            (f"{row['id']}.md", row["id"], (row.get("decision") or "")[:100])
            for row in decisions if "id" in row
        ]
        for row in decisions:
            if "id" in row:
                (ddir / f"{row['id']}.md").write_text(_decision_page(row), encoding="utf-8")
        (ddir / "index.md").write_text(_dir_index("Decisions", entries), encoding="utf-8")
        sections.append(("decisions/", "Decisions", f"{len(decisions)} recorded decision(s)"))

    if (root / "log" / "log.jsonl").exists():
        (dest / "log.md").write_text(_log_md(root), encoding="utf-8")

    generated_at = utc_now()
    root_fm = {
        "okf_version": "0.1",
        "notebook": m.slug,
        "generated_by": f"flip {__version__}",
        "generated_at": generated_at,
    }
    head = _git_head(root)
    if head:
        root_fm["source_commit"] = head
    title = m.title or m.slug
    body = [f"# {title}", ""]
    if m.title:
        body += [f"OKF projection of the flip notebook `{m.slug}` ({m.kind}).", ""]
    for path, label, desc in sections:
        body.append(f"* [{label}]({path}) - {desc}")
    if (dest / "log.md").exists():
        body.append("* [Update Log](log.md) - chronological work history")
    (dest / "index.md").write_text(
        _frontmatter(root_fm) + "\n" + "\n".join(body) + "\n", encoding="utf-8"
    )

    (dest / STATE_FILE).write_text(
        json.dumps(
            {"generated_at": generated_at, "tool": f"flip {__version__}", "notebook": m.slug},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if announce is not None:
        _announce(announce, dest, m.slug)
    return dest


def _announce(agents_md: Path, bundle: Path, slug: str) -> None:
    """Append (or replace) the FLIP marker block in an AGENTS.md, pointing agents
    at the bundle's root index — the same idiom OpenWiki uses, different marker."""
    try:
        rel = bundle.resolve().relative_to(agents_md.resolve().parent)
        pointer = str(rel / "index.md")
    except ValueError:
        pointer = str(bundle.resolve() / "index.md")
    block = (
        f"{MARKER_START}\n"
        f"This repository contains an OKF knowledge bundle exported from the flip "
        f"notebook `{slug}`. Start at [{pointer}]({pointer}) and follow links; the "
        f"bundle is generated — do not edit it by hand (edit the notebook and "
        f"re-export instead).\n"
        f"{MARKER_END}\n"
    )
    if agents_md.exists():
        text = agents_md.read_text(encoding="utf-8")
        if MARKER_START in text and MARKER_END in text:
            pre = text.split(MARKER_START)[0]
            post = text.split(MARKER_END, 1)[1]
            agents_md.write_text(pre + block + post, encoding="utf-8")
        else:
            agents_md.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    else:
        agents_md.write_text(block, encoding="utf-8")
