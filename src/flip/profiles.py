"""Profiles and the notebook.md section menu.

Profiles are data, not code (SPEC §12): TOML files shipped under
src/flip/profiles/, one per kind. Projects can add their own by dropping a
TOML file into .flip/profiles/ inside the notebook (checked first).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

# Canonical section menu (SPEC §7.1). Order is fixed; profiles pick membership.
# Each section is a heading plus a one-line prompt the author writes under —
# prompts render as blockquotes and are meant to be replaced, not answered.
SECTION_ORDER = [
    "tip", "frame", "explore", "hypotheses", "sources",
    "priors", "decisions", "omissions", "workflow", "gaps", "handoff",
]

SECTIONS: dict[str, dict[str, str]] = {
    "tip": {
        "heading": "The tip",
        "prompt": "Where the question came from, and what the reader will do with the answer.",
    },
    "frame": {
        "heading": "Frame",
        "prompt": "Decision the reader should be able to make · headline claim (state it "
        "before building) · counter-narrative to rule out · audience and their prior knowledge.",
    },
    "explore": {
        "heading": "What the data can and can't say",
        "prompt": "Can say / can't say (but readers might assume) / could say with more "
        "ingest. Name unresolved tensions so they travel forward explicitly.",
    },
    "hypotheses": {
        "heading": "Hypotheses & falsifiers",
        "prompt": "Set before looking, each with a named falsifier (H1, H2…). Close the "
        "loop with a 'what survived the reporting' audit.",
    },
    "sources": {
        "heading": "Sources & provenance",
        "prompt": "What fed this. Point at sources/ledger.jsonl; for datasets name the "
        "generator, inputs, cut date, and rebuild command.",
    },
    "priors": {
        "heading": "Priors ledger",
        "prompt": "Each shift: claim · prior → posterior · shift size · confidence · source.",
    },
    "decisions": {
        "heading": "Decisions",
        "prompt": "Resolved forks and why (D1, D2…). The why is the payload — the what "
        "is recoverable from git, the why isn't.",
    },
    "omissions": {
        "heading": "What's not in the piece",
        "prompt": "Honest omissions — what you left out, and why.",
    },
    "workflow": {
        "heading": "Workflow notes",
        "prompt": "What helped, what hurt — tooling, agent patterns, dead ends. About "
        "the process, not the piece.",
    },
    "gaps": {
        "heading": "Gaps & self-critique",
        "prompt": "Where this work is weakest; what a hostile reviewer would attack first.",
    },
    "handoff": {
        "heading": "Handoff",
        "prompt": "For picking it up cold: what this is · state · what's locked · "
        "what's open · next moves. Graduates to HANDOFF.md.",
    },
}


@dataclass
class Profile:
    id: str
    description: str = ""
    sections: list[str] = field(default_factory=list)
    # Paths (relative to the notebook root) that `flip doctor` requires to exist.
    requires: list[str] = field(default_factory=list)
    # Claim verification bar: minimum independent sources for a load-bearing
    # claim to be `verified`, and whether one grade-A primary suffices.
    claim_min_independent: int = 2
    claim_grade_a_suffices: bool = True
    # Freshness threshold in months before a source is flagged `dated`.
    freshness_months: int = 18
    # Manifest policy values this profile forces (e.g. engagement →
    # visibility=client-confidential).
    forced_policy: dict[str, object] = field(default_factory=dict)


def _profile_from_toml(text: str) -> Profile:
    data = tomllib.loads(text)
    return Profile(
        id=data["id"],
        description=data.get("description", ""),
        sections=[s for s in SECTION_ORDER if s in set(data.get("sections", []))],
        requires=data.get("requires", []),
        claim_min_independent=data.get("claim_min_independent", 2),
        claim_grade_a_suffices=data.get("claim_grade_a_suffices", True),
        freshness_months=data.get("freshness_months", 18),
        forced_policy=data.get("forced_policy", {}),
    )


def load_profile(kind: str, notebook_root: Path | None = None) -> Profile:
    """Load a profile by id: notebook-local .flip/profiles/<kind>.toml wins,
    then the ones shipped with flip."""
    if notebook_root is not None:
        local = notebook_root / ".flip" / "profiles" / f"{kind}.toml"
        if local.is_file():
            return _profile_from_toml(local.read_text(encoding="utf-8"))
    ref = resources.files("flip") / "profiles" / f"{kind}.toml"
    try:
        return _profile_from_toml(ref.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            f"unknown profile kind '{kind}' (no shipped or notebook-local definition); "
            f"shipped: {', '.join(sorted(list_profiles()))}"
        ) from None


def list_profiles() -> list[str]:
    out = []
    for entry in (resources.files("flip") / "profiles").iterdir():
        if entry.name.endswith(".toml"):
            out.append(entry.name.removesuffix(".toml"))
    return sorted(out)
