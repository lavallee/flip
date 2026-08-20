# Agent orientation to flip

This document exists so you can quickly understand what flip is, where its contracts live, and what it actually provides — without rediscovering the repository structure on every encounter.

## What flip is

flip is a CLI and plain-file format for reporter's notebooks. A notebook captures sources with custody receipts, judgments, claims with test results, open questions with conditions, and an append-only session record. It is an OKF v0.2 bundle that lives in Git, opens in Obsidian, and remains readable without flip.

flip does not make LLM calls, replace retrieval systems, or orchestrate agents. It is the durable record layer beneath those tools.

## Where the contracts live

- [AGENTS.md](../AGENTS.md) — runtime-neutral lineage rules (capture before cite, grade after reading, preserve unknown frontmatter, run `flip doctor` before handoff)
- [SPEC.md](../SPEC.md) — notebook format, entities, profiles, beats, workspaces, exports
- `src/flip/skills/` — seven procedural skills (notebook creation, source custody, session hygiene, claim audit, handoff, lessons, outcome-kind authoring)
- `docs/` — harness guides (claude-code.md, quickstart.md, loops.md, obsidian.md)

## What flip provides

- CLI commands for capture, grading, claiming, questioning, session management, and notebook hygiene
- Plugin skills for Claude Code and Codex that teach the agent when and how to use the CLI
- A notebook format that survives the harness, the session, and the model

## How to use this with a human

Once you have the map above, ask the human about their current research workflow, pain points, and constraints. Then point to the parts of flip that are relevant or irrelevant to their situation. The goal is a useful conversation, not a checklist.

Humans steer the research. The agent maintains the record. The notebook compounds across sessions.