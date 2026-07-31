"""Docs stay current mechanically, not by memory.

Five checks, run on every commit and named as a release gate in RELEASING.md:

1. `test_retired_vocabulary_absent_from_docs` — terms a release retired must
   not reappear in prose. Each entry names the release that retired it.
2. `test_okf_version_claims_match_the_code` — every doc that states which OKF
   version a notebook conforms to must state `manifest.OKF_VERSION`.
3. `test_manifest_examples_show_the_current_profile_version` — the canonical
   manifest example is what a reader copies.
4. `test_declared_spec_version_matches_the_package` — the version SPEC.md and
   README announce must match `flip.__version__`.
5. `test_every_version_declaration_agrees` — the places RELEASING.md says to
   bump in lockstep actually agree.

**Prose files are DISCOVERED, not listed.** A hand-maintained list is what let
AGENTS.md drift three releases behind (still teaching `--grade A|B|C`, retired
in 0.12) — it had simply never been added. Anything matching the patterns below
is covered the day it is written; exclusions are explicit and reasoned.
"""

import json
import re
import tomllib
from pathlib import Path

from flip import __version__
from flip.manifest import FLIP_PROFILE_VERSION, OKF_VERSION

ROOT = Path(__file__).resolve().parent.parent

# Directories whose markdown is NOT a prose surface a reader learns from.
EXCLUDED_DIRS = (
    # A real flip notebook: it models its own history on purpose (a superseded
    # claim still says OKF v0.1, which is the point) and sources/raw/ is
    # CUSTODY — captured bytes are never edited, whatever they say.
    "website/notebook/",
    # Byte-identical synced copy of src/flip/skills (test_plugin_skills guards
    # the sync); linting both would double-report every finding.
    "skills/",
    ".venv/",
    "dist/",
)

# Individual files exempt, with the reason.
EXCLUDED_FILES = {
    # A changelog is history. Old entries describe what was true then, and
    # rewriting them to match the present is the opposite of a changelog.
    "CHANGELOG.md",
}


def prose_files() -> list[str]:
    """Every prose surface, discovered. Root markdown, docs/, packaged skills,
    the deployable site, the site's working design docs, and llms.txt."""
    found: list[Path] = [
        *ROOT.glob("*.md"),
        *(ROOT / "docs").glob("*.md"),
        *ROOT.glob("src/flip/skills/*/SKILL.md"),
        *ROOT.glob("website/site/*.html"),
        *ROOT.glob("website/work/*.md"),
        *ROOT.glob("llms.txt"),
    ]
    out = []
    for path in sorted(set(found)):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXCLUDED_FILES or rel.startswith(EXCLUDED_DIRS):
            continue
        out.append(rel)
    return out


# --- 1. retired vocabulary ------------------------------------------------------

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
]

# file -> needles allowed there (each with a reason a reviewer can check).
ALLOW = {
    # Both name the pre-0.8 values to state the rule that they are a MISSING
    # judgment rather than a weak one — a reader carrying a notebook across the
    # 0.8 change can't recognize their own pages without the old spellings.
    "SPEC.md": {"self-interested`"},
    "AGENTS.md": {"self-interested`"},
    # The migration section has to name the value it parks, for the same reason.
    "docs/quickstart.md": {"independence: original"},
    "docs/wiki-alignment.md": {"# Citations"},  # describes the v0.1->v0.2 OKF change
}


def test_retired_vocabulary_absent_from_docs():
    offenders = []
    for rel in prose_files():
        text = (ROOT / rel).read_text(encoding="utf-8")
        allowed = ALLOW.get(rel, set())
        for needle, retired_in, why in RETIRED:
            if needle in allowed or needle not in text:
                continue
            line = next(i + 1 for i, ln in enumerate(text.splitlines()) if needle in ln)
            offenders.append(f"{rel}:{line}: {needle!r} (retired {retired_in}: {why})")
    assert not offenders, (
        "stale vocabulary in docs — update the prose (or add an explicit "
        "ALLOW entry with a reason):\n" + "\n".join(offenders)
    )


# --- 2. OKF version claims ------------------------------------------------------

# "OKF v0.2", "OKF 0.2", and manifest examples `okf_version: "0.2"`.
_OKF_CLAIM = re.compile(r"\bOKF\s+v?(\d+\.\d+)|\bokf_version:\s*[\"']?(\d+\.\d+)")

# Prose that legitimately names an older OKF release, with the reason.
OKF_ALLOW = {
    # Explains what changed between OKF v0.1 and v0.2 — naming the old release
    # is the whole subject of the page.
    "docs/wiki-alignment.md",
}


def test_okf_version_claims_match_the_code():
    """A doc that says which OKF version a notebook conforms to must say the
    one flip actually writes. `okf_version` is stamped into every manifest, so
    prose and disk disagreeing is a factual error, not a style nit."""
    offenders = []
    for rel in prose_files():
        if rel in OKF_ALLOW:
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            for match in _OKF_CLAIM.finditer(line):
                stated = match.group(1) or match.group(2)
                if stated != OKF_VERSION:
                    offenders.append(
                        f"{rel}:{i}: claims OKF {stated}, but flip writes "
                        f"okf_version {OKF_VERSION} (manifest.OKF_VERSION)"
                    )
    assert not offenders, (
        "docs disagree with the code about the OKF version at rest:\n"
        + "\n".join(offenders)
    )


# --- 2b. the canonical manifest example -----------------------------------------

# `flip: "0.8"` inside a fenced manifest example. Only the annotated canonical
# form is checked — prose that discusses older profiles ("a 0.4 notebook gets
# the profile pass alone") is legitimate and must stay legible.
_MANIFEST_EXAMPLE = re.compile(
    r"^flip:\s*[\"'](\d+\.\d+)[\"']\s*#\s*flip profile version", re.M
)


def test_manifest_examples_show_the_current_profile_version():
    """The canonical manifest example in SPEC.md is what a reader copies. It
    said `flip: "0.7"` one profile after 0.8 shipped."""
    offenders = []
    for rel in prose_files():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for match in _MANIFEST_EXAMPLE.finditer(text):
            if match.group(1) != FLIP_PROFILE_VERSION:
                line = text[: match.start()].count("\n") + 1
                offenders.append(
                    f"{rel}:{line}: manifest example shows flip {match.group(1)}, "
                    f"current profile is {FLIP_PROFILE_VERSION}"
                )
    assert not offenders, "stale manifest example(s):\n" + "\n".join(offenders)


# --- 3 & 4. version declarations ------------------------------------------------

_SPEC_STATUS = re.compile(r"^\*\*Status:\*\*\s+draft\s+v(\d+\.\d+)", re.M)
_README_STATUS = re.compile(r"^Status:\s+spec draft\s+v(\d+\.\d+)", re.M)


def _minor(version: str) -> str:
    major, minor, *_ = version.split(".")
    return f"{major}.{minor}"


def test_declared_spec_version_matches_the_package():
    """SPEC.md and README announce a version to readers; both drifted by hand
    at 0.16.0 and had to be caught by eye."""
    expected = _minor(__version__)
    spec = _SPEC_STATUS.search((ROOT / "SPEC.md").read_text(encoding="utf-8"))
    readme = _README_STATUS.search((ROOT / "README.md").read_text(encoding="utf-8"))
    assert spec, "SPEC.md has no '**Status:** draft vX.Y' line to check"
    assert readme, "README.md has no 'Status: spec draft vX.Y' line to check"
    assert spec.group(1) == expected, (
        f"SPEC.md announces draft v{spec.group(1)}, package is {__version__}"
    )
    assert readme.group(1) == expected, (
        f"README.md announces spec draft v{readme.group(1)}, package is {__version__}"
    )


def test_every_version_declaration_agrees():
    """The lockstep bump, mechanized. RELEASING.md lists five places plus the
    plugin manifest and notes that 'versions have drifted before' — a checklist
    item a human verifies by eye is exactly the thing to make a test."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    spindle = tomllib.loads(
        (ROOT / "src" / "flip" / "spindle-package.toml").read_text(encoding="utf-8")
    )
    plugin = json.loads(
        (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    declared = {
        "pyproject [project]": pyproject["project"]["version"],
        "pyproject [tool.spindle.package]": pyproject["tool"]["spindle"]["package"][
            "version"
        ],
        "src/flip/spindle-package.toml": spindle["tool"]["spindle"]["package"][
            "version"
        ],
        "src/flip/__init__.py __version__": __version__,
        ".claude-plugin/plugin.json": plugin["version"],
    }
    distinct = set(declared.values())
    assert len(distinct) == 1, "version declarations disagree:\n" + "\n".join(
        f"  {where}: {value}" for where, value in sorted(declared.items())
    )
