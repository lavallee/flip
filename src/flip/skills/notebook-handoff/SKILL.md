---
name: notebook-handoff
description: Write or refresh HANDOFF.md for cold pickup — invoke when pausing work, switching actors, or ending an engagement.
---

# notebook-handoff

The next reader has zero context and no access to your reasoning except what
the notebook holds. HANDOFF.md is the cold-start view: state of play, not
history (history is the ledgers' job).

## Command map (verbs → leaves)

`flip cli` prints the full, always-current map; the leaves you reach for most:

| to do this | run |
|---|---|
| start a notebook | `flip new <slug> --kind <profile>` |
| capture a source | `flip add-source <url\|doi\|file> [--kind --via --note]` |
| grade a source | `flip grade <id> --independence independent\|corroborated\|self-reported\|derivative --basis … [--n … --base-defined\|--base-undefined]` — the letter is derived |
| assert a claim | `flip claim add "<text>" --source <id> [--load-bearing]` |
| link/unlink sources | `flip claim source add\|rm <C#> <id…>` |
| record a verification | `flip claim verify <C#> --method adversarial\|independent-sources\|recomputation` |
| move a claim's status | `flip claim status <C#> <status>` |
| questions | `flip question add\|repose\|answer\|list` |
| decisions / dead ends | `flip decide …` · `flip pass …` |
| log / sessions | `flip log "<text>"` · `flip session start\|end` |
| views | `flip show [--claims\|--stale] [--json]` · `flip ws show [--open\|--claims] [--json]` |
| resolve an id | `flip open <ref>` · `flip resolve <ref> --json` |
| lint | `flip doctor [--json]` · `flip doctor --workspace [--fix]` |

**Attribution is the `--actor` flag or the `FLIP_ACTOR` env var — there is no
other actor flag.** Precedence: `--actor` > `FLIP_ACTOR` > detected default.
(`--notebook` / `FLIP_NOTEBOOK` pins the notebook root the same way.)

**`flip doctor` prints "expected until use" notes** for profile files that
appear with the work — they harden into ERRORs only at done/published/
archived. They are not problems; don't re-run doctor for reassurance.

## Checklist

1. **Lint before handing off.** `flip doctor` — never hand off with ERROR
   findings; note any WARNs you're deliberately leaving in the log.
2. **Read what the next actor will see.** `flip show` (the hot view) and
   `flip show --stale` — these plus HANDOFF.md are the pickup surface.
3. **Write/refresh `HANDOFF.md`** at the notebook root, current-state only:
   - **State of play** — where the work stands in 3–5 sentences; the working
     thesis and its version (v1, v2…)
   - **Open questions** — from `flip show`, cited by id (`Q3`), with any
     leads on where answers live
   - **Claims needing work** — `asserted`/`needs-2nd` load-bearing claims by
     id (`C7`) and what corroboration each still needs
   - **Next actions** — concrete, ordered; include walls already hit (with
     log pointers) so nobody re-runs into them
   - **Don't redo** — point at `log/passed.jsonl` entries and decision pages
     (`[D2]`) that a newcomer would otherwise relitigate
4. **Update the manifest** if the work is pausing: set `status: dormant`
   (or `done`) in the root `index.md` frontmatter — change only that key
   and leave the body alone (it's a generated listing).
5. **Record the handoff.** `flip log "handoff: <one-line state of play>"`
   and, if an episode is open, `flip session end <slug> --summary ...`.
6. **Verify cold pickup.** Reread HANDOFF.md pretending you know nothing:
   every id it cites must resolve (`flip open <id>` per id, or scan
   `flip source list` / `flip question list` / `flip claim list`), every
   next action must be executable without asking you anything.

Do not write a handoff that summarizes history instead of state — the next
actor needs what is true now and what to do next; if a fact matters, cite
the entity id, don't retell the story.
