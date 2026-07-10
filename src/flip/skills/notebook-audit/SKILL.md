---
name: notebook-audit
description: Pre-publish claim audit — invoke before a draft ships, a render publishes, or a notebook is declared done.
---

# notebook-audit

The gate between reporting and publishing: every load-bearing claim faces the
verification bar, and what doesn't clear it gets flagged, not shipped.

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
4. **Move statuses honestly.** `flip claim status C7 verified` only when the
   bar is genuinely met (flip refuses otherwise — do not game it by
   regrading sources you haven't reread). Otherwise `needs-2nd`,
   `unconfirmed`, or `retracted`, with a `flip log` line saying why.
5. **Emit the coverage map** into `notebook.md` (or the draft's changelog):
   three lists — **solidly sourced** (verified, bar met), **authorial frame**
   (interpretation presented as such, no claim needed), **flagged for
   further reporting** (asserted/needs-2nd; must be softened or cut before
   publish).
6. **Close the hypothesis loop.** Note in `notebook.md` what survived the
   reporting: which hypotheses stood, which falsifiers fired.
7. **Final pass.** `flip doctor` again — clean exit — and
   `flip log "audit: <n> load-bearing claims, <n> verified, <n> flagged"`.

Do not mark a claim verified without the corroboration bar — independent
original sources or a grade-A primary, actually reread — and never soften
the bar by editing statuses or grades directly in page frontmatter: go
through `flip claim status` and `flip grade`, which enforce and recompute
(hand-set corroboration counts show up as doctor drift findings).
