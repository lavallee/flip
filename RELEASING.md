# Releasing flip

Spec-stage checklist (until the CLI lands, a "release" is a spec draft):

1. `SPEC.md` header: bump the draft version and date.
2. `CHANGELOG.md`: dated entry, Keep-a-Changelog headings (Added/Changed/Fixed);
   call out anything that changes the meaning of existing on-disk files as
   **breaking**.
3. Content scrub: the repo references only public tools and standards — run
   the maintainer-local scrub checklist over the tree *and* the diff before
   pushing.
4. Docs consistency: `.venv/bin/python -m pytest tests/test_docs_current.py`
   must be green (see the gate below). Fix prose before tagging — a released
   doc that misstates the format is the expensive kind of wrong.
5. Commit `chore(release): X.Y.Z`, tag `vX.Y.Z`, push `main` and the tag.
6. `gh release create vX.Y.Z` with focused notes and a compare link.

Code path (the CLI has landed): ruff + pytest green locally, and the
six package declarations move **in lockstep** — `pyproject.toml` `[project]`
and `[tool.spindle.package]`, `src/flip/spindle-package.toml`,
`src/flip/__init__.py` `__version__`, `.claude-plugin/plugin.json`, and
`.codex-plugin/plugin.json`. The `**Status:** draft vX.Y` lines in `SPEC.md`
and `README.md` must match too. All of that is
now **enforced by tests, not by eye** — see the docs-consistency gate below.
If any skill changed, re-sync the plugin copy —
`rm -rf skills && cp -r src/flip/skills skills` —
(`tests/test_plugin_skills.py` fails on drift). PyPI publish happens via
the trusted-publishing workflow (`publish.yml`) triggered by the GitHub
release, or manually with `uv build && uv publish`.

Run the suite with the project venv (`.venv/bin/python -m pytest`), not a
bare `python`: under an interpreter where flip isn't installed, three tests
fail spuriously (`test_version_flag` and two `test_fetch` subprocess tests)
and look like a broken baseline.

## The docs-consistency gate

`tests/test_docs_current.py` is a release gate, not a style check. It asserts
prose against the code:

1. **Retired vocabulary** stays gone (each needle names the release that
   retired it; exceptions need an `ALLOW` entry with a reason).
2. **OKF version claims** match `manifest.OKF_VERSION`. A doc that names a
   superseded OKF release while flip stamps the current one into every
   manifest is a factual error about the format, not a style nit.
3. **Manifest examples** show the current `FLIP_PROFILE_VERSION`. The
   canonical example in SPEC.md is what a reader copies; it sat one profile
   behind. Prose discussing older profiles ("a 0.4 notebook gets the profile
   pass alone") is legitimate and deliberately not matched.
4. **The announced spec version** in SPEC.md and README matches
   `flip.__version__`.
5. **Every version declaration agrees** — the six package declarations and
   both status lines above.

**Prose files are discovered, not listed.** Anything matching `*.md` at the
root, `docs/*.md`, `src/flip/skills/*/SKILL.md`, `website/site/*.html`,
`website/work/*.md`, or `llms.txt` is covered the day it is written. That
matters: `AGENTS.md` — the contract agents read — sat three releases behind,
still teaching the authored-letter grade flags retired in 0.12, purely because
nobody had added it to a hand-maintained list.

Exclusions are deliberate and narrow: `CHANGELOG.md` (history describes what
was true then), `website/notebook/` (a real notebook that models its own
superseded claims, and whose `sources/raw/` is custody — captured bytes are
never edited), and `skills/` (a byte-identical synced copy).

When a check fires during a release, fix the prose — reaching for `ALLOW` or
an exclusion is the exception, and each one carries a written reason.
