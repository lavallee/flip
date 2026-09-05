# Agent orientation to flip

flip is the reporting layer for source-backed work done by humans and agents
together. Use the repository's existing search, retrieval, data, and publishing
systems; use flip to keep the durable record connecting them.

## What changes

Instead of leaving only a polished answer and URL list, leave a reporter's
notebook containing:

- captured source material with hashes and provenance;
- source judgments recorded separately from capture;
- claims linked to evidence and held at honest statuses;
- question reformulations, narrower answers, dead ends, and reopen conditions;
- attributed work sessions another agent can inspect and continue.

The notebook is an OKF v0.2 bundle made of Markdown, YAML, and append-only
JSONL. It remains readable in GitHub, Obsidian, and ordinary text tools without
a service.

## Install the harness plugin

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

Start a new session after installation. If the `flip` executable is absent,
install it as a standalone Python 3.12+ tool:

```bash
uv tool install --python 3.12 flip-notebook
uv tool update-shell        # only if the installer says its bin dir is off PATH
flip --version
```

`pipx install flip-notebook` is the alternative when pipx already runs on
Python 3.12+. Do not add flip to the researched project's application dependencies. Full PATH,
configuration, update, and removal instructions are in
[Getting started](https://github.com/lavallee/flip/blob/main/docs/getting-started.md).

## Preflight before any notebook write

Set attribution first. `pursuit` creates Q1 during `flip new`, so a later export
cannot repair that first record:

```bash
export FLIP_ACTOR="agent:<name>"
flip --version
flip kind list
flip config show
```

If no integration config exists, `flip config init` enables directed web
capture through the bundled `flip-fetch`. Local files require no configuration.

## Put it to work

When the user gives a research question or deliverable:

1. Choose the matching output with `flip kind list`; users do not need to learn
   flip's vocabulary.
2. Create the notebook and start a session before retrieval.
3. Capture a source the moment the work begins relying on it.
4. Open what landed, then grade it; capture itself never establishes quality.
5. Add claims as soon as the work leans on them. Honor verification refusals.
6. Keep questions and negative evidence in the notebook, not only in chat.
7. End the session with a cold-pickup summary, then run `flip doctor`.

The minimum loop is:

```bash
flip new <slug> --kind <kind> --title "<human title>"
cd <slug>
flip session start first-pass --model <model> --tools <tool>
flip log "started: <mission>"
flip add-source <url-or-file> --note "<why it matters>"
flip grade <id> --independence ... --basis ...
flip claim add "<assertion>" --source <id> --load-bearing
flip show
flip session end first-pass --summary "<cold-pickup line>"
flip doctor
```

## Keep what makes the work easier

Notice recurring source problems, repeated manual repairs and successful
methods during ordinary work. Preserve the useful lesson while its evidence
is available; use notebook-extend to improve a nearby plugin or package a
checked solution. Finish the current job and keep the improvement proportional.
See [Make the next run easier](https://github.com/lavallee/flip/blob/main/docs/repeatable-gains.md)
and the [public plugin catalog](https://github.com/lavallee/flip/blob/main/docs/plugins.md).

## The contract you must preserve

- Capture before cite; never paste fetched text in as if it had custody.
- An ungraded source counts toward nothing.
- LLM and retrieval synthesis is a grade-C lead until public sources are
  captured and judged.
- `--source` means evidence for a claim; `--about` means the document the claim
  is about and owes an attribution test instead of corroboration.
- Raw custody and event/derivation JSONL are append-only.
- Generated index bodies and `log.md` are views; do not hand-edit them.
- Preserve unknown frontmatter keys and untouched prose on every round trip.
- Rename entity pages only through `flip rename`; ids are immutable.
- Status, stance, and tests are separate records.
- Before handoff, fix every doctor ERROR and account for every WARN.

## Where to read next

- [Short agent contract](https://github.com/lavallee/flip/blob/main/AGENTS.md)
- [Complete agent reference](https://github.com/lavallee/flip/blob/main/docs/agent-reference.md)
- [CLI quickstart](https://github.com/lavallee/flip/blob/main/docs/quickstart.md)
- [Evidence workflow](https://github.com/lavallee/flip/blob/main/docs/evidence-workflow.md)
- [Integrations](https://github.com/lavallee/flip/blob/main/docs/integrations.md)
- [Task skills](https://github.com/lavallee/flip/tree/main/src/flip/skills)
- [Specification](https://github.com/lavallee/flip/blob/main/SPEC.md)

Use `flip cli` rather than reconstructing command syntax from memory. Humans
steer the research; the agent maintains the inspectable record.
