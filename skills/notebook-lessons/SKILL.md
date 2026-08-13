---
name: notebook-lessons
description: End-of-life distillation to lessons.md — invoke when a notebook is done, published, killed, or archived, so its method survives it.
---

# notebook-lessons

A notebook's last act is teaching the next one. lessons.md is prescriptive
advice for future notebooks — method, not findings (findings live in the
analysis; this is about how the work went).

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

1. **Confirm end-of-life.** The notebook's `status` (root `index.md`
   frontmatter) is moving to `done`, `published`, or `archived`. Run the
   audit first if it's publishing (see notebook-audit); run `flip doctor`
   regardless — profile minimums become ERRORs at these statuses.
2. **Mine the trail**, not your memory:
   - `flip show --claims` — which claims died, which needed the most work,
     what corroboration was hardest to get
   - `decisions/` pages — which decisions paid off, which you'd reverse
   - `log/passed.jsonl` — rejections that turned out right or wrong
   - `log/log.jsonl` and `sessions/` — walls hit, pivots, which tools
     and fetchers earned their keep
   - `notebook.md` hypotheses — what survived the reporting and why
3. **Write `lessons.md`** at the notebook root. Each lesson is prescriptive
   and portable: *"do X / avoid Y, because Z happened here"* — with ledger
   ids as evidence (`[D4]`, `[C7]`, `[P2]` — `flip open` resolves them).
   Cover at least: source
   landscape (which wells were rich/dry), method (what sequence worked),
   tooling (fetcher/processing gotchas), and scope (what this kind of
   notebook should include next time).
4. **Feed the compound loop.** If a beat or a standing skill system exists
   above this notebook, propose the top 1–3 lessons upward — cross-notebook
   references use `<handle>:<id>` (the `#` form was removed in 0.10).
5. **Close out.** Set the final `status` in the root `index.md` frontmatter
   (only that key; the body is a generated listing),
   `flip log "lessons distilled; notebook <done|published|archived>"`, and
   consider `flip export bag <dest>` for cold archival. Re-run `flip index`
   so the registry reflects the final state.

Do not write lessons as a narrative of what happened or a restatement of
findings — a lesson that doesn't tell the next notebook what to do
differently (and point at the evidence here) is a diary entry, not a lesson.
