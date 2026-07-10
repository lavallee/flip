"""flip doctor — lint a notebook against the spec and its profile (SPEC §12/§14).

Every check is independent and tolerant: a missing optional file is simply
skipped unless the profile requires it, and one broken file never stops the
other checks from running. `run_doctor` only reports; exiting non-zero on
ERROR findings is the CLI's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .claims import STATUSES as CLAIM_STATUSES  # claim status enum (SPEC §7.2)
from .claims import corroboration_count
from .manifest import MANIFEST, STATUSES, VISIBILITIES, Manifest, load_manifest
from .profiles import SECTIONS, Profile, list_profiles, load_profile

# Source ledger enums (SPEC §5.4), re-exported from the owning module.
from .sources import FRESHNESS, GRADES, INDEPENDENCE
from .util import age_months, read_jsonl

LEDGER = "sources/ledger.jsonl"
PROVENANCE = "sources/_provenance.jsonl"
CLAIMS = "analysis/claims.jsonl"

# Manifest statuses where profile minimums are completion requirements that
# have come due: missing required paths are ERRORs (SPEC §12). While the
# notebook is still active/dormant they are WARNs — files appear with use.
CLOSED_STATUSES = ("done", "published", "archived")


@dataclass
class Finding:
    level: str  # "ERROR" | "WARN"
    code: str  # short slug, e.g. "orphan-ledger"
    message: str  # one actionable line
    path: str  # path relative to the notebook root


def _error(code: str, message: str, path: str) -> Finding:
    return Finding("ERROR", code, message, path)


def _warn(code: str, message: str, path: str) -> Finding:
    return Finding("WARN", code, message, path)


def _read(root: Path, rel: str) -> tuple[list[dict], Finding | None]:
    """Read an optional ledger; a corrupt line becomes a finding, not a crash."""
    try:
        return read_jsonl(root / rel), None
    except ValueError as e:
        return [], _error("bad-jsonl", f"{e}; fix or remove that line", rel)


def run_doctor(root: Path) -> list[Finding]:
    findings: list[Finding] = []

    manifest = _check_manifest(root, findings)
    profile = _check_profile(root, manifest, findings)

    sources, bad = _read(root, LEDGER)
    if bad:
        findings.append(bad)
    provenance, bad = _read(root, PROVENANCE)
    if bad:
        findings.append(bad)
    claims, bad = _read(root, CLAIMS)
    if bad:
        findings.append(bad)

    _check_notebook_md(root, profile, findings)
    _check_sources(root, sources, provenance, findings)
    _check_freshness(sources, profile, findings)
    _check_raw(root, provenance, findings)
    _check_claims(claims, sources, profile, findings)
    return findings


def _check_manifest(root: Path, findings: list[Finding]) -> Manifest | None:
    try:
        manifest = load_manifest(root)
    except SystemExit as e:
        findings.append(_error("bad-manifest", str(e), MANIFEST))
        return None
    except Exception as e:  # e.g. required field missing, wrong types
        findings.append(
            _error("bad-manifest", f"{MANIFEST} is not a valid manifest: {e}", MANIFEST)
        )
        return None
    if manifest.status not in STATUSES:
        findings.append(
            _error(
                "bad-status",
                f"status '{manifest.status}' invalid (one of: {', '.join(STATUSES)})",
                MANIFEST,
            )
        )
    policy = manifest.policy if isinstance(manifest.policy, dict) else {}
    visibility = policy.get("visibility")
    if visibility is not None and visibility not in VISIBILITIES:
        findings.append(
            _error(
                "bad-visibility",
                f"policy.visibility '{visibility}' invalid (one of: {', '.join(VISIBILITIES)})",
                MANIFEST,
            )
        )
    return manifest


def _check_profile(
    root: Path, manifest: Manifest | None, findings: list[Finding]
) -> Profile | None:
    if manifest is None:
        return None
    try:
        profile = load_profile(manifest.kind, root)
    except SystemExit:
        findings.append(
            _error(
                "unknown-kind",
                f"kind '{manifest.kind}' matches no profile; set kind to one of "
                f"{', '.join(list_profiles())} or add .flip/profiles/{manifest.kind}.toml",
                MANIFEST,
            )
        )
        return None
    closed = manifest.status in CLOSED_STATUSES
    make = _error if closed else _warn
    detail = (
        f"required before status '{manifest.status}'"
        if closed
        else "it appears with use; required before done/published/archived"
    )
    for rel in profile.requires:
        if not (root / rel).exists():
            findings.append(
                make(
                    "missing-required",
                    f"profile '{profile.id}' requires {rel} ({detail}); create it",
                    rel,
                )
            )
    policy = manifest.policy if isinstance(manifest.policy, dict) else {}
    for key, want in profile.forced_policy.items():
        have = policy.get(key)
        if have != want:
            findings.append(
                _error(
                    "policy-mismatch",
                    f"profile '{profile.id}' forces policy.{key} = {want!r} "
                    f"but manifest has {have!r}; edit [policy] in {MANIFEST}",
                    MANIFEST,
                )
            )
    return profile


def _check_notebook_md(root: Path, profile: Profile | None, findings: list[Finding]) -> None:
    path = root / "notebook.md"
    if not path.is_file():
        findings.append(
            _error(
                "missing-notebook",
                "notebook.md missing; it is required for every notebook (SPEC §3)",
                "notebook.md",
            )
        )
        return
    if profile is None:
        return
    headings = [
        line.lstrip("#").strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#")
    ]
    for section in profile.sections:
        heading = SECTIONS.get(section, {}).get("heading", section)
        if not any(heading.lower() in h for h in headings):
            findings.append(
                _warn(
                    "missing-section",
                    f"notebook.md has no '{heading}' heading "
                    f"(profile '{profile.id}' expects section '{section}')",
                    "notebook.md",
                )
            )


def _check_sources(
    root: Path, sources: list[dict], provenance: list[dict], findings: list[Finding]
) -> None:
    logged_ids = {p.get("source_id") for p in provenance}
    for row in sources:
        sid = str(row.get("id", "?"))
        local = row.get("local")
        if local and not (root / local).exists():
            findings.append(
                _error(
                    "orphan-ledger",
                    f"source {sid}: local file {local} missing; "
                    "recapture it or fix the ledger 'local' path",
                    str(local),
                )
            )
        if sid not in logged_ids:
            findings.append(
                _warn(
                    "unlogged-capture",
                    f"source {sid} has no capture event in {PROVENANCE}; log the acquisition",
                    LEDGER,
                )
            )
        for field, valid in (
            ("grade", GRADES),
            ("independence", INDEPENDENCE),
            ("freshness", FRESHNESS),
        ):
            value = row.get(field)
            if value is not None and value not in valid:
                findings.append(
                    _error(
                        "bad-enum",
                        f"source {sid}: {field} '{value}' invalid (one of: {', '.join(valid)})",
                        LEDGER,
                    )
                )


def _check_freshness(sources: list[dict], profile: Profile | None, findings: list[Finding]) -> None:
    """Stale freshness (SPEC §14): a row dated past the profile threshold but
    still judged "fresh" needs a re-judgment, not silence."""
    months = profile.freshness_months if profile is not None else Profile(id="?").freshness_months
    today = datetime.now(timezone.utc).date()
    for row in sources:
        if row.get("freshness") != "fresh":
            continue
        age = age_months(row.get("date"), today)
        if age is not None and age >= months:
            sid = str(row.get("id", "?"))
            findings.append(
                _warn(
                    "stale-freshness",
                    f"source {sid}: dated {row.get('date')} (~{age} months old, threshold "
                    f"{months}) but freshness is still 'fresh'; re-judge it — "
                    f"`flip grade {sid} --freshness dated` or update the date",
                    LEDGER,
                )
            )


def _check_raw(root: Path, provenance: list[dict], findings: list[Finding]) -> None:
    raw = root / "sources" / "raw"
    if not raw.is_dir():
        return
    logged_paths = {str(p["local_path"]).rstrip("/") for p in provenance if p.get("local_path")}
    for path in sorted(raw.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        # A capture may be a directory (multi-file capture, SPEC §5.1): any file
        # under a logged local_path counts as registered.
        covered = rel in logged_paths or any(rel.startswith(p + "/") for p in logged_paths)
        if not covered:
            findings.append(
                _warn(
                    "unregistered-raw",
                    f"{rel} has no provenance record; log its capture in {PROVENANCE} "
                    "or remove the file",
                    rel,
                )
            )


def _check_claims(
    claims: list[dict], sources: list[dict], profile: Profile | None, findings: list[Finding]
) -> None:
    by_id = {str(row.get("id")): row for row in sources}
    for claim in claims:
        cid = str(claim.get("id", "?"))
        status = claim.get("status")
        if status is not None and status not in CLAIM_STATUSES:
            findings.append(
                _error(
                    "bad-enum",
                    f"claim {cid}: status '{status}' invalid (one of: {', '.join(CLAIM_STATUSES)})",
                    CLAIMS,
                )
            )
        if not claim.get("load_bearing"):
            continue
        if status == "asserted":
            findings.append(
                _warn(
                    "unaudited-claim",
                    f"load-bearing claim {cid} is still 'asserted'; "
                    "verify it or set status needs-2nd",
                    CLAIMS,
                )
            )
        elif status == "verified" and profile is not None:
            # Recompute the bar with the shared helper (claims.corroboration_count:
            # deduped ids, judged + original only); never trust the stored count.
            claim_sources = claim.get("sources") or []
            linked = [by_id[str(s)] for s in dict.fromkeys(claim_sources) if str(s) in by_id]
            corroboration = corroboration_count(sources, claim_sources)
            has_grade_a = any(s.get("grade") == "A" for s in linked)
            ok = corroboration >= profile.claim_min_independent or (
                profile.claim_grade_a_suffices and has_grade_a
            )
            if not ok:
                suffix = " or one grade-A primary" if profile.claim_grade_a_suffices else ""
                findings.append(
                    _error(
                        "under-verified",
                        f"claim {cid} is 'verified' with {corroboration} independent "
                        f"source(s); profile '{profile.id}' needs "
                        f"{profile.claim_min_independent}{suffix} — add corroboration "
                        "or set status needs-2nd",
                        CLAIMS,
                    )
                )
