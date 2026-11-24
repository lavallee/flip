---
name: notebook-audit
description: Pre-publish claim audit — invoke before a draft ships, a render publishes, or a notebook is declared done.
---

# notebook-audit

The gate between reporting and publishing: every load-bearing claim faces the
verification bar, and what doesn't clear it gets flagged, not shipped.

## Preflight

Use `flip cli` for current syntax, `flip show --claims` for the notebook's
claim surface, and `flip doctor` for structural findings. Doctor lists
expected-until-use profile files separately; they become errors only when a
notebook is done, published, or archived.

## Editorial handoff

When the task includes handing a researched draft to an editor, use the optional
[flip-publication](https://github.com/lavallee/flip-publication) bundle for its
workflow, evidence map and handoff templates. Read its README, get a persistent
checkout, then `flip plugin doctor <path>` and `flip plugin link <path>`.
It is definitions only: linking executes no renderer and needs no enable step.
Use `flip workflow show lavallee/publication-evidence/publication-handoff`
before selecting it. Review exported citation metadata before sharing; neither
a successful render nor a completed workflow establishes editorial approval.

## Checklist

1. **Lint first.** `flip doctor` — fix every ERROR (bad enums, orphan
   custody, id/alias breakage, under-verified claims) before auditing
   content. Doctor exits 1 while ERRORs remain.

   **Read the top lines before counting the rest.** Doctor emits cause
   lines for exactly two root problems: a `vocabulary-drift` line when
   sources carry pre-0.8 independence vocabulary (naming which claims it
   explains), and a capture-method group line when many sources share one
   method problem. Every other code just repeats — don't hunt for a cause
   line that isn't there; group those yourself with `--code`. A long wall
   of findings is usually one fix, not a deeply unsound notebook (520 of
   552 findings on one real corpus were a single code). Triage by cause,
   not by count.

   **`--json` returns every finding and scales with the count** — 130KB
   measured on a 507-page notebook. Narrow before you machine-read:
   `flip doctor --code <code>` keeps one finding code, `--limit N` caps
   the list.

   **A corroboration count is not always a verdict on the evidence.** If a
   claim fails the bar, check whether doctor named sources it *could not
   count* — a page carrying pre-0.8 `independence` vocabulary is unjudged
   whatever letter is stored on it, so the count understates the evidence
   rather than measuring it. Establish that first; regrading 100+ sources
   because a number looked wrong is the expensive way to find out.
2. **Pull the claim map.** `flip show --claims` (or
   `flip claim list --json`). Audit every claim marked `load_bearing` first,
   then the rest. At scale, work in batches: pick a handful of claims, pull
   their cited source pages together, clear the batch, move on — never open
   every claim page at once.
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
   not a corroboration count — is the one to clear. Run that test against the
   **pinned passage** (`--against F2§label`): if the claim cites the whole
   document, pin the words it rests on first (`flip source passage pin`), and
   check the pin carries what the claim *says* about it, not only its number.
4. **Walk each load-bearing claim against the bar** (profile default: two
   sources whose recorded independence is `independent`, or one whose
   derived digest is A):
   - sources actually support the claim as worded — reread them, don't trust
     the link
   - every cited source is judged — `flip source list` and grade any `?`
     rows first; an ungraded source corroborates nothing
   - corroborating sources are recorded `independent` — not derivatives of
     the same upstream, not `self-reported` parties agreeing with themselves.
     Two that carry one origin (a wire story captured twice, a report quoting
     another's figure) are one: record it with `flip source origin <id>
     --republishes <id> --because …`, and clear every `possible-shared-origin`
     hint before trusting a count
   - every passage ref the claim cites is intact — `excerpt-drift` or
     `unbacked-excerpt` means the words flip vouched for are not what is on
     disk; a pin on a text derivative is a pin on a derivative
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
   to clear it; it never softens it. When a check was made by applying a
   written rule, name it: `--basis <kind>:<id>@<version>#<digest>
   [--basis-against <ref>]` on `claim verify|test|status`, written by the
   tool as `--actor tool:<name>`. A basis is a label; flip accepts or refuses
   the record exactly as it would without one. The snapshot's `status_set`
   says who set each claim's status — check which were ruled by a person.
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
