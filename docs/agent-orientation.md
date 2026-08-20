# Orient an agent to flip

Use this guide when you are deciding whether flip belongs in an existing
research workflow. The first pass is an assessment, not an installation: inspect
the work as it exists, identify the smallest useful boundary, and report before
changing anything.

## What flip is

flip is a CLI and plain-file format for reporter's notebooks maintained by
humans and agents together. A notebook keeps the material the work relies on,
the judgments made about it, the claims and questions built from it, and an
append-only account of who did what.

At rest it is an OKF v0.2 knowledge bundle: Markdown pages with YAML
frontmatter, raw source custody, and JSONL event history. It can live in Git,
open as an Obsidian vault, travel between agent harnesses, and be read without
running flip.

flip is not a retrieval system, vector store, task tracker, agent framework, or
hosted research product. It is the durable research record beneath those tools.

## Assess fit before changing the repository

Inspect the repository and current workflow read-only. Then report:

1. **What research has to survive.** Name the source material, synthesized
   findings, decisions, recurring questions, and handoffs that currently live in
   chat history, loose documents, application state, or people's memory.
2. **Where authority currently lives.** Distinguish original evidence from
   derived data, LLM synthesis, editorial judgment, and downstream publication.
   Do not propose moving an artifact until you have found its owner.
3. **Whether flip addresses the failure mode.** It is a strong fit when work is
   source-heavy, multi-session, challenged or corroborated later, continued by
   different agents, or published from a private evidence base. It is a weak fit
   for disposable questions, ordinary project documentation, deterministic build
   outputs, or data whose canonical home is already a database with adequate
   lineage.
4. **The smallest useful pilot.** Recommend one bounded question or corpus, the
   proposed notebook location, and the profile or outcome kind that fits. Do not
   begin with a repository-wide migration.
5. **What flip would coexist with.** Name the retrieval, browser, storage,
   orchestration, publishing, and task-management systems that remain owners of
   their current responsibilities.
6. **The costs.** Call out source-byte storage, Git/LFS policy, capture tooling,
   grading and close-reading work, actor attribution, and the discipline required
   to keep generated views and append-only ledgers honest.
7. **A verdict.** Recommend `pilot`, `defer`, or `not a fit`, with the evidence for
   that recommendation and the condition that would change it.

Do not install flip, initialize a notebook, move files, or alter agent
instructions until the person supervising the workflow approves the pilot.

## Choose the smallest notebook shape

Start from the job, not the taxonomy:

| Job | Start with |
|---|---|
| Screen whether an angle is worth pursuing | `scout` |
| Run one question to ground | `pursuit` |
| Survey a field or prepare a publishable review | `research-review` or `lit-review` |
| Recompute, reconcile, or investigate data | `data-investigation` |
| Prepare an evidence-backed choice | `decision-packet` |
| Record forecasts and what will resolve them | `forward-set` |
| Maintain a shared source spine | `ledger` |
| Work inside confidential client boundaries | `engagement` |

Profiles set the notebook's rigor and operating contract. Outcome kinds add a
collection contract for a particular deliverable. A beat sits above notebooks
when the mission is recurring and needs a deterministic next-work view.

## If the pilot is approved

Read the repository's [AGENTS.md](../AGENTS.md) completely before operating the
notebook. Its lineage rules are the contract. In particular:

- capture before cite;
- grade after reading—capture is custody, not judgment;
- keep LLM synthesis at lead grade until public sources are captured and judged;
- record sessions, actors, open questions, failed probes, and negative evidence;
- preserve unknown frontmatter keys and append-only ledgers;
- run `flip doctor` before handoff and resolve every error.

Install the plugin for the active harness first. Its creation skill checks for
the CLI and, with the person's approval, installs `flip-notebook` as a standalone
tool if needed before beginning the pilot. Humans should direct the question and
the boundaries; the agent should handle setup, operate the CLI, and maintain the
notebook.

The deeper guides are:

- [Claude Code and Codex](claude-code.md) — plugin installation and harness behavior
- [Quickstart](quickstart.md) — the full CLI mechanics underneath the agent
- [Running a beat on a loop](loops.md) — recurring and unattended work
- [Specification](../SPEC.md) — the complete portable format contract
