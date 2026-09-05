---
name: notebook-lessons
description: Preserve useful method lessons during work and at notebook closure; turn recurring problems or proven fixes into reusable guidance and extensions.
---

# notebook-lessons

Teach the next notebook while the useful change is still clear. lessons.md is prescriptive
advice for future notebooks — method, not findings (findings live in the
analysis; this is about how the work went).

Use `flip cli` for current syntax and set `FLIP_ACTOR` before writing. At
end-of-life statuses, expected-until-use profile files become real doctor
errors; resolve them before distilling lessons.

## During active work

After a recurring problem or useful fix, append a short evidenced lesson to
`lessons.md` now: when it applies, what to do, what was checked, and its limits.
Keep existing lessons and notebook status intact. Read notebook-extend when
another user or notebook could reuse the method; improve an existing plugin
or prepare the smallest useful extension. A single successful run is a
candidate, not proof of a repeatable gain. This does not require closing the
notebook or doing an end-of-life audit. Continue the user's current work.

## At notebook closure

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
