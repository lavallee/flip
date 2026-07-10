# AGENTS.md — flip for agents

flip is a CLI and plain-file format for **reporter's notebooks**: research
corpora (sources, claims, logs, sessions) maintained by humans and agents together.

A notebook is one directory — `notebook.toml` + `notebook.md` plus JSONL
ledgers — readable with `less`, diffable with `git`, no service required.
[SPEC.md](SPEC.md) is the format; [docs/internals.md](docs/internals.md) is the
code map; this file is how you, an agent, should use it.

## When to reach for flip

- You are doing research whose sources, reasoning, and claims must survive
  your context window: capture into a notebook, don't summarize into the void.
- You are asked to "start a notebook," "log this," "capture that source,"
  "verify the claims," or to pick up work someone else left in a directory
  containing `notebook.toml`.
- You produced LLM synthesis that later work will lean on. It is a **lead,
  grade C, not evidence** — a notebook is where it gets promoted or killed.

If a directory (or any parent) holds `notebook.toml`, you are inside a
notebook and every `flip` command works from there — flip walks up to find
the root.

## The five-minute tour

Everything below is real output (paths shortened). Read commands take
`--json`.

```console
$ flip new nj-schools --kind scout --title "NJ enrollment dip"
created scout notebook 'nj-schools' at /work/nj-schools
next: cd /work/nj-schools && flip log "started" — see `flip --help` for the toolkit

$ flip log "started scouting the angle"
logged 2026-07-10T17:42:48Z · agent:claude

$ flip add-source ./districts.csv --note "district enrollment table"
F1 · file · sources/raw/F1.csv (grade ?)
judge it: flip grade F1 --grade A|B|C --independence original|republisher|derivative|self-interested

$ flip grade F1 --grade A --independence original --notes "state data, extracted ourselves"
F1 · grade A · original · fresh

$ flip claim add "District enrollment fell 4.2% since 2021" --source F1 --load-bearing
C1 asserted · sources: F1 · corroboration: 1

$ flip claim status C1 verified
C1 → verified · corroboration: 1

$ flip decide --question "Which county first?" --decision "Start with Essex" --why "largest enrollment swing"
D1 · Start with Essex

$ flip pass "2019 funding blog post" --reason "republishes state PR verbatim, no added data"
passed 2026-07-10T17:43:12Z · republishes state PR verbatim, no added data

$ flip question add "Does the fall predate the funding change?"
Q1 open · Does the fall predate the funding change?

$ flip show
nj-schools · scout · active · 2026-07-10

OPEN QUESTIONS
  Q1 · Does the fall predate the funding change?

RECENT LOG
  2026-07-10T17:42:48Z · agent:claude · started scouting the angle

$ flip doctor
ok: no findings
```

(Source ids use `P`/`A`/`F`/`T`/`S` prefixes by kind; `D#` is reserved for
decisions in `log/decisions.jsonl`, so a bare `[F3]` or `[D2]` cite is never
ambiguous.) Note that `flip doctor` tracks the profile's minimums: while a
notebook's status is `active` or `dormant`, missing required ledgers are
WARNs (they appear with use — the first `flip decide` and `flip pass` create
a scout's); once status is `done`, `published`, or `archived`, they become
ERRORs.

When verification isn't earned, flip refuses and says what to do:

```console
$ flip claim status C2 verified
cannot verify C2: 0 independent original source(s) of 1 required and no
grade-A source among its sources (sources: none); add independent original
sources to the claim or upgrade one to grade A via `flip grade`
```

The rest of the surface: `flip source list` (the ledger at a glance —
grade/independence/freshness per source), `flip question list` (every Q# with
open/answered status), `flip session start|end` (working-episode records),
`flip profiles` (available kinds), `flip index` (per-user notebook registry),
`flip export bag|csl` (BagIt / CSL JSON projections),
`flip show --claims|--stale`, and `--json` on every read command.

## Conventions you MUST honor

1. **Append-only ledgers.** `log/*.jsonl`, `sources/_provenance.jsonl`, and
   `derived/_derivations.jsonl` are append-only — never edit or rewrite a
   line, never delete one. Only `sources/ledger.jsonl` and
   `analysis/claims.jsonl` are current-state, and you change those through
   `flip grade` / `flip claim`, not a text editor. IDs (`A1`, `C3`, `D2`,
   `Q4`) are never reused, even after retraction.
2. **LLM output is grade C until promoted.** Anything you synthesized — or
   pulled from a retrieval service — enters as a lead in a session record or
   a grade-`C` source. It becomes evidence only by being promoted through the
   source ledger, and under `citation_rule = "public-terminus"` every
   load-bearing chain must end at a public, independently verifiable source.
3. **Every load-bearing claim needs sources.** Assert claims with
   `flip claim add --source <id>` the moment the work leans on them.
   `verified` is gated by the profile's corroboration bar (default: two
   independent original sources, or one grade-A primary); don't argue with
   the gate — go get corroboration.
4. **Run `flip doctor` before finishing.** It exits 1 on ERROR findings. Fix
   every ERROR; read every WARN and either fix it or note in the log why it
   stands. Never hand off a notebook that fails doctor.
5. **Set `FLIP_ACTOR`.** Every ledger line carries an actor. flip
   auto-detects known agent harnesses, but be explicit:
   `export FLIP_ACTOR="agent:claude"` (or `agent:<your-name>`). Humans are
   `human:<name>`, tools `tool:<name>`.

Also: never hand-edit anything under `sources/raw/` (verbatim bytes,
immutable — recapture instead), and never paste fetched text into the
notebook as if it were a source; capture it with `flip add-source` so hash
and provenance are recorded.

## Recipes

### Start a notebook

```bash
flip profiles                              # pick a kind: ledger|scout|research-review|engagement|data-investigation
flip new <slug> --kind scout --title "..."
cd <slug>
export FLIP_ACTOR="agent:claude"
flip log "started: <one-line mission>"
# fill in notebook.md's section stubs — 'The tip' and 'Hypotheses & falsifiers' first
flip doctor   # expect missing-required WARNs until the profile's ledgers exist through use
```

Profiles require ledgers that appear through use: on a fresh `scout`, doctor
WARNs until the first `flip decide` and `flip pass`; on a fresh
`research-review`, until `add-source`, `claim add`, and `session start` have
each run once and you've created `drafts/` yourself. The WARN lines name
exactly what's missing — and they harden into ERRORs the moment you set the
manifest status to `done`, `published`, or `archived` (SPEC §12: completion
requirements, not creation requirements).

### Capture + grade a source

```bash
flip add-source https://example.com/report --note "why captured"   # runs your configured web fetcher
flip add-source ./filing.pdf                                       # local file: builtin copy + hash
flip add-source doi:10.1234/abcd                                   # paper: configured doi fetcher
# read it, then judge it — grading is a judgment, not a formality:
flip grade A1 --grade B --independence original --freshness fresh --notes "official docs; original publisher"
flip source list           # audit the ledger: any grade "?" line is captured but unjudged
flip source list --json    # same rows for machine consumption
```

URL/DOI capture needs a `[fetchers]` entry in `$FLIP_HOME/config.toml`
(default `~/.flip/config.toml`) — see [docs/quickstart.md](docs/quickstart.md).
If the fetcher isn't configured, flip's error shows the exact stanza to add.
`republisher`/`derivative` sources don't count toward corroboration — prefer
the original — and neither does anything still graded `?`: an ungraded
source is custody, not judgment, and satisfies no verification bar.

### Assert and verify a claim

```bash
flip claim add "<one-sentence assertion>" --source A1 --source F2 --load-bearing
flip claim status C1 verified          # refused until the profile's bar is met
flip claim status C1 needs-2nd         # honest fallback while you hunt corroboration
flip claim list --status needs-2nd --json
```

### Record a session

Before an LLM run or research sweep:

```bash
flip session start landscape-scan --model claude-fable-5 --tools web-search
# prints log/sessions/2026-07-10T1743-landscape-scan.md
# fill in its Goal / Prompt / Key outputs sections as you work
flip session end landscape-scan --summary "3 candidate districts; Essex strongest signal"
```

Promote anything from the session the work will rely on: leads →
`flip add-source` + `flip grade`, follow-ups → `flip question add`, forks
resolved → `flip decide`, dead ends → `flip pass`.

### Hand off

```bash
flip doctor                 # fix ERRORs first
flip show                   # this is what the next reader sees
# write/refresh HANDOFF.md: state of play, open questions (Q#), claims
# needing work (C#), next actions — the cold-start view
flip log "handoff: <where things stand in one line>"
```

## Skills

Procedural checklists for these workflows ship in
[src/flip/skills/](src/flip/skills/) — `notebook-create`, `notebook-source`,
`notebook-log`, `notebook-audit`, `notebook-handoff`, `notebook-lessons` —
as plain `SKILL.md` files usable by any agent runtime, and as a
[spindle](https://github.com/lavallee/spindle) package named `flip`.
