---
name: notebook-audit
description: Pre-publish claim audit — invoke before a draft ships, a render publishes, or a notebook is declared done.
---

# notebook-audit

The gate between reporting and publishing: every load-bearing claim faces the
verification bar, and what doesn't clear it gets flagged, not shipped.

## Command map (verbs → leaves)

`flip cli` prints the full, always-current map; the leaves you reach for most:

| to do this | run |
|---|---|
| start a notebook | `flip new <slug> --kind <profile>` |
| capture a source | `flip add-source <url\|doi\|file> [--kind --via --note]` |
| grade a source | `flip grade <id> --grade A\|B\|C --independence … --freshness …` |
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

1. **Lint first.** `flip doctor` — fix every ERROR (bad enums, orphan
   custody, id/alias breakage, under-verified claims) before auditing
   content. Doctor exits 1 while ERRORs remain.
2. **Pull the claim map.** `flip show --claims` (or
   `flip claim list --json`). Audit every claim marked `load_bearing` first,
   then the rest.
3. **Walk each load-bearing claim against the bar** (profile default: two
   independent `original` sources, or one grade-A primary):
   - sources actually support the claim as worded — reread them, don't trust
     the link
   - every cited source is judged — `flip source list` and grade any `?`
     rows first; an ungraded source corroborates nothing
   - corroborating sources are independent — not republishers of the same
     upstream, not `self-interested` parties agreeing with themselves
   - the chain ends at a public, independently verifiable source when
     `citation_rule = "public-terminus"` — no grade-C (LLM/vendor) terminus
   - freshness: a `dated` source can't carry a present-tense claim
4. **Record verifications where they apply.** Beyond corroboration, a claim
   earns `verified` through a recorded check — `flip claim verify C7 --method
   <method> [--against <ref>…] [--note …]` (append-only; records are added,
   never edited):
   - `adversarial` — a skeptic pass that sought disconfirming evidence and
     found none. **Clears the `verified` gate on its own.**
   - `recomputation` — the result re-derived independently. **Clears the gate
     on its own.**
   - `independent-sources` — documents the corroboration *reasoning*; it does
     **not** satisfy the gate by itself (the recomputed independent-source
     count does). Use it to leave a trail, not as a shortcut.
   The corroboration bar is unchanged — the vocabulary widens the honest ways
   to clear it; it never softens it.
5. **Move statuses honestly.** `flip claim status C7 verified` only when the
   bar is genuinely met — the corroboration count OR a recorded
   adversarial/recomputation verification (flip refuses otherwise — do not
   game it by regrading sources you haven't reread). Otherwise `needs-2nd`,
   `unconfirmed`, or `retracted`, with a `flip log` line saying why.
6. **Emit the coverage map** into `notebook.md` (or the draft's changelog):
   three lists — **solidly sourced** (verified, bar met), **authorial frame**
   (interpretation presented as such, no claim needed), **flagged for
   further reporting** (asserted/needs-2nd; must be softened or cut before
   publish).
7. **Close the hypothesis loop.** Note in `notebook.md` what survived the
   reporting: which hypotheses stood, which falsifiers fired.
8. **Final pass.** `flip doctor` again — clean exit — and
   `flip log "audit: <n> load-bearing claims, <n> verified, <n> flagged"`.

Do not mark a claim verified without the corroboration bar — independent
original sources or a grade-A primary, actually reread — and never soften
the bar by editing statuses or grades directly in page frontmatter: go
through `flip claim status` and `flip grade`, which enforce and recompute
(hand-set corroboration counts show up as doctor drift findings).
