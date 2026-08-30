# Releasing flip

Releases publish three connected surfaces: the `flip-notebook` wheel, the
Claude/Codex plugin repository, and marketplace entries that make the plugin
installable. Treat all three as one release path.

## Prepare the release

1. Start from a clean `main` and review the changes since the previous tag.
2. Add a dated `CHANGELOG.md` entry. Mark any changed interpretation of
   existing notebook files as breaking and document its migration path.
3. Move these seven version declarations in lockstep:

   - `pyproject.toml` `[project]` and `[tool.spindle.package]`;
   - `uv.lock` (regenerate with `uv lock` after changing `pyproject.toml`);
   - `src/flip/spindle-package.toml`;
   - `src/flip/__init__.py` `__version__`;
   - `.claude-plugin/plugin.json`;
   - `.codex-plugin/plugin.json`.

   Update the `SPEC.md` and `README.md` status lines to the same minor version.
   `tests/test_docs_current.py` enforces the set mechanically.
4. If a canonical skill changed, copy the same change from
   `src/flip/skills/` into `skills/`. The plugin test detects added, removed,
   and changed files in either direction.
5. Run the public-repository hygiene gate:

   ```bash
   git grep -niE 'downunder|paperboy|\bfrank\b|\bivy\b|lyra[[:space:]]+forge' -- \
     ':!CHANGELOG.md' ':!RELEASING.md' \
     ':!.github/workflows/pages.yml' ':!tests/test_website.py'
   ```

   It must return nothing. The exclusions are narrow and intentional:
   `CHANGELOG.md` preserves released history; this file, the workflow, and the
   test define the denylist they enforce against the deployable site. The
   public `lyra-forge/marketplace` slug is Flip's distribution address, not
   private product branding; the gate still rejects the prose name.
6. Confirm the `flip` entry exists in both marketplace catalogs before
   publishing:

   ```bash
   python scripts/check_marketplace.py /path/to/lyra-forge-marketplace
   ```

   With no argument, the check reads the live `main` branch. The publish
   workflow runs that live check and will stop before PyPI if either harness
   catalog is missing flip.

## Run the release gates

```bash
uv sync --locked
uv run ruff check src tests scripts
uv run pytest -q
uv build
uv run --no-project --python 3.12 python scripts/release_smoke.py
```

The test suite validates docs, version declarations, plugin manifests, and the
synced skills. The release smoke installs the built wheel in a fresh virtual
environment, checks both executables and packaged resources, and runs a pursuit
from creation through a verified local-file claim and `flip doctor`.

CI repeats the wheel smoke on Linux, macOS, and Windows. Do not publish a wheel
that only passed from the source checkout: missing package data is invisible on
that path.

## Publish

Commit as `chore(release): X.Y.Z`, tag `vX.Y.Z`, and push `main` plus the tag.
Create the GitHub release with focused notes and a compare link. The release
event triggers `.github/workflows/publish.yml`, which rebuilds and smokes the
artifact, verifies both live marketplace catalogs, and publishes to PyPI via
trusted publishing.

The publish job is idempotent for a version already present on PyPI. If it
stops before publishing, fix the failed release surface and rerun the workflow;
do not replace an immutable PyPI artifact under the same version.

## Why the docs gate is strict

`tests/test_docs_current.py` discovers root Markdown, `docs/`, packaged skills,
the deployable site, working site docs, and `llms.txt`. It checks retired
vocabulary, OKF/profile versions, the canonical manifest example, public status
lines, and all package version declarations. Historical changelog content and
captured notebook custody are deliberately excluded. When it fires, update the
prose; add an exemption only when a reader genuinely needs the historical term.
