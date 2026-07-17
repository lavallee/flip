# Releasing flip

Spec-stage checklist (until the CLI lands, a "release" is a spec draft):

1. `SPEC.md` header: bump the draft version and date.
2. `CHANGELOG.md`: dated entry, Keep-a-Changelog headings (Added/Changed/Fixed);
   call out anything that changes the meaning of existing on-disk files as
   **breaking**.
3. Content scrub: the repo references only public tools and standards — run
   the maintainer-local scrub checklist over the tree *and* the diff before
   pushing.
4. Commit `chore(release): X.Y.Z`, tag `vX.Y.Z`, push `main` and the tag.
5. `gh release create vX.Y.Z` with focused notes and a compare link.

Code path (the CLI has landed): ruff + pytest green locally, and the
version bumped **in lockstep in all four places** — `pyproject.toml`
`[project]` and `[tool.spindle.package]`, `src/flip/spindle-package.toml`,
and `src/flip/__init__.py` `__version__`
(`tests/test_spindle_package.py` guards the TOML three; `__version__` is
on the checklist because it has drifted before). PyPI publish happens via
the trusted-publishing workflow (`publish.yml`) triggered by the GitHub
release, or manually with `uv build && uv publish`.
