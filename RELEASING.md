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

When the CLI lands, this file grows the code path: ruff + pytest green
locally, version bumped in lockstep (`pyproject.toml` + `__init__.py`),
minimal CI workflow green from day one, and PyPI publish via `uv build &&
uv publish` (or a trusted-publish workflow triggered by the GitHub release).
