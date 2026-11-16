---
name: notebook-handoff
description: Write or refresh HANDOFF.md for cold pickup — invoke when pausing work, switching actors, or ending an engagement.
---

# notebook-handoff

The next reader has zero context and no access to your reasoning except what
the notebook holds. HANDOFF.md is the cold-start view: state of play, not
history (history is the ledgers' job).

## Orient cheaply first

The pickup path you are writing for: `flip show` → `HANDOFF.md` → targeted
`flip open <id>`. Cold orientation by reading pages cost ~40K tokens on a
507-page notebook; a handoff that makes the next actor browse directories
has failed. Generated `index.md` files are directory listings, never reading
material (`references/index.md` alone measured 73KB). At scale, point the
reader at list commands with narrowing flags (`flip question list --status
open`, `flip claim list --status needs-2nd`) instead of at directories.

Use `flip cli` when you need syntax beyond the targeted commands below. Set
`FLIP_ACTOR` before refreshing the handoff or logging the final state.

## Checklist

1. **Lint before handing off.** `flip doctor` — never hand off with ERROR
   findings; note any WARNs you're deliberately leaving in the log.
2. **Read what the next actor will see.** `flip show` (the hot view) and
   `flip show --stale` — these plus HANDOFF.md are the pickup surface. Active
   directives print at the top of `flip show`: they are a person's standing
   instructions, they carry over to the next actor as they are, and you do not
   withdraw one to tidy up. `flip lead list` shows candidate sources still
   untriaged.
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
   If the episode exposed recurring friction or a reusable fix, point to the
   short lesson and its working command/plugin in **Don't redo**. Use
   notebook-lessons and notebook-extend to preserve it while the evidence is
   available; don't add an improvement project to every handoff.
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
