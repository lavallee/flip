# flip in Claude Code

flip was built to be operated conversationally: you direct the research the
way you already talk to your agent, and flip is the discipline the agent
works under — capture before cite, judgments recorded, claims gated, the
whole trail in plain files. This guide covers the Claude Code plugin: what
it installs, what each piece does, and what a working session looks like.

Nothing here is Claude Code-specific in substance. The skills are plain
`SKILL.md` files any agent runtime can load, and every behavior described
below is the CLI underneath. The plugin is packaging: the skills, a custody
hook, and a versioned channel that tracks releases.

## Install

In Claude Code:

```
/plugin marketplace add lyra-forge/marketplace
/plugin install flip@lyra-forge
```

And the CLI the skills drive, on your PATH:

```bash
uv tool install flip-notebook      # or: pipx install flip-notebook
```

The marketplace does not pin versions, so `/plugin update flip@lyra-forge`
(or `claude plugin update flip@lyra-forge` from a shell) tracks releases.
The plugin's version matches the PyPI release it shipped with; keeping the
CLI and plugin in step is one `uv tool upgrade flip-notebook` away.

## What a session looks like

You do not issue flip commands. You ask questions and direct follow-ups;
the agent runs the notebook:

> **You:** People keep saying NJ school enrollment dipped in the pandemic.
> Did it? Did it come back?
>
> **Agent:** *creates a notebook, captures four NJ DOE fall-enrollment
> files — local bytes, hashed at capture — grades each, computes statewide
> totals two independent ways, records the claims, and answers.* The dip
> was real but modest — down 0.98% in fall 2020 — and it fully recovered
> by 2023-24. Three claims verified by recomputation; one question
> answered; a new one opened — what's driving the recent decline?
>
> **You:** Interesting — keep an eye on that. What would change the answer?
>
> **Agent:** *records the open question with the surface that could answer
> it, arms a reopen trigger on the answered one ("2026-27 fall file
> posts"), and ends the session with a summary a cold reader can pick up.*

What the conversation leaves behind is the notebook: one markdown page per
source, claim, question, decision, and session, custody bytes under
`sources/raw/`, an append-only work log. Browsable on GitHub, in any
editor, or as an Obsidian vault — real ones are at
[flip-examples](https://github.com/lavallee/flip-examples), none of which
had a human typing the commands.

## The seven skills

Each skill is a procedure the agent loads when the work calls for it
(namespaced `flip:notebook-*`):

| skill | when it engages | what it enforces |
|---|---|---|
| `notebook-create` | "start a notebook," a new research thread | the right kind/profile for the outcome; two-file start; the manifest |
| `notebook-source` | capturing anything the work will rely on | capture before cite; grading after reading; the return-envelope lanes |
| `notebook-log` | every working episode | session open/close around the work; log-as-you-go; promote before the episode ends |
| `notebook-audit` | before a draft ships or a claim is leaned on | the verification bar; attribution tests on subject claims; doctor findings triaged |
| `notebook-handoff` | passing work to another agent or person | what a cold reader needs; open questions with watching surfaces |
| `notebook-lessons` | after something went wrong or unusually right | lessons as durable pages, not chat scroll |
| `notebook-kind-author` | defining a new outcome kind | contract requirements a doctor can check |

Two conventions matter more than any skill:

- **Attribution is `FLIP_ACTOR` (or the `--actor` flag)** — `agent:claude`,
  `human:marc`. Every event and page records who did it; OKF consumers
  derive trust tiers from the `human:` prefix. There is no other actor
  mechanism, so an agent that invents flags gets refused rather than
  misattributed.
- **LLM output is a lead, not evidence.** Synthesis the agent produces —
  including `flip ask` output — is grade C until the cited public sources
  are captured and judged. The skills repeat this because it is the rule
  agents most want to skip.

## The custody hook

The capture rule is written in the skills, but an agent doing research
reads a skill only after deciding to use flip — which is exactly the
decision that goes wrong. So the plugin puts the rule at the moment of the
act. Inside a flip notebook (and silent everywhere else):

- **On the first web fetch of a session** it names the notebook and the
  capture command — the reminder arrives with the fetch, not after.
- **Each fetch** is recorded as read-but-not-yet-in-custody.
- **At turn end**, if anything was read and never captured, the hook says
  so and holds the turn open once — the one deliberate interruption.

It is conservative by construction: a URL counts as captured on a loose
match against provenance, so it under-reports rather than nags falsely.
Web *search* is deliberately not hooked — discovery is capture-free by
doctrine; a search returns leads, and a lead is not evidence.

## Directing the work

Phrases the skills are built to answer:

- "Start a notebook on X" / "make this a literature review" (kinds)
- "Capture that before you cite it" — though the hook usually gets there first
- "How solid is that claim?" → grades, corroboration, tests on the page
- "Keep this question open — what would answer it?" → `resolves_via`
- "We're done for now, but reopen this if the numbers restate" →
  `--reopen-when`
- "What did this evidence actually answer?" → an evidence note with an
  `as-worded` / `narrower` / `adjacent` scope verdict
- "Write up the follow-up as a contract" → a commission with its input
  universe, stop condition, and does-not-redo boundary
- "Hand this off" / "what's the state of the notebook?" → `flip show`,
  the handoff skill

The agent's judgment stays in the conversation; the notebook records what
was done and why. `flip doctor` validates after the fact — it never
gatekeeps, so nothing about the discipline blocks the work in flight.

## Many notebooks, one vault

A repo or vault holding several notebooks becomes a **workspace**
(`flip ws init`): each notebook binds to a handle, refs qualify as
`recipes:A3`, and `flip ws show` gives the agent a merged roster of open
questions and claims needing work across all of them — the view a session
starts from when the work spans notebooks.

## Other runtimes

The plugin is one packaging of [src/flip/skills/](../src/flip/skills/) —
plain `SKILL.md` files with no Claude-specific syntax. Codex users can add
the same marketplace (`codex plugin add flip@lyra-forge`); any other
runtime can load the files directly or via the
[spindle](https://github.com/lavallee/spindle) package named `flip`.
[AGENTS.md](../AGENTS.md) is the runtime-neutral contract: the five-minute
tour, the lineage rules, and task recipes.
