"""Guards on the deployable documentation site.

These are cheap structural checks that run in the ordinary test suite — they
do not build the site (that needs artoo and a CLI run; the Pages workflow does
it). What they protect is the property that matters most for a public repo:
that nothing internal, broken, or externally-dependent reaches ``website/site``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "website" / "site"
PAGES = ["index.html", "flipbook.html", "spec.html", "start.html", "notebook.html",
         "404.html"]

# Tool, host, and project names that must never appear in public output. The
# public distribution names integration *roles*, never the commands that fill
# them (SPEC §7).
INTERNAL_NAMES = re.compile(
    r"\b(weaver|frank|collagen|malo|fab|keel|barnowl|cistern|downunder|paperboy"
    r"|george|oslo|delphi|trawler|jackdaw)\b",
    re.IGNORECASE,
)

pytestmark = pytest.mark.skipif(not SITE.exists(), reason="website/site is not present")


def site_files() -> list[Path]:
    return [p for p in SITE.rglob("*") if p.is_file()]


def test_every_page_is_present():
    for name in PAGES:
        assert (SITE / name).is_file(), f"{name} is missing from the site"


def test_no_internal_names_anywhere_in_the_deployable_site():
    """The name-leak gate, over generated data as well as authored markup."""
    offenders = []
    for path in site_files():
        if path.suffix in {".png", ".jpg", ".woff2", ".ico"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in INTERNAL_NAMES.finditer(text):
            offenders.append(f"{path.relative_to(SITE)}: {match.group(0)}")
    assert not offenders, "internal names in the deployable site: " + "; ".join(offenders)


def test_no_external_assets():
    """A site that renders from file:// cannot depend on a CDN.

    External *links* are fine; external stylesheets, scripts, images, and fonts
    are not — they would break offline rendering and leak reader requests.
    """
    pattern = re.compile(
        r"<(?:script|link|img|iframe|source)\b[^>]*\b(?:src|href)\s*=\s*[\"'](https?:|//)",
        re.IGNORECASE,
    )
    for name in PAGES:
        html = (SITE / name).read_text(encoding="utf-8")
        # Anchor hrefs are allowed; only asset-bearing elements are checked.
        assert not pattern.search(html), f"{name} loads an external asset"


def test_internal_links_resolve():
    """Every relative href/src in a page points at a file that exists."""
    pattern = re.compile(r"(?:href|src)\s*=\s*\"([^\"#?]+)\"")
    missing = []
    for name in PAGES:
        html = (SITE / name).read_text(encoding="utf-8")
        for target in pattern.findall(html):
            if target.startswith(("http://", "https://", "mailto:", "data:", "//")):
                continue
            if not (SITE / target).exists():
                missing.append(f"{name} -> {target}")
    assert not missing, "dangling internal references: " + "; ".join(missing)


def test_generated_data_matches_the_package_version():
    """The site's coordinates are derived, so they must not drift from the package."""
    data = SITE / "data" / "flip.json"
    if not data.exists():
        pytest.skip("site data has not been generated in this checkout")
    import json

    payload = json.loads(data.read_text(encoding="utf-8"))
    from flip import __version__

    assert payload["version"] == __version__, (
        "website/site/data/flip.json is stale — rebuild with `artoo build website`"
    )


def test_first_contact_leads_with_proof_not_installation():
    home = (SITE / "index.html").read_text(encoding="utf-8")
    hero = re.search(r'<header class="hero">([\s\S]*?)</header>', home)
    assert hero, "homepage hero is missing"
    assert "hero__comparison" in hero.group(1), "hero no longer shows the before/after"
    assert hero.group(1).count('class="btn') == 2, "hero should offer exactly two actions"
    assert "harness-band" not in home, "install commands moved to start.html"
    assert home.index("jobs-intro") < home.index("home-proof") < home.index("The gap")
    assert 'id="proof-refusal"' in home


def test_flipbook_demonstrates_a_real_verification_refusal():
    import json

    payload = json.loads((SITE / "data" / "flipbook.json").read_text(encoding="utf-8"))
    refusal = next((step for step in payload["steps"] if step["id"] == "refused"), None)
    assert refusal, "flipbook lost the refusal beat"
    assert refusal["refused"] is True
    assert refusal["exit_code"] != 0
    assert "cannot verify" in refusal["stdout"].lower()
    assert refusal["command_outputs"], "pages need command-level output for the proof"


def test_navigation_distinguishes_the_format_tour_from_the_spec():
    for name in PAGES:
        html = (SITE / name).read_text(encoding="utf-8")
        nav = re.search(r'<nav class="site-nav">([\s\S]*?)</nav>', html)
        assert nav, f"{name} has no site nav"
        assert '>Format</a>' in nav.group(1), f"{name} calls the visual tour Spec"

    tour = (SITE / "spec.html").read_text(encoding="utf-8")
    assert "This page is the tour" in tour
    assert "SPEC.md is the" in tour and "law" in tour


def test_spec_anchors_use_the_github_slug_algorithm():
    """Spec deep-links must land; GitHub deletes punctuation rather than replacing it."""
    data = SITE / "data" / "spec.json"
    if not data.exists():
        pytest.skip("site data has not been generated in this checkout")
    import json

    payload = json.loads(data.read_text(encoding="utf-8"))
    headings = re.findall(r"^## (\d+\..+)$", (REPO / "SPEC.md").read_text(encoding="utf-8"), re.M)
    expected = {
        re.sub(r"[^\w\s-]", "", h.strip().lower()).replace(" ", "-") for h in headings
    }
    actual = {section["anchor"] for section in payload["sections"]}
    assert actual == expected, "spec anchors drifted from SPEC.md headings"
