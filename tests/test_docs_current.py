"""Docs stay current mechanically, not by memory: retired vocabulary must not
reappear in prose surfaces. Each entry names the release that retired it.
When a term genuinely needs discussing (e.g. migration notes describing the
old model), the allowlist below carries the exception explicitly."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Prose surfaces a reader learns from. Source code and tests are exempt
# (migration code legitimately names old vocabulary).
DOC_FILES = [
    "README.md",
    "SPEC.md",
    "llms.txt",
    *[p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "docs").glob("*.md"))],
    *[p.relative_to(ROOT).as_posix() for p in sorted(ROOT.glob("src/flip/skills/*/SKILL.md"))],
    "website/site/index.html",
    "website/site/start.html",
    "website/site/spec.html",
]

# (needle, retired-in, why) — needles are chosen to be unambiguous in prose.
RETIRED = [
    ("--grade A", "0.12.0", "grades are derived, never authored"),
    ("--grade B", "0.12.0", "grades are derived, never authored"),
    ("independence original", "0.12.0", "old independence vocabulary"),
    ("independence: original", "0.12.0", "old independence vocabulary"),
    ("original|republisher", "0.12.0", "old independence vocabulary"),
    ("original\\|republisher", "0.12.0", "old independence vocabulary"),
    ("self-interested`", "0.12.0", "old independence vocabulary"),
    ("# Citations", "0.11.0", "claims use footnote attribution"),
    ("`supports`", "0.11.0", "claims carry OKF sources entries"),
    ("supports: [", "0.11.0", "claims carry OKF sources entries"),
    ("OKF v0.1)", "0.11.0", "flip is an OKF v0.2 bundle"),
]

# file -> needles allowed there (each with a reason a reviewer can check).
ALLOW = {
    # SPEC's §15 migration notes and CHANGELOG-style history may describe the
    # old model when explaining what `flip migrate` rewrites.
    "SPEC.md": {"independence: original", "# Citations", "`supports`"},
    "docs/wiki-alignment.md": {"# Citations"},  # describes the v0.1->v0.2 OKF change
}


def test_retired_vocabulary_absent_from_docs():
    offenders = []
    for rel in DOC_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        allowed = ALLOW.get(rel, set())
        for needle, retired_in, why in RETIRED:
            if needle in allowed:
                continue
            if needle in text:
                line = next(
                    i + 1 for i, ln in enumerate(text.splitlines()) if needle in ln
                )
                offenders.append(f"{rel}:{line}: {needle!r} (retired {retired_in}: {why})")
    assert not offenders, (
        "stale vocabulary in docs — update the prose (or add an explicit "
        "ALLOW entry with a reason):\n" + "\n".join(offenders)
    )
