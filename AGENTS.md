# AGENTS.md — flip for agents

flip is a CLI and plain-file format for **reporter's notebooks**: research
corpora (sources, claims, decisions, questions, sessions) maintained by
humans and agents together.

A notebook is one directory and a conformant OKF v0.1 knowledge bundle: a
root `index.md` whose frontmatter is the manifest, `notebook.md` as prose
working memory, and **one markdown page per entity** with YAML frontmatter —
`references/`, `claims/`, `decisions/`, `questions/`, `sessions/`. Event
history is append-only JSONL under `log/` and `sources/`. Readable with
`less`, diffable with `git`, no service required. [SPEC.md](SPEC.md) is the
format; [docs/internals.md](docs/internals.md) is the code map; this file is
how you, an agent, should use it.

## When to reach for flip

- You are doing research whose sources, reasoning, and claims must survive
  your context window: capture into a notebook, don't summarize into the void.
- You are asked to "start a notebook," "log this," "capture that source,"
  "verify the claims," or to pick up work someone else left in a directory
  whose `index.md` frontmatter declares a `flip:` version.
- You produced LLM synthesis that later work will lean on. It is a **lead,
  grade C, not evidence** — a notebook is where it gets promoted or killed.

If a directory (or any parent) holds an `index.md` with `flip:` in its
frontmatter, you are inside a notebook and every `flip` command works from
there — flip walks up to find the root. (A directory with `notebook.toml` is
a pre-0.4 notebook: run `flip migrate` first.)

## The five-minute tour

Everything below is real output (paths shortened). Read commands take
`--json`.

```console
$ flip new nj-schools --kind scout --title "NJ enrollment dip"
created scout notebook 'nj-schools' at /work/nj-schools
next: cd /work/nj-schools && flip log "started" — see `flip --help` for the toolkit

$ flip log "started scouting the angle"
logged 2026-07-10T19:59:41Z · agent:claude

$ flip add-source ./districts.csv --note "district enrollment table"
F1 · sources/raw/F1.csv · references/districts.md (grade ?)
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
passed 2026-07-10T19:59:41Z · republishes state PR verbatim, no added data

$ flip question add "Does the fall predate the funding change?"
Q1 open · Does the fall predate the funding change?

$ flip show
nj-schools · scout · active · 2026-07-10

OPEN QUESTIONS
  Q1 · Does the fall predate the funding change?

RECENT LOG
  2026-07-10T19:59:41Z · agent:claude · started scouting the angle

$ flip doctor
ok: no findings
```

Every entity is a page whose **filename is a human slug and whose id is
immutable frontmatter**: the capture above created
`references/districts.md` with `id: F1` and `aliases: [F1]`. Cite ids in
prose as `[F1]`, `[C1]` — greppable both directions — and resolve them with
`flip open`:

```console
$ flip open F1
/work/nj-schools/references/districts.md

$ flip rename F1 district-enrollment-table
F1: references/districts.md → references/district-enrollment-table.md
rewrote links in 2 file(s)
```

`flip rename` is the **only sanctioned rename**: it moves the page (id and
aliases untouched, so `[F1]` cites keep resolving) and rewrites every
markdown link and `supports` path notebook-wide. Never `mv` a page yourself.
An unknown id fails helpfully:

```console
$ flip open Z9
no page with id 'Z9' (known ids: C1, D1, F1, Q1)
```

(Source ids use `P`/`A`/`F`/`T`/`S` prefixes by kind; `C#` claims, `D#`
decisions, `Q#` questions — prefixes are disjoint, so a bare `[F1]` or `[D2]`
cite is never ambiguous.) `flip doctor` tracks the profile's minimums: while
a notebook's status is `active` or `dormant`, missing required files are
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

The rest of the surface: `flip source list` (every source at a glance:
`F1 · A/original/fresh · districts.csv · references/district-enrollment-table.md`),
`flip question list` / `flip question answer Q1 --note "..."`,
`flip session start|end` (working-episode pages under `sessions/`),
`flip profiles` (available kinds), `flip index` (per-user notebook registry),
`flip migrate` (v0.3 → v0.4 in place),
`flip export bag|csl|okf` (BagIt / CSL JSON / policy-filtered public bundle),
`flip show --claims|--stale`, and `--json` on every read command.

## The contract — lineage rules you MUST honor (SPEC §6)

1. **Capture before cite.** A page may only cite what the notebook has
   custody of: a `references/` page backed by raw bytes under `sources/raw/`
   and a provenance event. Never paste fetched text into the notebook as if
   it were a source — `flip add-source` records bytes, hash, and provenance.
   Dangling citations are legal but counted; `flip doctor` reports them.
2. **Judgment is explicit and separate from capture.** Every capture opens at
   grade `?`, which counts toward **nothing** — read the source, then
   `flip grade` it. Capture is custody, not judgment.
3. **LLM output is grade C until promoted.** Anything you synthesized — or
   pulled from a retrieval service — enters as a lead in a session page or a
   grade-`C` source. Under `citation_rule: public-terminus` every
   load-bearing chain must end at a public, independently verifiable source.
4. **Claims carry status, and verification is gated.** Assert claims with
   `flip claim add --source <id>` the moment the work leans on them.
   `verified` is refused until the profile's corroboration bar is met
   (default: two independent original sources, or one grade-A primary),
   counting judged sources only. Don't argue with the gate — go get
   corroboration.
5. **Generation is logged.** Wrap every LLM run or research sweep in
   `flip session start` / `flip session end` — the reasoning chain is
   evidence too.
6. **Events append, views regenerate.** `log/*.jsonl`,
   `sources/_provenance.jsonl`, and `derived/_derivations.jsonl` are
   append-only: never edit, rewrite, or delete a line. `index.md` bodies and
   `log.md` are **generated** — flip overwrites them on every mutating
   command, so hand-edits there don't survive; edit pages and ledgers, not
   listings.
7. **The round-trip rule: preserve keys you don't own.** Entity pages are
   edited by humans, editors, and other tools. When you edit one — by hand or
   programmatically — change only the keys and prose you mean to change;
   frontmatter keys you don't understand MUST survive, and so must the body.
   flip's own commands obey this; so must you.
8. **Attribution everywhere.** Every event and page records its `actor`. flip
   auto-detects known agent harnesses, but be explicit:
   `export FLIP_ACTOR="agent:claude"` (or `agent:<your-name>`). Humans are
   `human:<name>`, tools `tool:<name>`.

Also: ids are never reused, even after retraction; never hand-edit anything
under `sources/raw/` (verbatim bytes, immutable — recapture instead); and
run `flip doctor` before finishing — fix every ERROR (doctor exits 1), read
every WARN and either fix it or note in the log why it stands.

## Recipes

### Start a notebook

```bash
flip profiles                              # pick a kind: ledger|scout|research-review|engagement|data-investigation
flip new <slug> --kind scout --title "..."
cd <slug>
export FLIP_ACTOR="agent:claude"
flip log "started: <one-line mission>"
# fill in notebook.md's section stubs — 'The tip' and 'Hypotheses & falsifiers' first
flip doctor   # expect missing-required WARNs until the profile's files exist through use
```

Profiles require files that appear through use: on a fresh `scout`, doctor
WARNs (`missing-required decisions`, `missing-required log/passed.jsonl`)
until the first `flip decide` and `flip pass`; on a fresh `research-review`,
until `add-source`, `claim add`, and `session start` have each run once and
you've created `drafts/` yourself. The WARN lines name exactly what's
missing — and they harden into ERRORs the moment the manifest status becomes
`done`, `published`, or `archived` (SPEC §13: completion requirements, not
creation requirements).

### Capture + grade a source

```bash
flip add-source https://example.com/report --note "why captured"   # runs your configured web fetcher
flip add-source ./filing.pdf                                       # local file: builtin copy + hash
flip add-source doi:10.1234/abcd                                   # paper: configured doi fetcher
flip add-source --kind lookup "who acquired X?"                    # cited synthesis; grade C, then capture its citations
# read it, then judge it — grading is a judgment, not a formality:
flip grade A1 --grade B --independence original --freshness fresh --notes "official docs; original publisher"
flip source list           # audit: any grade "?" line is captured but unjudged
flip source list --json    # same rows for machine consumption
```

Each capture opens a `references/<slug>.md` page — custody and judgment in
frontmatter, your capture notes in the body. URL/DOI capture needs a
`[fetchers]` entry in `$FLIP_HOME/config.toml` (default `~/.flip/config.toml`)
— see [docs/quickstart.md](docs/quickstart.md). If the fetcher isn't
configured, flip's error shows the exact stanza to add.
`republisher`/`derivative` sources don't count toward corroboration — prefer
the original — and neither does anything still graded `?`.
On a fleet-configured workstation, ordinary URLs route through Downunder,
X/Twitter post URLs through Jackdaw, DOI/arXiv identifiers through Paperboy,
and explicit `lookup` captures through Trawler. Trawler output is a lead, not
an evidence terminus: grade it C and capture its cited public URLs separately.

### Assert and verify a claim

```bash
flip claim add "<one-sentence assertion>" --source A1 --source F2 --load-bearing
flip claim status C1 verified          # refused until the profile's bar is met
flip claim status C1 needs-2nd         # honest fallback while you hunt corroboration
flip claim list --status needs-2nd --json
```

The claim page (`claims/<slug>.md`) carries `sources: [ids]` and a generated
`# Citations` block linking the reference pages; flip recomputes
`independent_corroboration` on status changes and doctor flags drift.

### Record a session

Before an LLM run or research sweep:

```bash
flip session start landscape-scan --model claude-fable-5 --tools web-search
# prints sessions/2026-07-10T2000-landscape-scan.md
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

### Pick up a pre-0.4 notebook

```bash
flip migrate      # from anywhere inside it; finds the notebook.toml root
# migrated /work/legacy to v0.4 · 1 sources, 1 claims, 1 decisions, 1 questions, 1 sessions
flip doctor       # audit the result; migration preserves ids and history
```

## Skills

Procedural checklists for these workflows ship in
[src/flip/skills/](src/flip/skills/) — `notebook-create`, `notebook-source`,
`notebook-log`, `notebook-audit`, `notebook-handoff`, `notebook-lessons` —
as plain `SKILL.md` files usable by any agent runtime, and as a
[spindle](https://github.com/lavallee/spindle) package named `flip`.
