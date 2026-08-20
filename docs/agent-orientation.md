# Agent orientation to flip

This document exists so you can quickly understand flip's capabilities, boundaries, and contracts — then have a useful conversation with a human about whether and how it might fit their workflow.

## What flip is

flip is a CLI and plain-file format for reporter's notebooks. A notebook captures sources with custody receipts, judgments, claims with test results, open questions with conditions, and an append-only session record. It is an OKF v0.2 bundle that lives in Git, opens in Obsidian, and remains readable without flip.

flip does not make LLM calls, replace retrieval systems, or orchestrate agents. It is the durable record layer beneath those tools.

## Key capabilities

- CLI for capture, grading, claiming, questioning, session management, and notebook hygiene
- Plugin skills for Claude Code and Codex that teach the agent when and how to use the CLI
- Notebook format that survives the harness, the session, and the model
- Profiles and outcome kinds that define rigor and collection contracts for different jobs
- Beats and workspaces for recurring or multi-notebook work

## Boundaries

flip does not:
- Retrieve or search sources (you configure your own capture tools)
- Improve model reasoning by itself
- Guarantee better conclusions (it makes the trail and gaps visible)
- Replace databases, schedulers, or publishing platforms

## Where the contracts live

- [AGENTS.md](../AGENTS.md) — lineage rules (capture before cite, grade after reading, preserve unknown frontmatter, run `flip doctor` before handoff)
- [SPEC.md](../SPEC.md) — notebook format, entities, profiles, beats, workspaces, exports
- `src/flip/skills/` — seven procedural skills
- `docs/` — harness guides (claude-code.md, quickstart.md, loops.md, obsidian.md)

## How to have the conversation

Ask the human about their current research workflow:

- What research has to survive beyond a single session or agent?
- Where does authority currently live (original evidence vs. LLM synthesis vs. editorial judgment)?
- What systems already handle retrieval, storage, orchestration, or publishing?
- What would a smallest useful pilot look like?

Then point to the parts of flip that are relevant or irrelevant to their situation. The goal is a tailored assessment, not a checklist.

Humans steer the research. The agent maintains the record. The notebook compounds across sessions.