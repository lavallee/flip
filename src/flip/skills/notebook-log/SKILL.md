---
name: notebook-log
description: Session hygiene for a working episode — invoke around every LLM run, research sweep, or extended work burst inside a notebook.
---

# notebook-log

The reasoning chain is evidence too. One session record per working episode;
promote what matters out of it before the episode ends.

## Checklist

1. **Open the session before the work.**
   ```bash
   export FLIP_ACTOR="agent:<name>"
   flip session start <slug> --model <model> --tools <tool> --tools <tool>
   ```
   It prints the session page path (`sessions/<UTC stamp>-<slug>.md` — an
   entity page, `type: Work Session`). Fill in **Goal** and **Prompt** now,
   while they're true.
2. **Log as you go.** Terse work-log lines for anything a future reader must
   retrace: `flip log "fetched X"`, `flip log "hit wall: Y requires auth"`.
   Walls and pivots are the payload — git can't recover the why.
   A retrieval or LLM-backed lookup belongs inside this session; record the
   configured command's name with `--tools`. Its synthesis remains a grade-C
   lead until the cited public sources are captured and judged.
3. **Promote before you close.** Walk the episode's output and route each
   item to its page or ledger:
   - leads worth relying on → `flip add-source` + `flip grade`
     (session text itself is grade C until promoted)
   - assertions the work now leans on → `flip claim add --source ...`
   - follow-ups → `flip question add "<q>"`
   - forks resolved → `flip decide --question ... --decision ... --why ...`
   - roads not taken → `flip pass "<thing>" --reason "<why rejected>"`
4. **Record key outputs** in the session file's **Key outputs** section —
   pointers and ids (`[A3]`, `[C2]`, `[Q1]`), not re-pasted content. Keep or
   point to the raw transcript when it exists.
5. **Close it.**
   ```bash
   flip session end <slug> --summary "<what the episode accomplished, one cold-pickup line>"
   ```
6. **Sanity check.** `flip show` — the episode's residue should be visible
   there (open questions, claims needing work, recent log), not trapped in
   the session file.

Do not let findings live only in the session transcript — an unpromoted
session is a lead that dies with the context window; if the work will rely
on it, it goes through source/claim/question pages before `session end`.
