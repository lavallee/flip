---
name: notebook-create
description: Start a new flip notebook — invoke when research begins and there is no notebook yet (no index.md with flip frontmatter up the tree), or when a thread graduates to its own notebook.
---

# notebook-create

Interview, pick a profile, scaffold, seed the tip. A notebook exists to hold
one piece of research; don't create it until you can say what that piece is.

## Checklist

1. **Interview.** Establish, in one line each: where the question came from
   (the tip), what the reader will do with the answer, and how heavy the work
   is (quick screen vs. publishable survey vs. dataset dig vs. client work).
2. **Pick the profile.** Run `flip profiles` and choose the lightest kind
   that fits: `ledger` (source spine only), `scout` (screen fast, kill or
   graduate), `research-review` (headed for publication), `engagement`
   (client-confidential), `data-investigation` (dataset-first). When unsure,
   start `scout` — graduating later beats hauling empty ceremony.
3. **Scaffold.**
   ```bash
   flip new <slug> --kind <profile> --title "<human title>"
   cd <slug>
   export FLIP_ACTOR="agent:<name>"   # or human:<name>
   ```
   This creates exactly two files: `index.md` (the manifest lives in its
   frontmatter — the notebook is an OKF bundle and this is its root) and
   `notebook.md`. Check the policy keys in the `index.md` frontmatter
   (`visibility`, `citation_rule`, …) — set `--visibility` at creation if
   the profile's default is wrong for this work.
4. **Seed the tip.** In `notebook.md`, replace the "The tip" stub with the
   real tip, and write hypotheses **before looking**, each with a named
   falsifier (H1, H2…). Delete section stubs this project genuinely won't
   need — empty structure is worse than absent structure. (Keep the
   frontmatter block; edit prose freely — the body is yours.)
5. **First log line.** `flip log "started: <one-line mission>"`.
6. **Lint.** `flip doctor`. Heavier profiles require files that appear
   through use (`add-source`, `claim add`, `session start`) plus `drafts/`
   which you create by hand — those show as WARNs while the notebook is
   `active`/`dormant` and harden into ERRORs once it's marked
   done/published/archived. Fix every ERROR before doing research.

Do not create a notebook without a stated tip and at least one falsifiable
hypothesis — a notebook with no question is a folder, not a notebook.
