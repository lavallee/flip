# AGENTS.md — flip for agents

flip is a CLI and plain-file format for **reporter's notebooks**: research
corpora (sources, claims, decisions, questions, sessions) maintained by
humans and agents together.

A notebook is one directory and a conformant OKF v0.2 knowledge bundle: a
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
judge it after reading: flip grade F1 --independence independent|corroborated|self-reported|derivative --basis … [--n … --base-defined|--base-undefined]

$ flip grade F1 --independence independent --basis official-record --base-defined \
    --freshness fresh --notes "state data, extracted ourselves"
F1 · grade A (derived) · independent · official-record · base_defined: true · fresh

$ flip grade F1 --explain
F1 · grade A (derived) — districts.csv
  because: independence 'independent' + strong basis 'official-record', base not undefined
  to move it: A is the ceiling
  moves the letter:
    independence: independent
    basis: official-record
    base_defined: true
    method: — (alone gates B)
  documentation only (never moves the letter): n=—, vintage=—, freshness=fresh

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
markdown link and citation `resource` path notebook-wide. Never `mv` a page
yourself.
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
cannot verify C2: 0 independent source(s) of 1 required and no grade-A
source among its sources (sources: none); add sources whose independence is
'independent' to the claim or upgrade one to grade A via `flip grade`; or
record a skeptic/recompute pass with `flip claim verify C2 --method
adversarial|recomputation`
```

The refusal names every path out, including the ones that don't need more
sources. It also names anything it *couldn't count* — a cited source still on
pre-0.8 `independence` vocabulary is neither for nor against, and a bare `0`
would read as a verdict on your evidence when it isn't one.

The rest of the surface: `flip source list` (every source at a glance:
`F1 · A/independent/fresh · districts.csv · references/district-enrollment-table.md`
— the letter shown is the *derived* digest, and where the letter stored on the
page disagrees it says so),
`flip question list` / `flip question answer Q1 --note "..."` /
`flip question repose Q1 "<sharper wording>"` (append-only; the journey survives),
`flip question note|close|dormant|reopen` (the rest of the journey — evidence
accretion with scope verdicts, honest ends, parking, un-stop triggers),
`flip commission add|status|list` (bounded follow-up work as a contract),
`flip claim verify C7 --method adversarial|recomputation` (a recorded check
that also clears the `verified` gate), `flip session start|end`
(working-episode pages under `sessions/`), `flip profiles` (available kinds,
incl. `pursuit`), `flip index` (per-user notebook registry),
`flip migrate` (v0.3 → pages, then to the current profile in place),
`flip export bag|csl|okf|json` (BagIt / CSL JSON / policy-filtered public
bundle / the `flip-render/1` JSON projection), `flip ws show` (the merged
workspace roster), `flip show --claims|--stale`, and `--json` on every read
command.

## Command map

`flip cli` prints a compact, always-current map of every command (group path,
one-line purpose, key flags) — generated from the CLI tree, so it never drifts;
`flip cli --json` is the machine form. One read instead of walking `--help` per
group. The leaves you reach for most:

| to do this | run |
|---|---|
| start a notebook | `flip new <slug> --kind <profile>` (kinds: `flip profiles`) |
| capture a source | `flip add-source <url\|doi\|file> [--kind --via --note]` |
| make a captured PDF readable | `flip extract <id> [--via <lane>] [--method text-layer\|ocr\|…]` — `sources/text/<id>.txt` + one derivation row; raw custody untouched |
| see what tooling you have | `flip config show` — the lanes configured on this machine, and the command behind each |
| record what you couldn't get | `flip add-source <target> --record --note "<rungs tried>"` — citable page, no custody of the document |
| grade a source | `flip grade <id> --independence independent\|corroborated\|self-reported\|derivative --basis … [--method … --base-defined\|--base-undefined]` — the letter is derived |
| ask why a letter | `flip grade <id> --explain` — the derivation; writes nothing |
| fix a capture's title | `flip source retitle <id> "<title>"` — never hand-edit frontmatter |
| assert a claim | `flip claim add "<text>" --source <id> [--load-bearing]` |
| cite the source a claim is ABOUT | `flip claim add "<text>" --about <id>` · `flip claim source add <C#> --about <id>` — never counted toward corroboration; owes an attribution test instead |
| link/unlink sources | `flip claim source add\|rm <C#> <id…>` |
| record a verification | `flip claim verify <C#> --method adversarial\|independent-sources\|recomputation` |
| move a claim's status | `flip claim status <C#> <status>` |
| record a test — including one that FAILED | `flip claim test <C#> --probe attribution\|substance\|scope --error "<the specific way of being wrong>" --result survived\|failed\|inconclusive\|untestable [--would-detect … --if-absent … --against <ref>]` — `verify` can only record confirmations; this is where a probe that found the error goes |
| see what the tests add up to | `flip claim exposure <C#>` — derived, never stored: `bent` · `severely-tested` · `misattributed` · `refuted` · `untestable`, with the derivation printed |
| take a position on a claim | `flip claim stance <C#> pursuing\|holding\|abstaining\|rejecting --because "…"` — `pursuing`/`rejecting` are refused without `--falsifier`; `--holder <who> --source <id>` records a belief the notebook does *not* share |
| let a claim go | `flip claim rival <C#> <C#> --because "…"`, then `flip claim supersede <C#> --by <C#> --because "…"` |
| keep the conversation itself | `flip session transcript <session> --file <path> [--participant --model]` — a `T#` source under ordinary custody |
| cite one exchange, not the whole file | `flip transcript excerpt T1 --lines 88-104 --label <slug>` → cite `T1§<slug>` · `flip transcript list\|unpin` |
| questions | `flip question add\|note\|repose\|answer\|close\|dormant\|reopen\|list` — evidence accretes via `note` (`--answers as-worded\|narrower\|adjacent`, `--zero-yield saturated\|bad-reformulation\|corpus-gap\|entity-collision`); answers/closes can arm `--reopen-when` triggers; `dormant --until` parks with a review date |
| absence claims / derivation | `flip claim add --absent-from corpus\|named_surfaces\|world --surface …` (a null's weight is its coverage) · `flip claim derives add\|rm <C#> <C#>` (what a claim rests on; doctor walks the chain) |
| commission contracts | `flip commission add "<deliverable>" --universe … --stop … --does-not-redo … [--for Q#] [--roi-low …]` · `flip commission status <K#> dispatched\|returned\|declined [--consumed …]` · `flip commission list [--status]` |
| decisions / dead ends | `flip decide …` · `flip pass …` |
| log / sessions | `flip log "<text>"` · `flip session start\|end` |
| views | `flip show [--claims\|--stale] [--json]` · `flip ws show [--open\|--claims] [--json]` |
| resolve an id | `flip open <ref>` · `flip resolve <ref> --json` |
| lint | `flip doctor [--json] [--code <code>] [--limit N]` · `flip doctor --fix` · `flip doctor --workspace [--fix]` |
| render / export | `flip export json [--out -] [--include-private]` · `flip export bag\|csl\|okf` |

**Attribution is the `--actor` flag or the `FLIP_ACTOR` env var — there is no
other actor flag.** Precedence: `--actor` > `FLIP_ACTOR` > detected default.
(`--notebook` / `FLIP_NOTEBOOK` pins the notebook root the same way, refusing
if it disagrees with the directory you're in.)

**`flip doctor` prints "expected until use" notes** — profile files that appear
with the work, listed apart from real findings, hardening into ERRORs only at
done/published/archived. They are not problems; don't re-run doctor for
reassurance.

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
   (default: two sources recorded `independent`, or one grade-A primary),
   counting judged sources only. Don't argue with the gate — go get
   corroboration. **Unless the claim is *about* a source**: cite that one with
   `--about <id>`, and the bar is replaced rather than waived, because no
   second witness to what one document says can exist. Such a claim carries no
   corroboration number at all (`n/a (subject)`, never `0`) and earns
   `verified` with a severe, surviving `flip claim test --probe attribution`.
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
9. **What you DO with a claim is not its status.** `status` tracks what is
   known; `flip claim stance` records the position taken, and `flip claim test`
   records what was asked of it. Use them rather than bending the status:
   working from a hypothesis ahead of its evidence is `stance pursuing` (with
   the `--falsifier` that would end it), not a claim quietly left `asserted`;
   a belief you are recording because an audience holds it is
   `--holder <them>`, never the notebook's own. Two gates follow from this and
   will refuse you: `verified` is refused when a severe test found the error
   (`exposure: misattributed` or `refuted`) however many sources agree, and
   `status <C#> superseded` is refused outright — concede with
   `flip claim supersede --by --because`, because letting go is comparative
   and a bare status change records only that you got tired of the claim.
   None of these keys appear in a notebook that doesn't use them.

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
flip find "who acquired X?"                                        # research: candidate leads (--capture <n>)
flip ask "who acquired X?"                                         # research: cited synthesis (a grade-C lead → sessions/raw/)
flip recall "prior work on X"                                      # knowledge: what we already hold locally
# read it, then judge it — grading is a judgment, not a formality:
flip grade A1 --independence independent --basis official-record --method "published filing" \
  --freshness fresh --notes "official docs; the original publisher"
flip grade A1 --explain    # which fields moved the letter, and what a higher one takes
flip source list           # audit: any grade "?" line is captured but unjudged
flip source list --json    # same rows for machine consumption
```

Each capture opens a `references/<slug>.md` page — custody and judgment in
frontmatter, your capture notes in the body. URL/DOI capture needs a
`[fetchers]` entry in `$FLIP_HOME/config.toml` (default `~/.flip/config.toml`)
— see [docs/quickstart.md](docs/quickstart.md). If the fetcher isn't
configured, flip's error prints a schematic stanza to adapt; `flip config show`
lists the lanes that *are* configured, and the command behind each.

**When a capture comes back empty-handed, the tool is reporting, not
malfunctioning** (SPEC §5.1). A fetcher that exits 0 having written nothing has
found the document gated or absent — that is a finding, and flip names the four
moves that follow: climb the ladder (`--via <lane>`, another `--kind`); ask the
tool directly, because flip wires exactly one verb of it and its own `--help`
often has more; `flip add-source <target> --record --note "<rungs tried>"` to
keep a citable page for a document you do not hold (`thin` fidelity, grade `?`);
or `flip pass` when the search is genuinely exhausted. Improvising a fetch
outside flip is the one wrong answer — no custody, no hash, no record of what
was tried. A capture that *does* land but reads `warning: thin capture` is the
same problem wearing a success: open the file in `sources/raw/` before citing
it.
`self-reported`/`derivative` sources don't count toward corroboration — prefer
an independent one — and neither does anything still graded `?`. On a notebook
carried across the 0.8 judgment change, watch for a third case: `independence`
used to record **custody** and now records **epistemics**, so a page still
holding the old values (`original`, `republisher`, `self-interested`) is
*unjudged* however confident the stored letter looks. `flip doctor` leads with
a `vocabulary-drift` line naming the count and the claims it explains; `flip
migrate` translates what it can and parks the rest for you to re-read.
Integrations are configured under four roles in `$FLIP_HOME/config.toml`:
`[fetchers]` (capture, run by `add-source`), `[extractors]` (text derivatives,
run by `flip extract`, keyed by media family), `[research]` (`find`/`ask`), and
`[knowledge]` (`recall`). `flip config init` writes a starter config whose
`web` lane uses the bundled `flip-fetch` helper, so URL capture works with no
external tool; local files always copy with no config. Nothing fills
`[extractors]` by default — a stdlib-only web GET can ship inside flip and a
PDF/OCR toolchain cannot — so that stanza is written commented, for you to
choose. They are operator configuration, not flip's public
contract — public docs and packaged skills refer only to kinds/verbs and the
`{url}`/`{id}`/`{query}`/`{dest}`/`{src}`/`{out}` placeholders, never to a
deployment's tools.
`flip find`/`ask` output is a **lead, grade C, not evidence**: `ask` saves its
raw synthesis under `sessions/raw/` and logs it, but you must capture and grade
its cited public URLs separately before a load-bearing claim relies on it.
`flip recall` reads local holdings and captures nothing. (`--kind lookup` is a
deprecated alias for `flip ask`.)

### Assert and verify a claim

```bash
flip claim add "<one-sentence assertion>" --source A1 --source F2 --load-bearing
flip claim status C1 verified          # refused until the profile's bar is met
flip claim status C1 needs-2nd         # honest fallback while you hunt corroboration
flip claim list --status needs-2nd --json
```

The claim page (`claims/<slug>.md`) carries OKF v0.2 `sources` entries
(`{id, role?, resource, title}`) and generated footnote attribution — id-shaped
markers ending the lead paragraph plus `[^F1]: …` definition lines linking
the reference pages. flip recomputes `independent_corroboration` on status
changes and doctor flags drift; where a cited source can't be counted at all,
every surface that shows the number names it too. A claim citing only
`role: subject` sources has **no** `independent_corroboration` key: absent
means the axis does not apply, never that the count came out zero.

### Pursue a question

The question page is where a pursuit accumulates — not your context window.

```console
$ flip question add "did the vendor's number replicate?" --resolves-via "the two independent audits"
Q2 open · did the vendor's number replicate? · watches: the two independent audits

$ flip question note Q2 "audit A replicates the direction, not the size" --answers narrower --source F3
Q2 evidence noted (open) · answers: narrower
```

Evidence lands as a dated section; the question stays open — a narrower
answer is recorded without being promoted to *the* answer. Empty probes
need their cause (`--zero-yield saturated|bad-reformulation|corpus-gap|
entity-collision`): a zero round without one is indistinguishable from
saturation and must not count toward stopping. When the ask itself
sharpens, re-pose (`flip question repose Q2 "..." --sharpened scope`) —
the old formulation is preserved. End it honestly:

```console
$ flip question answer Q2 --note "direction yes, size no — see C4" --reopen-when "vendor restates the figure"
Q2 answered · reopens when: vendor restates the figure
```

`answered` is one end among several — `close --reason split|yielded|
counter-example|dead-end|superseded` records the others; `dormant --until
YYYY-MM-DD` parks with a review date `flip show` resurfaces. Armed
`--reopen-when` triggers list under REOPEN TRIGGERS ARMED, and
`flip question reopen Q2 --because "..."` restores open with the whole
journey still on the page. Follow-up work worth dispatching gets a
commission — a contract with an input universe, stop condition, and
does-not-redo boundary (`flip commission add … --for Q2`) — so a
continuation run consumes prior output instead of re-searching it.

### Hold a position, and say what was asked of it

```bash
flip claim stance C1 pursuing --because "explains the 2021 discontinuity nothing else does" \
  --falsifier "the discontinuity survives in districts that never changed reporting"
flip claim test C1 --probe attribution --error "the cited table does not contain this figure" \
  --would-detect "the number is absent from the extracted text" \
  --if-absent "the figure appears in row 14 as stated" \
  --against F2 --result survived
flip claim exposure C1                 # what the record adds up to, and why
flip claim stance C1 holding --because "..." --holder "district administrators" --source A7
```

A test is **severe** only when four fields are on the record — the error, how
it would have shown up, what you'd have seen instead had it been absent, and
what did the testing. Anything less reads `bent`, which is one verdict and not
a rung on a ladder: a probe that fires whether or not the error is there
discriminates nothing. Don't reach for `--result untestable` to escape it;
that says the claim as posed admits no test, which is a finding about the
claim. Nothing here makes a claim true — flip checks the four fields are
*present*, never that they are honest.

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

When the conversation itself is where the position got built, keep it:

```bash
flip session transcript landscape-scan --file ./conversation.md \
  --participant human:marc --model claude-fable-5
# T1 · sources/raw/T1.md · references/…  (method: human-in-loop)
flip transcript excerpt T1 --lines 88-104 --label relevance-null
# cite it as T1§relevance-null
flip claim add "<assertion>" --about T1§relevance-null
```

The quote is read out of the immutable capture and hashed, never taken from
you. Passages of one conversation are several citations and **one** source, so
only the source reaches corroboration — and a claim about what was *said* in
the conversation is `--about` it, since no second witness to one exchange can
exist.

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
`notebook-log`, `notebook-audit`, `notebook-handoff`, `notebook-lessons`,
`notebook-kind-author` —
as plain `SKILL.md` files usable by any agent runtime, and as a
[spindle](https://github.com/lavallee/spindle) package named `flip`. Claude
Code and Codex users get the same skills as a plugin:
`/plugin install flip@lyra-forge` or
`codex plugin add flip@lyra-forge` ([plugin guide](docs/claude-code.md)). Claude
Code also invokes the custody hook around `WebFetch`; Codex hosted web tools do
not expose that hook event.
