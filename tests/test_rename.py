"""Tests for flip.rename — link-rewrite edge cases the CLI flow doesn't cover.

The main rename flow (move + rewrite + listing refresh) is exercised
end-to-end in test_cli.py; this file pins the link grammar."""

from __future__ import annotations

from pathlib import Path

import pytest

from flip import pages
from flip.rename import rename_entity

MANIFEST_MD = """\
---
okf_version: "0.1"
flip: "0.4"
slug: t
kind: scout
status: active
created: 2020-01-01
updated: 2020-01-01
---
# t
"""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FLIP_ACTOR", "human:test")
    (tmp_path / "index.md").write_text(MANIFEST_MD, encoding="utf-8")
    pages.write_page(
        tmp_path / "references" / "x.md",
        {"type": "Source", "id": "A1", "aliases": ["A1"], "title": "X"},
        "# X\n",
    )
    return tmp_path.resolve()


def test_rename_rewrites_titled_markdown_links(root: Path):
    # [text](target "Title") is legal markdown; the title must be preserved
    # and the target still rewritten
    prose = root / "analysis" / "notes.md"
    pages.write_page(
        prose,
        {"type": "Finding"},
        'See [the study](../references/x.md "Primary study"), '
        "[again](../references/x.md 'single quotes'), "
        '[anchored](../references/x.md#quote "With fragment"), '
        "and [plain](../references/x.md).\n",
    )

    _old, _new, changed = rename_entity(root, "A1", "primary-study")

    text = prose.read_text(encoding="utf-8")
    assert '[the study](../references/primary-study.md "Primary study")' in text
    assert "[again](../references/primary-study.md 'single quotes')" in text
    assert '[anchored](../references/primary-study.md#quote "With fragment")' in text
    assert "[plain](../references/primary-study.md)" in text
    assert "x.md" not in text
    assert changed >= 1


def test_rename_leaves_titled_links_to_other_files_alone(root: Path):
    pages.write_page(
        root / "references" / "other.md",
        {"type": "Source", "id": "A2", "aliases": ["A2"], "title": "Other"},
        "# Other\n",
    )
    prose = root / "analysis" / "notes.md"
    pages.write_page(
        prose,
        {"type": "Finding"},
        'Keep [other](../references/other.md "Other title") as-is.\n',
    )
    rename_entity(root, "A1", "primary-study")
    assert '[other](../references/other.md "Other title")' in prose.read_text(
        encoding="utf-8"
    )
