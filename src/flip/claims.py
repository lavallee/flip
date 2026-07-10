"""The claim ledger — analysis/claims.jsonl (SPEC §7.2).

Current-state file: rows are edited in place as judgments change (git history
is the temporal record), so io goes through util.read_jsonl/util.write_jsonl —
never append_jsonl. Ids are still never reused: retracted and superseded
claims keep their rows, so scanning the file yields every C# ever issued.

`independent_corroboration` is computed, never hand-set: the count of a
claim's listed source ids (deduped) whose sources/ledger.jsonl row is JUDGED
— grade A/B/C, never "?" — with independence == "original" (SPEC §7.2:
ungraded sources never corroborate; capture is custody, not judgment). It is
recomputed on every status change so the number tracks the ledger as gradings
evolve. `corroboration_count` is the one shared implementation; doctor's
under-verified check uses it too.
"""

from __future__ import annotations

from pathlib import Path

from . import manifest, profiles, util

CLAIMS = Path("analysis") / "claims.jsonl"
SOURCE_LEDGER = Path("sources") / "ledger.jsonl"

STATUSES = (
    "asserted",
    "verified",
    "needs-2nd",
    "unconfirmed",
    "false-positive",
    "retracted",
    "superseded",
)


# Grades that count as a recorded judgment; "?" is custody, not judgment.
JUDGED_GRADES = ("A", "B", "C")


def _linked_rows(source_rows: list[dict], source_ids: list[str]) -> list[dict]:
    """Rows matching the given source ids, deduped; unknown ids contribute nothing."""
    by_id = {str(r.get("id")): r for r in source_rows}
    return [by_id[s] for s in dict.fromkeys(str(s) for s in source_ids) if s in by_id]


def corroboration_count(source_rows: list[dict], source_ids: list[str]) -> int:
    """Independent corroboration for a claim, per SPEC §7.2.

    Counts the claim's source ids (deduped — listing a source twice never
    counts twice) whose ledger row is judged (grade A/B/C — a grade-"?" row
    counts toward nothing, whatever its capture-time defaults say) AND
    independence == "original". Shared by add_claim/set_claim_status and
    doctor's under-verified check.
    """
    return sum(
        1
        for r in _linked_rows(source_rows, source_ids)
        if r.get("grade") in JUDGED_GRADES and r.get("independence") == "original"
    )


def _source_rows(root: Path, source_ids: list[str]) -> list[dict]:
    """Ledger rows for the given source ids (deduped; unknown ids and a
    missing ledger contribute nothing)."""
    return _linked_rows(util.read_jsonl(root / SOURCE_LEDGER), source_ids)


def _corroboration(root: Path, source_ids: list[str]) -> int:
    return corroboration_count(util.read_jsonl(root / SOURCE_LEDGER), source_ids)


def add_claim(
    root: Path,
    text: str,
    sources: list[str],
    load_bearing: bool = False,
    notes: str | None = None,
) -> dict:
    """Add a claim with status "asserted", allocating the next C#. Returns the row."""
    root = util.require_notebook_root(root)
    text = (text or "").strip()
    if not text:
        raise SystemExit("empty claim text; state the assertion in one sentence")
    sources = [str(s) for s in (sources or [])]
    rows = util.read_jsonl(root / CLAIMS)
    row: dict = {
        "id": util.next_id("C", [r.get("id", "") for r in rows]),
        "text": text,
        "status": "asserted",
        "load_bearing": bool(load_bearing),
        "sources": sources,
        "independent_corroboration": _corroboration(root, sources),
        "first_asserted": util.today(),
        "actor": util.detect_actor(),
    }
    if notes:
        row["notes"] = notes
    rows.append(row)
    util.write_jsonl(root / CLAIMS, rows)
    manifest.touch_updated(root)
    return row


def set_claim_status(root: Path, claim_id: str, status: str) -> dict:
    """Move a claim to a new status, recomputing independent_corroboration.

    "verified" is gated by the notebook profile's verification bar: at least
    `claim_min_independent` sources with independence == "original", or — when
    `claim_grade_a_suffices` — any listed source graded A. Returns the row.
    """
    root = util.require_notebook_root(root)
    if status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    rows = util.read_jsonl(root / CLAIMS)
    row = next((r for r in rows if r.get("id") == claim_id), None)
    if row is None:
        known = ", ".join(r.get("id", "?") for r in rows) or "none yet"
        raise SystemExit(
            f"no claim '{claim_id}' in analysis/claims.jsonl (known: {known}); "
            "add it with `flip claim add`"
        )
    sources = [str(s) for s in row.get("sources", [])]
    corroboration = _corroboration(root, sources)
    row["independent_corroboration"] = corroboration
    if status == "verified":
        profile = profiles.load_profile(manifest.load_manifest(root).kind, root)
        linked = _source_rows(root, sources)
        has_grade_a = any(r.get("grade") == "A" for r in linked)
        met = corroboration >= profile.claim_min_independent or (
            profile.claim_grade_a_suffices and has_grade_a
        )
        if not met:
            msg = (
                f"cannot verify {claim_id}: {corroboration} independent original source(s) "
                f"of {profile.claim_min_independent} required"
            )
            if profile.claim_grade_a_suffices:
                msg += " and no grade-A source among its sources"
            msg += (
                f" (sources: {', '.join(sources) or 'none'}); add independent original "
                "sources to the claim"
            )
            if profile.claim_grade_a_suffices:
                msg += " or upgrade one to grade A via `flip grade`"
            ungraded = [str(r.get("id")) for r in linked if r.get("grade") not in JUDGED_GRADES]
            if ungraded:
                msg += (
                    f"; {', '.join(ungraded)} still graded '?' and ungraded sources "
                    "never corroborate — judge them with `flip grade` first"
                )
            raise SystemExit(msg)
    row["status"] = status
    util.write_jsonl(root / CLAIMS, rows)
    manifest.touch_updated(root)
    return row


def list_claims(root: Path, status: str | None = None) -> list[dict]:
    """All claims, optionally filtered by status. Read-only."""
    if status is not None and status not in STATUSES:
        raise SystemExit(f"invalid claim status '{status}' (one of: {', '.join(STATUSES)})")
    rows = util.read_jsonl(root / CLAIMS)
    return [r for r in rows if status is None or r.get("status") == status]
