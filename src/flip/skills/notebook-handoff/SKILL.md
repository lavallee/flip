---
name: notebook-handoff
description: Write or refresh HANDOFF.md for cold pickup — invoke when pausing work, switching actors, or ending an engagement.
---

# notebook-handoff

The next reader has zero context and no access to your reasoning except what
the notebook holds. HANDOFF.md is the cold-start view: state of play, not
history (history is the ledgers' job).

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
   - **Don't redo** — point at `log/passed.jsonl` and `log/decisions.jsonl`
     highlights that a newcomer would otherwise relitigate
4. **Update the manifest** if the work is pausing: set `status = "dormant"`
   (or `done`) in `notebook.toml`.
5. **Record the handoff.** `flip log "handoff: <one-line state of play>"`
   and, if an episode is open, `flip session end <slug> --summary ...`.
6. **Verify cold pickup.** Reread HANDOFF.md pretending you know nothing:
   every id it cites must resolve (`flip source list`, `flip question list`,
   `flip claim list`, or `grep` the ledgers), every next action must be
   executable without asking you anything.

Do not write a handoff that summarizes history instead of state — the next
actor needs what is true now and what to do next; if a fact matters, cite
the ledger id, don't retell the story.
