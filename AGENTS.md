# AGENTS.md — flip's agent contract

flip is a CLI and plain-file format for reporter's notebooks: captured sources,
explicit source judgments, claims, questions, decisions, and work sessions that
humans and agents can inspect and continue.

This file is the minimum always-loaded contract. Complete examples and edge
cases live in [docs/agent-reference.md](docs/agent-reference.md). Use `flip cli`
for the current command map and the task skills under
[`src/flip/skills/`](src/flip/skills/) for procedural checklists.

## Recognize a notebook

A notebook root is an `index.md` whose YAML frontmatter contains `flip:`. Every
`flip` command walks upward to find it. A root with `notebook.toml` is an older
notebook; run `flip migrate` before using it.

If no notebook exists and the work is source-backed research, choose a kind
with `flip kind list` and use the notebook-create skill.

## Before the first write

Set attribution before `flip new`. A `pursuit` notebook creates its primary Q1
during that command, so setting the actor afterwards is too late.

```bash
export FLIP_ACTOR="agent:<name>"   # humans: human:<name>; tools: tool:<name>
flip --version
```

Attribution precedence is `--actor` > `FLIP_ACTOR` > detected harness/user.
There is no other actor flag. `--notebook` / `FLIP_NOTEBOOK` similarly pins a
root and refuses disagreement with the current directory.

If the CLI is missing, install the standalone `flip-notebook` tool; do not add
it to the researched project's runtime dependencies. See
[Getting started](docs/getting-started.md).

## Non-negotiable lineage rules

1. **Capture before cite.** External material enters through `flip add-source`,
   which preserves bytes, a hash, and provenance. Never paste fetched text into
   the notebook as though it were custody.
2. **Capture and judgment are separate.** Every new source starts at grade `?`
   and counts toward nothing. Read what landed, then use `flip grade`.
3. **LLM and retrieval synthesis is a lead.** Treat it as grade C until its
   public sources are captured and judged separately.
4. **Claims have honest states.** Add a claim as soon as the work relies on it.
   Do not bypass verification refusals; add evidence or record an allowed
   adversarial/recomputation check.
5. **Citation roles matter.** `--source` cites a witness. `--about` cites the
   document a claim is about and owes a severe surviving attribution test
   instead of a corroboration count.
6. **Sessions surround the work.** Start a session before an LLM run or research
   sweep, promote useful outputs to durable entities, and end with a cold-pickup
   summary.
7. **History is append-only.** Never edit or delete lines in `log/*.jsonl`,
   `sources/_provenance.jsonl`, or `derived/_derivations.jsonl`. Never hand-edit
   `sources/raw/`; recapture instead.
8. **Generated views are disposable.** flip rewrites `index.md` bodies,
   directory indexes, and `log.md`. Edit entity pages, `notebook.md`, and
   `HANDOFF.md`, not listings.
9. **Round trips preserve foreign data.** When editing a page, change only the
   intended keys/prose; preserve unknown frontmatter and the rest of the body.
10. **Ids are immutable and never reused.** Use `flip rename` for entity-page
    filenames; never `mv` one yourself.
11. **Status, stance, and tests are different axes.** Record positions with
    `flip claim stance`, probes with `flip claim test`, and comparative
    replacement with `flip claim supersede`.
12. **Finish with an audit.** Run `flip doctor`; fix every ERROR and read every
    WARN. Expected-until-use notices are completion reminders, not current
    failures.

## Task procedures

Read the matching skill completely before acting:

| Task | Skill |
|---|---|
| Create or choose a notebook kind | [`notebook-create`](src/flip/skills/notebook-create/SKILL.md) |
| Capture, extract, or grade a source | [`notebook-source`](src/flip/skills/notebook-source/SKILL.md) |
| Run a working episode | [`notebook-log`](src/flip/skills/notebook-log/SKILL.md) |
| Audit claims or prepare publication | [`notebook-audit`](src/flip/skills/notebook-audit/SKILL.md) |
| Pause or transfer the work | [`notebook-handoff`](src/flip/skills/notebook-handoff/SKILL.md) |
| Preserve a process lesson | [`notebook-lessons`](src/flip/skills/notebook-lessons/SKILL.md) |
| Define an outcome kind | [`notebook-kind-author`](src/flip/skills/notebook-kind-author/SKILL.md) |
| Route a reusable process change | [`notebook-extend`](src/flip/skills/notebook-extend/SKILL.md) |
| Define a reusable work sequence | [`notebook-workflow-author`](src/flip/skills/notebook-workflow-author/SKILL.md) |
| Package and share extensions | [`notebook-plugin-author`](src/flip/skills/notebook-plugin-author/SKILL.md) |

The common operating loop is orient → select → open → work → check → close →
continue or stop:

```bash
flip next --explain
flip session start <slug> --model <model> --tools <tool> \
  --workflow <id> --phase <phase> --item <id>
flip add-source <url-or-file> --note "<why it matters>"
flip grade <id> --independence ... --basis ...
flip claim add "<assertion>" --source <id> --load-bearing
flip show
flip doctor
flip session end <slug> --summary "<cold-pickup line>" \
  --output <path-or-id> --check doctor
flip next
```

Use `flip show` for the hot state, `flip open <id>` for targeted reading, and
`flip cli --json` when a machine-readable command inventory is useful.

## Keep repeatable gains

When work exposes recurring friction or a reusable fix, preserve its trigger,
working method, evidence and limits in an author-owned lesson or decision page.
Use notebook-extend to improve an existing plugin or keep the smallest useful
extension; try another relevant case before claiming repeatability. Do this
while the evidence is fresh, without turning every handoff into a new project.

## Handoff

Before stopping, promote anything the work will rely on, close the active
session, run doctor, refresh `HANDOFF.md` when another actor needs cold pickup,
and log one line stating where the work stands. Cite entity ids (`[F1]`, `[C2]`,
`[Q3]`) instead of restating their contents without lineage.
