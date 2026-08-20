# Agent orientation to flip

flip is a reporting layer for research done by humans and agents together. Use
this map to put it to work in an existing repository or research workflow.

## What flip changes

Agent research often ends as a polished answer whose sources, search path,
judgments, and unresolved questions disappear with the session. flip leaves a
reporter's notebook instead: captured source material with custody receipts,
explicit source judgments, claims linked to evidence, questions that accumulate
answers and follow-ons, and an attributed session history.

The result is work another agent can inspect, challenge, continue, and publish
from without reconstructing the investigation from chat logs.

## What flip provides

- A CLI for source capture, grading, claims, tests, questions, sessions,
  decisions, forecasts, and notebook hygiene.
- Skills for Claude Code and Codex that let the agent operate that CLI while the
  human directs the research conversationally.
- Profiles and outcome kinds for investigations, reviews, decisions, forecasts,
  recurring beats, and shared source ledgers.
- A portable notebook format: OKF v0.2 Markdown and YAML in Git, readable in
  Obsidian and ordinary text tools, with append-only provenance and event logs.
- Exports for BagIt, CSL JSON, render data, and policy-filtered public OKF
  bundles.

## Put it into the workflow

Install the plugin for the active harness. Its notebook-creation skill checks
for the `flip` CLI and guides the one-time tool installation when needed.

Then use flip for source-backed research already happening in the repository.
Choose the notebook kind that matches the job, keep the source systems,
retrieval tools, databases, and publishing paths that already own their parts
of the workflow, and use the notebook as the durable research record connecting
them.

Existing research does not need to be migrated before work begins. Open a
notebook for the investigation at hand; the record can grow, adopt a more
specific outcome, join a beat, or connect to other notebooks as the work does.

## The operating contract

- [AGENTS.md](../AGENTS.md) — capture before cite, judge after reading, preserve
  lineage and attribution, and run `flip doctor` before handoff.
- [SPEC.md](../SPEC.md) — the notebook format, entities, profiles, beats,
  workspaces, exports, and integration contract.
- [`src/flip/skills/`](../src/flip/skills/) — the seven runtime-neutral
  procedures agents use to create, source, audit, and hand off notebooks.
- [Harness guide](claude-code.md) — Claude Code and Codex installation and
  behavior.
- [Quickstart](quickstart.md) — the CLI mechanics and integration configuration
  underneath the conversational workflow.

flip works alongside search, retrieval, orchestration, databases, and publishing
systems. It does not call an LLM or replace those systems; it gives their
research outputs a shared, inspectable record.

Humans steer the research. The agent maintains the record. The notebook
compounds across sessions.
