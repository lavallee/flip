# Getting started

flip has two layers: a harness plugin teaches an agent the workflow, and the
`flip` executable enforces it on disk. Install the plugin where research
happens; the first notebook then checks for the executable.

## 1. Install the harness plugin

Claude Code:

```text
/plugin marketplace add lyra-forge/marketplace
/plugin install flip@lyra-forge
```

Codex:

```bash
codex plugin marketplace add lyra-forge/marketplace
codex plugin add flip@lyra-forge
```

Start a new agent session after installation. Then give it the job, not a list
of bookkeeping commands:

> Use flip for this investigation: <question>. Keep the sources and judgments
> the work relies on, and leave a notebook another agent can inspect and
> continue.

The plugin supplies seven task-specific skills. Claude Code can also run the
custody hook at web-fetch time; Codex's hosted web tools do not traverse that
local hook, so its skills and `flip doctor` provide the discipline there. See
[Claude Code and Codex](claude-code.md) for that boundary.

## 2. Install the CLI when prompted

The command is `flip`; its PyPI package is `flip-notebook`. Python 3.12 or
newer is required. The recommended installer is uv because it can obtain the
requested Python independently of the repository:

```bash
uv tool install --python 3.12 flip-notebook
flip --version
```

If the install succeeds but `flip` is not found, run `uv tool update-shell`,
open a new shell, and retry. If uv is not installed, follow the
[official uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/).

With pipx and an installed Python 3.12+:

```bash
python --version
pipx install flip-notebook
pipx ensurepath
flip --version
```

Open a new shell after `pipx ensurepath`. Do not add flip to the researched
project's runtime dependencies; it is an operator tool.

The install provides two executables:

```bash
flip --version
flip-fetch --help
```

`flip` itself manages local files and invokes configured tools. `flip-fetch`
is the optional bundled network helper used for directed URL capture after it
is configured; flip makes no LLM calls and requires no service.

## 3. Initialize URL capture once

Local files can always be captured. To make ordinary URLs work immediately:

```bash
flip config init
flip config show
```

This writes `~/.flip/config.toml` with a `web` lane using `flip-fetch`. It will
not overwrite an existing config unless asked. PDF/OCR extraction, research,
and local-knowledge lanes remain operator choices; see [Integrations](integrations.md) and the [public plugin catalog](plugins.md).

## 4. Verify the first notebook

The agent should set its actor before `flip new`, choose a kind with `flip kind
list`, open a work session, and finish with `flip doctor`. Ask it to report:

- the notebook path and selected kind;
- the actor printed by `flip new`;
- source and claim ids created;
- `flip show` output;
- every doctor ERROR or WARN, with expected-until-use notices kept separate.

For a copy-and-run CLI exercise, use the [CLI quickstart](quickstart.md). For
the evidence rules after the first success, continue to the
[Evidence workflow](evidence-workflow.md).

## Update or remove

Claude Code:

```text
/plugin marketplace update lyra-forge
/plugin update flip@lyra-forge
/plugin uninstall flip@lyra-forge
```

Codex:

```bash
codex plugin marketplace upgrade lyra-forge
codex plugin add flip@lyra-forge
codex plugin remove flip
```

CLI installed with uv:

```bash
uv tool upgrade flip-notebook
uv tool uninstall flip-notebook
```

CLI installed with pipx:

```bash
pipx upgrade flip-notebook
pipx uninstall flip-notebook
```

Removing the tool never removes a notebook. The Markdown pages, captured
bytes, hashes, and append-only ledgers remain ordinary files.

## Supported environments

The package is pure Python and release smoke tests exercise the built wheel on
Linux, macOS, and Windows with Python 3.12. The agent plugins require a harness
version that exposes its plugin commands. If an install command is unknown,
update the harness first and confirm its current `plugin --help` surface.
