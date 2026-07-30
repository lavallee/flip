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
    # The agent-facing contract. It was NOT on this list until 0.16.0 and had
    # drifted three releases behind — still teaching `--grade A|B|C` (retired
    # 0.12) and the pre-0.8 independence vocabulary. The surface agents read
    # is the last one that should rot.
    "AGENTS.md",
    "CONTRIBUTING.md",
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
    # §5.4 has to name the pre-0.8 values to state the rule that they are a
    # MISSING judgment rather than a weak one — the axis changed (custody →
    # epistemics), so a reader who doesn't know the old spellings can't tell
    # whether their notebook is affected. The §5.3 example page carries current
    # vocabulary; the old needles were removed from it in 0.16.0.
    # Both name the pre-0.8 values to state the rule that they are a MISSING
    # judgment rather than a weak one — a reader carrying a notebook across the
    # change can't recognize their own pages without the old spellings.
    "SPEC.md": {"self-interested`"},
    "AGENTS.md": {"self-interested`"},
    # The migration section has to name the value it parks, for the same reason:
    # a reader carrying a notebook across 0.8 needs to recognize their own pages.
    "docs/quickstart.md": {"independence: original"},
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
