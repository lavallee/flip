"""Saved answer versions on a question page, including recoverable legacy prose."""
from __future__ import annotations

import hashlib
import re

SECTION = re.compile(
    r"^## (Answer|(?:Evidence|Re-posed|Closed|Dormant|Reopened) "
    r"\d{4}-\d{2}-\d{2}(?: — [^\n]*)?)[ \t]*$", re.M
)


def sections(body: str) -> list[tuple[str, str]]:
    parts = SECTION.split(body)
    return list(zip(parts[1::2], parts[2::2]))


def record(text, number, *, at=None, by=None, because=None, question=None):
    return {"version": f"v{number}", "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(), "at": at,
            "by": by, "because": because, "question": question}


def history(page, *, root=None, event_rows=None):
    saved = page.fm.get("answer_revisions")
    if isinstance(saved, list):
        return list(saved)
    answers = [text.strip() for heading, text in sections(page.body)
               if heading == "Answer" and text.strip()]
    if event_rows is None and root is not None:
        from . import events
        event_rows = events.read_events(root, op="question.answer", entity_id=page.id)
    events_by_text = {}
    logged = []
    for row in event_rows or ():
        text = (row.get("text") or "").strip()
        if text and row.get("op") == "question.answer" and row.get("id") == page.id:
            logged.append(text)
            events_by_text.setdefault(text, []).append(row)
    # Some older pages kept only the latest answer. The append-only log can
    # recover earlier saves in their original order. Older page-only sections
    # stay in page order when the two records cannot be aligned reliably.
    if not answers:
        answers = logged
    elif len(answers) == 1 and logged:
        answers = logged if logged[-1] == answers[0] else [*logged, answers[0]]
    versions = []
    for i, text in enumerate(answers, 1):
        rows = events_by_text.get(text, [])
        event = rows.pop(0) if rows else {}
        versions.append(record(text, i, at=event.get("ts"), by=event.get("actor")))
    return versions


def current(page, versions):
    if page.fm.get("status") != "answered":
        return None
    ident = page.fm.get("current_answer_version")
    saved = next((v for v in reversed(versions) if v["version"] == ident), None)
    if saved:
        marker = "## Answer\n" + saved["text"] + "\n"
        position = page.body.rfind(marker)
        if position >= 0:
            rest = page.body[position + len(marker):].strip()
            if not rest or (SECTION.match(rest) and not any(
                h == "Answer" or h.startswith("Reopened ") for h, _ in sections(rest)
            )):
                return saved["text"]
    for heading, text in reversed(sections(page.body)):
        if heading.startswith("Reopened "):
            break
        if heading == "Answer":
            return text.strip() or None
    return None


def cited_prose(text: str) -> str:
    """Exclude fenced examples, copied passage bodies and link destinations from evidence lookup."""
    kept = []
    fence = None
    for line in text.splitlines():
        quote = re.match(r"^(?: {0,3}>[ \t]?)*", line)[0]
        depth = quote.count(">")
        content = line[len(quote):]
        if fence and depth < fence[0]:
            fence = None
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", content)
        if fence:
            if (depth == fence[0] and marker and marker[1].startswith(fence[1])
                    and not marker[2].strip()):
                fence = None
            continue
        if marker:
            fence = (depth, marker[1])
            continue
        kept.append(content)
    prose = "\n".join(kept)
    prose = re.sub(r"(?<!`)(`+)(?!`)[^\n]*?(?<!`)\1(?!`)", " ", prose)
    prose = re.sub(r"\]\((?:<[^>\n]*>|(?:[^()\n]|\([^()\n]*\))*)\)", "]", prose)
    return re.sub(r"https?://[^\s<>]+", " ", prose)


def evidence_at_save(root, text):
    """Freeze notebook rulings on the claims and sources named by this answer."""
    from . import claims, sources, stance

    names = set(re.findall(r"(?<![\w:/])([A-Z]+\d+)\b", cited_prose(text)))
    if not names:
        return {}
    basis = {}
    linked = set()
    source_fms = {row["id"]: row for row in sources.list_sources(root)}
    for row in claims.list_claims(root):
        ident = row["id"]
        if ident in names:
            tests = stance.test_records(row)
            linked.update(claims.source_ids(row))
            basis[ident] = {"kind": "claim", "named": True, "summary": row.get("description"), "status": row.get("status"),
                            "exposure": row.get("exposure"),
                            "corroboration": claims.claim_corroboration(
                                [source_fms[sid] for sid in claims.evidence_ids(row) if sid in source_fms], row
                            ),
                            "verification": [v for v in (row.get("verified") or []) if isinstance(v, dict)],
                            "citations": [{"ref": ref, "role": role} for ref, role in claims.source_citations(row)],
                            "sources": claims.evidence_ids(row),
                            "subject": claims.subject_ids(row),
                            "contrary": [{"probe": item.get("probe"), "error": item.get("error"),
                                          "against": item.get("against")}
                                         for item in tests if item.get("result") == "failed"]}
    for row in source_fms.values():
        ident = row["id"]
        if ident in names or ident in linked:
            support = row.get("support") or {}
            basis[ident] = {"kind": "source", "named": ident in names, "grade": sources.derive_grade(row),
                            "basis": support.get("basis"), "independence": row.get("independence"),
                            "method": support.get("method"), "base": support.get("n"),
                            "vintage": support.get("vintage"), "caveats": row.get("notes")}
            if authority := sources.record_authority(row):
                basis[ident]["record_authority"] = authority
    return basis
