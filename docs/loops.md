# Running a notebook on a loop

Research that keeps going — a beat you sweep weekly, a corpus an agent works
overnight — eventually gets run on a schedule. This is what flip does and,
more importantly, what it deliberately leaves to whatever is running the loop.

flip holds no cadence, schedules nothing, and calls nothing. It records the
policy in one place and computes one view over it. Everything else is yours.

## The one measured problem

The expensive part of an autonomous pass is not the research. It is the
re-grounding: working out, from a standing start, where the last pass left
off. Measured on a real 507-page notebook, orienting cold cost about 40K
tokens of generated views — paid again on every pass, before anything was
learned.

`flip beat next` is the answer to that, computed from records the notebook
already holds.

## Write the policy once

A beat is already a standing mission, so the loop policy lives in its
manifest (SPEC §14.1):

```yaml
# index.md frontmatter, at the beat root
auto:
  selection: [in-flight, commissioned, due, open-question, thread]
  stop: no unblocked item this pass
  authority: capture, grade, claim, publish; never delete custody
  materiality: a reader-relevant public change, not a status edit
  surfaces: [the public site, the shared worklist]
  cadence: daily
```

Only `selection` changes what flip computes — it orders the lanes below. The
rest is policy the *agent* reads and honours; flip validates the shape and
never the judgment. A lane outside the vocabulary is refused rather than
quietly dropped, because a loop running a policy nobody wrote is the one
failure a pass cannot notice from the inside.

## Ask what is next

```bash
flip beat next                 # ranked, with the reason for each row
flip beat next --json          # the same thing for a runtime to read
flip beat next --limit 1       # just the top item; the total is still reported
```

```
dataviz · next 6 of 6
  mission: Track how AI changes data visualization practice
  stop: no unblocked item this pass
  authority: capture, grade, claim, publish; never delete custody
  materiality: a reader-relevant public change, not a status edit

  1. [in-flight] practitioner-experience:C1 · practitioners report a 40% drop
     load-bearing claim at 'asserted' with its bar unmet
  2. [commissioned] practitioner-experience:K1 · survey the 2026 cohort
     commission dispatched and not yet returned; stops when one pass
  3. [due] practitioner-experience:FC1 · will the drop persist?
     forecast resolves 2026-01-15 (overdue 215d)
  4. [due] practitioner-experience:Q2 · who verified the 2026 numbers?
     parked question came due 2026-01-01
  5. [open-question] practitioner-experience:Q1 · does the effect hold at scale?
     open question with no resolves_via surface
  6. [thread] TH2 · specialist vision models
     beat thread, triage 0.5
```

The lanes, in default order — finishing beats starting, and a promise already
made beats a new one:

| lane | what it is |
|---|---|
| `in-flight` | load-bearing claims whose verification bar is unmet |
| `commissioned` | commissions dispatched and not yet returned |
| `due` | forecasts at their resolution date; questions off dormancy |
| `open-question` | the working question roster |
| `thread` | beat threads not yet graduated, by triage score |

Ordering inside a lane is deterministic — notebook slug, then id — so two
agents reading the same corpus pick the same item, which is what makes
concurrent passes safe to run at all.

An empty frontier is **not** the same as "done". flip cannot tell those
apart; the mission's `stop` condition is what does, and the empty view says
so rather than implying an answer it does not have.

## Wire it to a harness

The contract is small enough to fit in a paragraph: invoke something, read
`flip beat next --json`, do the work, let the ledgers be the receipt. Any
scheduler works, because flip is not in the scheduling business.

```bash
#!/bin/sh
# one pass: hand the frontier to whatever agent runtime you use
cd /path/to/the/beat
flip beat next --json --limit 1 > /tmp/next.json
your-agent-runtime --prompt "$(cat prompts/pass.md)" --context /tmp/next.json
```

Point cron, a systemd timer, a CI schedule, or an agent runtime's own loop at
that script. Nothing in flip knows which you chose.

Two things worth putting in the prompt rather than the script, because they
are judgment and not mechanism:

- **The pass contract.** What counts as having done the work — the beat's
  `materiality` line is the honest version of this, and it belongs in front
  of the agent every pass.
- **The authority.** What this pass may change without asking. `authority:`
  records it; nothing enforces it, and you should assume nothing does.

## What flip will not do for you

- **Schedule.** No cadence, no daemon, no wake-ups. `cadence:` is a note to
  the humans and harnesses reading the manifest.
- **Judge whether a pass was worth running.** A pass that edited a status and
  called it progress ought to be visible as one, and deriving that honestly
  from the event log needs a session receipt flip does not define yet. A
  check that guessed would hand you false confidence about exactly the thing
  it exists to doubt. Until it lands, materiality is prose the agent
  self-certifies against — read the log.
- **Parse your other systems.** `surfaces:` lists where the work has to land
  so the agent can go there; flip does not read them. If you have an external
  worklist, it stays external.

## Related

- SPEC §14 (beats) and §14.1 (the `auto:` block and `flip beat next`).
- [quickstart.md](quickstart.md) — the human walkthrough of the core loop.
- [AGENTS.md](../AGENTS.md) — the lineage rules a pass works under.
