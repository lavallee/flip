# Contributing to flip

flip is a working Python CLI and an evolving plain-file format. Contributions
are welcome across implementation, format design, documentation, plugins, and
real notebook ergonomics.

## Set up the repository

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/) are the supported
development path:

```bash
git clone https://github.com/lavallee/flip.git
cd flip
uv sync --locked
uv run flip --version
```

Run the local gates before opening a pull request:

```bash
uv run ruff check src tests scripts
uv run pytest -q
```

Tests use temporary notebooks and require no network or service. CI runs the
suite on supported Python versions and installs the built wheel on Linux,
macOS, and Windows.

## Make a change

- Start with an issue for format changes, new command families, or anything
  that changes the meaning of files already on disk. A concrete research case
  is more useful than an abstract request.
- Add or update tests for behavior changes. Keep errors actionable: agents and
  people both need the next legitimate move, not only the failing condition.
- Update `docs/internals.md` when a module's public contract changes.
- Update `SPEC.md` and `CHANGELOG.md` when the on-disk contract changes.
- Keep the core filesystem-only. Network access lives in the bundled
  `flip-fetch` executable or operator-configured subprocess integrations; the
  library makes no LLM calls and requires no service.

Entity-page changes must preserve frontmatter keys they do not own and preserve
the page body. Event ledgers and raw custody are append-only. Tests should use
`tmp_path` and must not depend on global flip configuration.

## Documentation and skills

The short onramp lives in `docs/getting-started.md` and `docs/quickstart.md`;
advanced evidence mechanics live in `docs/evidence-workflow.md`. Keep those
roles distinct when adding material.

The canonical agent skills are under `src/flip/skills/` and ship in the wheel.
The repository-level `skills/` tree is the plugin copy. After changing a skill,
copy the same file to both locations; `tests/test_plugin_skills.py` checks the
trees byte-for-byte and validates both plugin manifests.

`tests/test_docs_current.py` discovers public prose automatically. Retired
vocabulary, stale OKF/profile claims, and mismatched release versions fail the
suite. Fix the prose when it fails; exemptions are for genuine historical
discussion and need a written reason.

## Verify the package path

Changes to packaging, resources, scaffolding, or the first-run workflow should
also exercise the actual wheel:

```bash
uv build --wheel
uv run --no-project --python 3.12 python scripts/release_smoke.py
```

The smoke test creates an isolated environment, installs the wheel, checks
packaged profiles/kinds/skills/editor assets, and runs the local-file quickstart
through `flip doctor`.

## Pull requests

Keep the change focused, explain the research or operator problem it solves,
and call out any migration or compatibility impact. A pull request is ready
when Ruff, pytest, and the relevant wheel smoke pass and user-facing behavior
is documented.
