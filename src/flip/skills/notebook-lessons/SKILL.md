---
name: notebook-lessons
description: End-of-life distillation to lessons.md — invoke when a notebook is done, published, killed, or archived, so its method survives it.
---

# notebook-lessons

A notebook's last act is teaching the next one. lessons.md is prescriptive
advice for future notebooks — method, not findings (findings live in the
analysis; this is about how the work went).

## Checklist

1. **Confirm end-of-life.** The notebook's `status` in `notebook.toml` is
   moving to `done`, `published`, or `archived`. Run the audit first if it's
   publishing (see notebook-audit); run `flip doctor` regardless.
2. **Mine the trail**, not your memory:
   - `flip show --claims` — which claims died, which needed the most work,
     what corroboration was hardest to get
   - `log/decisions.jsonl` — which decisions paid off, which you'd reverse
   - `log/passed.jsonl` — rejections that turned out right or wrong
   - `log/log.jsonl` and `log/sessions/` — walls hit, pivots, which tools
     and fetchers earned their keep
   - `notebook.md` hypotheses — what survived the reporting and why
3. **Write `lessons.md`** at the notebook root. Each lesson is prescriptive
   and portable: *"do X / avoid Y, because Z happened here"* — with ledger
   ids as evidence (`[D4]`, `[C7]`, `[P2]`). Cover at least: source
   landscape (which wells were rich/dry), method (what sequence worked),
   tooling (fetcher/processing gotchas), and scope (what this kind of
   notebook should include next time).
4. **Feed the compound loop.** If a beat or a standing skill system exists
   above this notebook, propose the top 1–3 lessons upward — cross-notebook
   references use `<slug>#<id>`.
5. **Close out.** Set the final `status` in `notebook.toml`,
   `flip log "lessons distilled; notebook <done|published|archived>"`, and
   consider `flip export bag <dest>` for cold archival. Re-run `flip index`
   so the registry reflects the final state.

Do not write lessons as a narrative of what happened or a restatement of
findings — a lesson that doesn't tell the next notebook what to do
differently (and point at the evidence here) is a diary entry, not a lesson.
