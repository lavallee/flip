"""The internal-name scrub, over the repo's own source and prose.

The site scrub (test_website.py) covers only ``website/site`` — and an
internal tool name shipped in a src/ comment for months because nothing
looked anywhere else. Same name list (imported, so there is exactly one),
wider net: everything scanned here is public distribution, and the public
distribution names integration *roles*, never the tools that fill them
(SPEC §16).
"""

from __future__ import annotations

from pathlib import Path

from test_website import INTERNAL_NAMES

REPO = Path(__file__).resolve().parent.parent

# The one file allowed to match: the list itself is defined there, and a scrub
# that flagged its own vocabulary would teach people to edit the vocabulary.
DEFINING_FILE = REPO / "tests" / "test_website.py"


def scrub_targets() -> list[Path]:
    found = [
        REPO / "SPEC.md",
        *(REPO / "src").rglob("*.py"),
        *(REPO / "src" / "flip" / "skills").rglob("*"),
        *(REPO / "tests").rglob("*.py"),
        *(REPO / "docs").rglob("*"),
    ]
    return sorted({p for p in found if p.is_file() and p != DEFINING_FILE})


def test_no_internal_names_in_source_tests_spec_or_docs():
    offenders = []
    for path in scrub_targets():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in INTERNAL_NAMES.finditer(text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(REPO)}:{line}: {match.group(0)}")
    assert not offenders, (
        "internal names in the public distribution — invent a generic name "
        "instead:\n" + "\n".join(offenders)
    )
