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
| grade a source | `flip grade <id> --independence independent\|corroborated\|self-reported\|derivative --basis … [--n … --base-defined\|--base-undefined]` — the letter is derived |
| assert a claim | `flip claim add "<text>" --source <id> [--about <id>] [--load-bearing]` |
| link/unlink sources | `flip claim source add\|rm <C#> <id…>` (`--about <id>` cites what the claim is ABOUT) |
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

1. **Lint first.** `flip doctor` — fix every ERROR (bad enums, orphan
   custody, id/alias breakage, under-verified claims) before auditing
   content. Doctor exits 1 while ERRORs remain.

   **Read the top line before counting the rest.** Doctor leads with any
   *cause* it can identify — a `vocabulary-drift` line naming how many
   sources share one root problem and which claims it explains — and
   collapses codes that repeat past three (`--json` for every finding). A
   long wall of findings is usually one fix, not a deeply unsound notebook.
   Triage by cause, not by count.

   **A corroboration count is not always a verdict on the evidence.** If a
   claim fails the bar, check whether doctor named sources it *could not
   count* — a page carrying pre-0.8 `independence` vocabulary is unjudged
   whatever letter is stored on it, so the count understates the evidence
   rather than measuring it. Establish that first; regrading 100+ sources
   because a number looked wrong is the expensive way to find out.
2. **Pull the claim map.** `flip show --claims` (or
   `flip claim list --json`). Audit every claim marked `load_bearing` first,
   then the rest.
3. **Check which bar the claim is even under.** A claim citing only sources
   marked `--about` — the documents it is *about*, not witnesses to what it
   asserts — cannot be corroborated at all: the only conceivable second source
   is a second reading of the same document. Those claims carry **no
   corroboration count**, print `n/a (subject)`, and owe a *severe attribution
   test* instead (`flip claim test <C#> --probe attribution --error …
   --would-detect … --if-absent … --against <id> --result …`), which is the
   audit any reader can re-run against the same custody. Do not go looking for
   a second source for one of these; there is none to find. Doctor names a
   subject citation whose attribution test was never run, and that finding —
   not a corroboration count — is the one to clear.
4. **Walk each load-bearing claim against the bar** (profile default: two
   sources whose recorded independence is `independent`, or one whose
   derived digest is A):
   - sources actually support the claim as worded — reread them, don't trust
     the link
   - every cited source is judged — `flip source list` and grade any `?`
     rows first; an ungraded source corroborates nothing
   - corroborating sources are recorded `independent` — not derivatives of
     the same upstream, not `self-reported` parties agreeing with themselves
   - the chain ends at a public, independently verifiable source when
     `citation_rule = "public-terminus"` — no synthesis-basis (LLM/vendor)
     terminus
   - freshness: a `dated` source can't carry a present-tense claim
   - nothing load-bearing rests on a **thin capture** — doctor names both
     flavors: a JS shell or consent wall that landed as 200, and a
     `record-only` page whose custody is flip's record of a document it never
     held. Climb the ladder for the real bytes (SPEC §5.1) or reword the
     claim; do not let a record stand in for the thing it records.
5. **Record verifications where they apply.** Beyond corroboration, a claim
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
6. **Move statuses honestly.** `flip claim status C7 verified` only when the
   bar is genuinely met — the corroboration count OR a recorded
   adversarial/recomputation verification (flip refuses otherwise — do not
   game it by regrading sources you haven't reread). Otherwise `needs-2nd`,
   `unconfirmed`, or `retracted`, with a `flip log` line saying why.
7. **Emit the coverage map** into `notebook.md` (or the draft's changelog):
   three lists — **solidly sourced** (verified, bar met), **authorial frame**
   (interpretation presented as such, no claim needed), **flagged for
   further reporting** (asserted/needs-2nd; must be softened or cut before
   publish).
8. **Close the hypothesis loop.** Note in `notebook.md` what survived the
   reporting: which hypotheses stood, which falsifiers fired.
9. **Final pass.** `flip doctor` again — clean exit — and
   `flip log "audit: <n> load-bearing claims, <n> verified, <n> flagged"`.

Do not mark a claim verified without the corroboration bar — independent
independent sources or a derived-A primary, actually reread — or, for a claim
that cites only what it is ABOUT, without the severe attribution test that
stands in for the bar there. Never soften either by editing statuses or grades
directly in page frontmatter: go through `flip claim status` and `flip grade`,
which enforce and recompute (hand-set corroboration counts show up as doctor
drift findings), and never re-role a citation `--about` to make a bar go away
— the role is on the page, and doctor names the audit it now owes.
