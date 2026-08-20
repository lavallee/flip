---
name: notebook-create
description: Start a new flip notebook — invoke when research begins and there is no notebook yet (no index.md with flip frontmatter up the tree), or when a thread graduates to its own notebook.
---

# notebook-create

Recognize the job, pick a profile, scaffold, and seed the tip. A notebook holds
one investigation or recurring research responsibility.

**Preflight:** run `flip --version`. If the CLI is not yet on the agent's PATH,
guide its one-time installation as a standalone tool —
`uv tool install flip-notebook` (or `pipx install flip-notebook`; Python 3.12+)
— following the harness's authority rules for system changes, then verify with
`flip --version`. Do not add it to the repository's project dependencies. One
tool, no services; everything below is plain files on disk.

## Command map (verbs → leaves)

`flip cli` prints the full, always-current map; the leaves you reach for most:

| to do this | run |
|---|---|
| start a notebook | `flip new <slug> --kind <kind>` — kinds are outcomes (`lit-review`, `decision-packet`) or rigor profiles (`scout`, …); `flip kind list` shows all |
| adopt an outcome late | `flip kind adopt <id>` — crystallizes an open notebook; prints the honest gap manifest |
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
| forecasts | `flip forecast add\|update\|resolve\|due\|list` — probabilities live here, never on claims |
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
