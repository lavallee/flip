---
name: notebook-create
description: Start a new flip notebook — invoke when research begins and there is no notebook yet (no index.md with flip frontmatter up the tree), or when a thread graduates to its own notebook.
---

# notebook-create

Interview, pick a profile, scaffold, seed the tip. A notebook exists to hold
one piece of research; don't create it until you can say what that piece is.

**Preflight:** if `flip --version` fails, install the CLI first —
`uv tool install flip-notebook` (or `pipx install flip-notebook`; Python
3.12+). One tool, no services; everything below is plain files on disk.

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

1. **Interview.** Establish, in one line each: where the question came from
   (the tip), what the reader will do with the answer, and how heavy the work
   is (quick screen vs. publishable survey vs. dataset dig vs. client work).
2. **Pick the profile.** Run `flip profiles` and choose the lightest kind
   that fits: `ledger` (source spine only), `scout` (screen fast, kill or
   graduate), `research-review` (headed for publication), `engagement`
   (client-confidential), `data-investigation` (dataset-first), `pursuit`
   (one question under pursuit — scaffolds `drafts/question-plan.md` and the
   primary question as Q1, for a banded answer backed by verified claims).
   When unsure, start `scout` — graduating later beats hauling empty ceremony.
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
