---
name: notebook-create
description: Start a new flip notebook — invoke when research begins and there is no notebook yet (no index.md with flip frontmatter up the tree), or when a thread graduates to its own notebook.
---

# notebook-create

Recognize the job, pick a profile, scaffold, and seed the tip. A notebook holds
one investigation or recurring research responsibility.

## Preflight

Run `flip --version`. If the CLI is missing, install it as a standalone tool:
`uv tool install --python 3.12 flip-notebook` or `pipx install
flip-notebook`. If the shell still cannot find it, run `uv tool update-shell`
or `pipx ensurepath`, open a new shell, and verify again. Do not add flip to
the research project's dependencies.

Use `flip kind list` to choose a notebook kind and `flip cli` for current
syntax. Set `FLIP_ACTOR` before `flip new`; pursuit notebooks make attributed
seed writes during creation. `--actor` overrides the environment for one
command, while `--notebook` / `FLIP_NOTEBOOK` pins the notebook root.

## Checklist

1. **Recognize the job.** People start one of two ways; both are first-class:
   - **Outcome mode**: they name what they're making ("a lit review", "a
     decision memo", "due diligence on a vendor"). Translate their words,
     never make them learn vocabulary: `flip kind list --json` gives every
     kind's summary AND its `aka` phrases (what people actually say), and
     `--kind` accepts those phrases directly — `flip new x --kind
     "systematic review"` lands on lit-review with the canonical id in the
     manifest. When their statement isn't a listed phrase, YOU are the
     semantic layer: read the summaries, pick the kind whose *output*
     matches what they described, and explain the choice briefly. No match at
     all → open mode, or offer to capture their process as its own kind
     (notebook-kind-author).
   - **Open mode**: they start open-ended. The job in open mode is durable
     capture: custody, judgments at read time, negative evidence with reasons,
     and questions with watching surfaces. That's what keeps a late
     `flip kind adopt` cheap.
   Use the assignment itself to record the tip and intended use. Clarify only
   what is genuinely missing to begin useful work.
2. **Pick the kind.** Outcome named → that kind. Otherwise choose the rigor
   profile that matches the work: `ledger` (source spine only), `scout`
   (screen an angle), `research-review` (headed for publication),
   `engagement` (client-confidential), `data-investigation` (dataset-first),
   `pursuit` (one question under pursuit). An open notebook can adopt a more
   specific outcome later without migrating its record.
3. **Scaffold.**
   ```bash
   export FLIP_ACTOR="agent:<name>"   # or human:<name>; set BEFORE flip new
   flip new <slug> --kind <profile> --title "<human title>"
   cd <slug>
   ```
   Most kinds create `index.md` (the manifest lives in its frontmatter — the
   notebook is an OKF bundle and this is its root) and `notebook.md`; `pursuit`
   also seeds Q1 and `drafts/question-plan.md` before retrieval. Setting the
   actor first matters because those pursuit seeds are attributed writes.
   Check the policy keys in the `index.md` frontmatter
   (`visibility`, `citation_rule`, …) — set `--visibility` at creation if
   the profile's default is wrong for this work.
4. **Seed the tip.** In `notebook.md`, replace the "The tip" stub with the
   real question, assignment, or recurring responsibility. Record hypotheses
   and named falsifiers (H1, H2…) when the work has them; do not invent a
   hypothesis for descriptive or exploratory research. Delete section stubs
   this project genuinely won't need. (Keep the frontmatter block; edit prose
   freely — the body is yours.)
5. **First log line.** `flip log "started: <one-line mission>"`.
6. **Lint.** `flip doctor`. Heavier profiles require files that appear
   through use (`add-source`, `claim add`, `session start`) plus `drafts/`
   which you create by hand — those show as WARNs while the notebook is
   `active`/`dormant` and harden into ERRORs once it's marked
   done/published/archived. Fix every ERROR before doing research.

Create the notebook once its question, assignment, or recurring responsibility
is clear enough to name. The record sharpens with the work.
