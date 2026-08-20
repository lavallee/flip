# flip

## Give your research a durable structure, not another prose dump

Your agent finishes a research task. The next agent starts from the chat log or from
scratch. The work doesn't survive.

flip brings rigor. It provides a spec for storing questions, claims, and raw
materials with provenance, and tools for conducting research like a reporter, not a
stenographer. flip notebooks can be evolved by humans and agents. The work
compounds across sessions.

The flip spec defines an agentic reporter's notebook format that works with OKF
and LLM- and wiki-friendly tools like Obsidian.

In Claude Code, Codex, or another agent harness, the agent operates flip: it
captures the material the work relies on, records how each source was judged,
keeps claims and questions at honest states, and leaves an attributed trail in
plain files. Humans rarely need to type the CLI commands.

**[See flip in action](https://lavallee.github.io/flip/flipbook.html)** ·
**[Explore real notebooks](https://lavallee.github.io/flip-examples/)** ·
**[Give flip to your agent](docs/agent-orientation.md)** ·
**[Get flip](#install-for-your-harness)**

## Start with your agent

### Curious about how flip can work for you?

**[Hand this to your agent.](https://raw.githubusercontent.com/lavallee/flip/main/docs/agent-orientation.md)**

### Install for your harness

Install the plugin in Claude Code:

```text
/plugin marketplace add lyra-forge/marketplace
/plugin install flip@lyra-forge
```

Or in Codex:

```bash
codex plugin marketplace add lyra-forge/marketplace
codex plugin add flip@lyra-forge
```

Start a new agent session after installing. The plugin ships seven procedural
skills covering notebook creation, source custody, session hygiene, claim audit,
handoff, lessons, and outcome-kind authoring. Claude Code also receives a custody
hook around web fetches; Codex's hosted web tools do not expose that hook event,
so its skills and `flip doctor` carry the discipline instead.

When an approved pilot starts, the creation skill checks whether the `flip` CLI
is available and guides its one-time installation as a standalone tool if needed.
The executable enforces the notebook contract; the human does not have to assemble
the two layers up front.

Other harnesses can read [AGENTS.md](AGENTS.md) as the runtime-neutral contract
and load the plain [`SKILL.md` files](src/flip/skills/) directly or through the
[spindle](https://github.com/lavallee/spindle) package named `flip`.

### Use it conversationally

> **You:** People keep saying NJ school enrollment dipped in the pandemic. Did
> it? Did it come back? Use flip so someone else can audit and continue the work.
>
> **Agent:** *starts a notebook, captures four NJ DOE enrollment files, grades
> them, computes the totals two independent ways, records three verified claims,
> answers the question, and opens the logical follow-on: what is driving the more
> recent decline?*

What remains is not a transcript or a final report. It is a browsable notebook
with the captured workbooks, hashes, derivations, claims, question journey,
session record, and named actor. [Read the real
notebook](https://github.com/lavallee/flip-examples/tree/main/nj-schools) or
[browse its rendered form](https://lavallee.github.io/flip-examples/).

Useful directions include:

- “Start a pursuit notebook for this question.”
- “Capture that before relying on it, then tell me how strong it is.”
- “What did this evidence answer: the question as worded, a narrower one, or an
  adjacent one?”
- “Try to disprove the load-bearing claims and record the probes that fail too.”
- “Keep the unresolved branch open and say what would resolve it.”
- “Hand this off so a cold agent can continue without reconstructing the trail.”

The full harness guide is [docs/claude-code.md](docs/claude-code.md).

## What flip changes

### Work the question, not just the first answer

A polished report is not the research record. In a 2026 benchmark of 100
deep-research tasks, the best evaluated system achieved 0.55 overall F1 and
systems covered only about half of the necessary search queries
([LiveDRBench](https://proceedings.iclr.cc/paper_files/paper/2026/file/114e1dc345fe31b8b9b0c6f7b55a0644-Paper-Conference.pdf)).
In DeepTRACE's dated August 2025 snapshot of 303 questions and 2,727
system-query samples, evaluated deep-research configurations were one-sided on
54.7%–94.8% of debate queries, while citation accuracy ranged from 31.4%–79.1%
([DeepTRACE](https://proceedings.iclr.cc/paper_files/paper/2026/file/ad08767706825033b99122332293033d-Paper-Conference.pdf)).

flip does not make a model reason better by itself. It makes the route durable:
follow-on questions, corroboration gaps, closer reads, recomputations, failed
tests, narrower and adjacent answers, reopen conditions, and bounded continuation
work remain available to the next session.

### Keep useful signals without promoting them prematurely

Capture and judgment are separate acts. A source can be held but ungraded; a
promising synthesis can remain a grade-C lead; a claim can be asserted,
challenged, corroborated, superseded, or rejected; an audience's belief can be
recorded without becoming the notebook's belief. Ungraded material counts toward
nothing, but it is not thrown away merely because it needs more work.

Claims record more than truth status. Tests say which error they looked for and
how it would have appeared. Stances say what someone is doing with a claim.
Absence claims name the surfaces searched, because a null is only as strong as
its coverage.

### Let the research outlive the session, agent, or model

Every source, claim, decision, question, and session is a Markdown page with an
immutable id. Every event names its actor. Raw captures and hashes establish
custody; append-only JSONL preserves history; generated views provide a bounded
cold-start surface. Different agents can continue the same notebook without
silently replacing one another's reasoning or reconstructing the investigation
from chat logs.

At rest, a notebook is a conformant [Open Knowledge Format
(OKF v0.2)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
knowledge bundle. It works in Git, opens as an Obsidian vault, and remains
readable with `less` if flip disappears.

## Real notebook outcomes

- **Data investigation:** the NJ schools notebook captured four state
  workbooks, found file oddities, recomputed totals two ways, corrected the
  popular pandemic framing, and opened a more consequential follow-on question.
- **Literature review:** the RAG/hallucination review froze criteria before
  searching and preserved its denominator—2,600+ records identified, 31
  examined, seven advanced, four excluded, three included—including a canonical
  paper excluded on license alone.
- **Honest non-answer:** the EV-charger pursuit distinguished failed-visit data
  from measured uptime, answered the narrower question, left the national trend
  unresolved, and armed conditions that should reopen it.
- **Long-running work:** an unattended loop ran 43 sessions over nearly 67
  hours, keeping 380 sources, 82 claims, 47 questions, corrections, bounded
  nulls, and two deliberately unconfirmed load-bearing claims coherent.

[Browse every example and its receipts](https://github.com/lavallee/flip-examples).
These are observed uses, not a controlled claim that flip-backed agents produce
better conclusions than agents without notebooks.

## Start from the outcome

Profiles define the notebook's rigor and operating contract. Outcome kinds add
a collection contract for a particular deliverable.

| What you need | Start with |
|---|---|
| Screen whether an angle is worth pursuing | `scout` |
| Run one question to ground | `pursuit` |
| Survey a field or prepare a publishable review | `research-review` or `lit-review` |
| Recompute, reconcile, or investigate data | `data-investigation` |
| Prepare an evidence-backed choice | `decision-packet` |
| Record forecasts and what will resolve them | `forward-set` |
| Maintain a shared source spine | `ledger` |
| Work inside confidential boundaries | `engagement` |

A **beat** sits above notebooks when the mission recurs. It keeps coverage memory
and computes the next bounded item—an unmet load-bearing claim, returned
commission, due forecast, open question, or ungraduated thread—so each pass does
not begin by rereading the whole corpus. A **workspace** binds many notebooks
under stable handles so agents can resolve and audit them together.

## What the agent maintains under the hood

The ordinary loop is capture → judge → assert → test → continue or hand off:

```bash
flip new nj-schools --kind pursuit --title "What changed in NJ enrollment?"
cd nj-schools
flip session start enrollment-sweep --model <model> --tools <tools>
flip add-source ./districts.csv --note "district enrollment table"
flip grade F1 --independence independent --basis official-record --base-defined
flip claim add "Enrollment fell 4.2% since 2021" --source F1 --load-bearing
flip question add "What is driving the decline?" --resolves-via "NJ DOE fall snapshot"
flip show
flip doctor
flip session end enrollment-sweep --summary "..."
```

Humans generally direct those acts rather than typing them. `flip cli` prints an
always-current command map; [docs/quickstart.md](docs/quickstart.md) explains the
mechanics and every legitimate path through the verification gates.

## The portable artifact

A notebook is one directory:

```text
index.md                 # OKF manifest + generated hot view
notebook.md              # prose working memory
references/              # one page per source
claims/                  # one page per assertion
questions/               # the question journey
decisions/               # forks resolved, with reasons
sessions/                # attributed working episodes
sources/raw/              # captured bytes, immutable
sources/_provenance.jsonl # append-only custody history
derived/                  # extraction and recomputation receipts
log/                      # append-only work and negative evidence
```

Human-slug filenames stay readable; immutable ids such as `F1`, `C3`, and `Q2`
keep citations stable through sanctioned renames. Unknown frontmatter keys and
page bodies survive round trips, so humans, editors, and other tools can work in
the same files.

Notebooks can be exported as BagIt, CSL JSON, render JSON, or a policy-filtered
OKF copy. The public export can withhold raw custody and private event history;
rights still have to be established by the workflow's source-selection and
licensing policy. It is rights-aware publishing infrastructure, not an automatic
legal-clearance system.

## Boundaries

flip is not a retrieval system, vector store, scheduler, agent framework,
database, or publishing platform. Integrations for capture, extraction,
research, and local knowledge remain operator-configured. The core makes no LLM
calls and requires no service; its two third-party libraries are Click and
PyYAML.

The CLI enforces structural invariants and exposes missing work. It cannot make
careless source grades honest or guarantee a good conclusion. Generated views
and `flip beat next` support bounded re-grounding, but the project has not yet
run a controlled benchmark showing that CLI-backed work always uses fewer
tokens.

## Documentation

- [Agent orientation](docs/agent-orientation.md) — read-only fit assessment and
  smallest-pilot procedure
- [Claude Code and Codex](docs/claude-code.md) — plugin behavior, skills, updates,
  and custody-hook boundary
- [Quickstart](docs/quickstart.md) — full CLI mechanics and capture configuration
- [AGENTS.md](AGENTS.md) — complete runtime-neutral lineage contract and recipes
- [Specification](SPEC.md) — OKF bundle, entities, profiles, beats, workspaces,
  exports, and integration contract
- [Obsidian](docs/obsidian.md) — human editing and the companion plugin
- [Running a beat on a loop](docs/loops.md) — recurring and unattended passes
- [llms.txt](llms.txt) — compact documentation map for agents

Status: spec draft v0.21; package 0.21.0; Python 3.12+; MIT licensed. Changes are
tracked in [CHANGELOG.md](CHANGELOG.md); contributions are welcome through
[CONTRIBUTING.md](CONTRIBUTING.md).
