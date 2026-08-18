---
name: notebook-log
description: Session hygiene for a working episode — invoke around every LLM run, research sweep, or extended work burst inside a notebook.
---

# notebook-log

The reasoning chain is evidence too. One session record per working episode;
promote what matters out of it before the episode ends.

## Orient cheaply first

`flip show` → `HANDOFF.md` → targeted `flip open <id>`, in that order — cold
orientation by reading pages cost ~40K tokens on a 507-page notebook.
Generated `index.md` files are directory listings, never reading material
(`references/index.md` alone measured 73KB). At scale, narrow before you
read: `flip question list --status open`, `flip claim list --status
needs-2nd`, `flip source list` — then open only the pages this episode
touches.

## Command map (verbs → leaves)

`flip cli` prints the full, always-current map; the leaves you reach for most:

| to do this | run |
|---|---|
| start a notebook | `flip new <slug> --kind <profile>` |
| capture a source | `flip add-source <url\|doi\|file> [--kind --via --note]` |
| grade a source | `flip grade <id> --independence independent\|corroborated\|self-reported\|derivative --basis … [--n … --base-defined\|--base-undefined]` — the letter is derived |
| assert a claim | `flip claim add "<text>" --source <id> [--about <id>] [--load-bearing]` |
| link/unlink sources | `flip claim source add\|rm <C#> <id…>` |
| record a verification | `flip claim verify <C#> --method adversarial\|independent-sources\|recomputation` |
| move a claim's status | `flip claim status <C#> <status>` |
| absence claims / derivation | `flip claim add --absent-from corpus\|named_surfaces\|world --surface …` (a null's weight is its coverage) · `flip claim derives add\|rm <C#> <C#>` (what a claim rests on) |
| commission contracts | `flip commission add "<deliverable>" --universe … --stop … --does-not-redo … [--for Q#]` · `status <K#> dispatched\|returned\|declined [--consumed …]` · `list` |
| questions | `flip question add\|note\|repose\|answer\|close\|dormant\|reopen\|list` — evidence accretes via `note` (--answers as-worded\|narrower\|adjacent, --zero-yield <cause>); answers/closes can arm `--reopen-when` triggers |
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
   Research sweeps belong inside this session: `flip find "<q>"` for candidate
   leads, `flip ask "<q>"` for cited synthesis (it saves its raw output under
   `sessions/raw/` and logs a breadcrumb automatically), `flip recall "<q>"` for
   what you already hold. `ask` synthesis remains a grade-C lead until the cited
   public sources are captured and judged.
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
