---
name: notebook-source
description: Capture and grade a source with custody discipline — invoke every time the work starts relying on an external artifact (URL, DOI, file, dataset, transcript).
---

# notebook-source

Custody first: local bytes, hash, provenance, then judgment. A source you
didn't capture is a source you don't have.

## Command map (verbs → leaves)

`flip cli` prints the full, always-current map; the leaves you reach for most:

| to do this | run |
|---|---|
| start a notebook | `flip new <slug> --kind <profile>` |
| capture a source | `flip add-source <url\|doi\|file> [--kind --via --note]` |
| recheck the world | `flip source recheck <id>` — re-fetch, hash-compare, receipt; never overwrites custody |
| a capture was refused | climb the ladder (SPEC §5.1): alt representation → archive replay → publisher API → browser render → save-as. A 403 is not a verdict on the source |
| grade a source | `flip grade <id> --independence independent\|corroborated\|self-reported\|derivative --basis … [--n … --base-defined\|--base-undefined]` — the letter is derived |
| ask why a letter | `flip grade <id> --explain` — the derivation, writes nothing |
| fix a bad capture title | `flip source retitle <id> "<title>"` — never hand-edit frontmatter |
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

1. **Capture the moment you rely on it.**
   ```bash
   flip add-source <url|doi:...|path> --note "<why captured / anything odd about the get>"
   ```
   flip infers the kind (web/paper/file, plus social for X/Twitter post URLs);
   pass `--kind` for datasets, talks, or anything ambiguous. Raw bytes land
   in `sources/raw/`, the hash in the provenance ledger, and a source page
   opens at `references/<slug>.md` at
   grade `?` — the id (`A3`, `F1`, …) is in its frontmatter and `flip open
   <id>` finds it again. URL/DOI capture runs the fetcher configured in
   `$FLIP_HOME/config.toml` — if flip errors, adapt the schematic stanza it
   prints; never work around the fetcher by saving text yourself.
   Fetcher implementations are operator configuration, not part of flip's
   public contract. Keep site-specific commands in `$FLIP_HOME/config.toml`
   or a separate private integration repository; portable instructions
   should name source kinds and placeholders, not a deployment's tools.
2. **A refusal is where the work starts, not where it ends.** The single
   most common way an acquisition fails is that the agent stopped at the
   first 403. It is a decision about *this request*, not a verdict on the
   source. Climb the ladder (SPEC §5.1 capture methods), and record which
   rung worked:

   | rung | method | try it when |
   |---|---|---|
   | 1 | `http-get` | always — flip-fetch already retries 429/502/503/504 with backoff |
   | 2 | `http-alt-representation` | a canonical/AMP/print/`?output=embed` variant of the same URL |
   | 3 | `archive-replay` | 403/401/dead — `web.archive.org/web/2024/<url>`, archive.today, Memento |
   | 4 | `publisher-api` | scholarly: Crossref → Unpaywall → OpenAlex → arXiv/PMC (all free, no auth) |
   | 5 | `browser-render` / `browser-session` | JS-only pages, consent walls |
   | 6 | `self-contained-archive` | the page matters visually, or its assets will rot |
   | 7 | `human-in-loop` | save it from your own browser, then `flip add-source <file> --kind file` |

   **On conduct** (SPEC §5.1): the shipped default assumes directed capture
   of a named document, not crawling. A User-Agent is a compatibility hint
   rather than an access control, so flip-fetch presents a browser string,
   fetches one document, follows no links, and paces per host. That is a
   default, not a rule — the operator can set a different policy
   (`--user-agent`, `--min-interval`) and owns the result; don't lecture them
   about it. Authenticated capture of material they legitimately have access
   to is a supported method (`browser-session`), not a transgression.

   What you must not do is misreport it. The capture row records the
   `user_agent` and `strategy` actually used, and a notebook that misdescribed
   how it got its bytes is worthless to whoever later has to trust it. If a
   source is genuinely out of reach — you have no credentials, no archive
   holds it, the ladder is exhausted — that is a `flip pass` with what you
   tried, not a puzzle to solve and not a fact to fudge.

   Two rules keep this honest. **Don't repeat an unchanged request that was
   refused** — a 403 retried identically is noise; change the method, not the
   patience. And **when the ladder really is exhausted, say so**: `flip pass
   "<what>" --reason "<rungs tried, what each returned>"`. A failed capture
   also writes its own ledger row, so "searched, gone" stays distinguishable
   from "did not look" — which is worth more than a silent gap.

3. **Check what actually landed.** A capture that returns 200 with 800 bytes
   is a consent wall or a JS shell, and it produces the same hash, the same
   ledger row, and the same grade `?` as the real document. `flip doctor`
   flags it as `thin-capture`. Never grade a source you have not confirmed
   you actually captured.

4. **Chase the original.** Before grading, check whether this evidence is
   independent or derivative. If it republishes another source, capture that
   original too
   and grade the republisher accordingly — republishers and derivatives do
   not count toward claim corroboration.
5. **Read it, then grade it** (grading is a judgment made after reading, not
   a formality at capture):
   ```bash
   flip grade <id> --independence independent|corroborated|self-reported|derivative \
     --basis official-record|platform-data|measured|survey|panel|single-operator|synthesis|spoken-management-remarks \
     [--n "<sample AS STATED, a string>"] [--base-defined|--base-undefined] [--method …] [--vintage YYYY-MM] \
       --freshness fresh|dated --notes "<why this grade>"
   ```
   `A` authoritative primary (gov / peer-reviewed / data extracted
   ourselves) · `B` official docs, independent journalism · `C` vendor,
   practitioner, self-interested, or any LLM/retrieval synthesis. Flag
   `--freshness dated` when older than the profile's threshold (~18 months).
   A source left at grade `?` counts toward nothing — it cannot corroborate
   a claim until judged. `flip source list` shows every capture's
   grade/independence/freshness at a glance; sweep it for `?` rows before
   any claim audit.

   **Only three fields move the letter** — `--independence`, `--basis` and
   `--base-defined` — plus `--method`, which alone gates B. `--n`,
   `--vintage` and `--freshness` are documentation: real, worth recording,
   but they never change the grade. Don't reverse-engineer this; run
   `flip grade <id> --explain` and it will name the rule that fired and what
   a higher letter would take.

   **On an inherited notebook, check the vocabulary before you trust a
   letter.** `independence` changed *axis* at 0.8 — it used to record custody
   ("we hold the original bytes"), it now records epistemics ("independent of
   its own subject"). A page still carrying the old values is **unjudged**:
   it derives `?` and corroborates nothing, however confident the letter
   stored on it looks. `flip doctor` leads with a `vocabulary-drift` line
   naming how many sources and which claims; `flip migrate` handles what can
   be translated mechanically and parks the rest for you to re-read. A
   corroboration count that dropped to 0 across a whole notebook is this,
   not an evidence problem.
6. **Public-terminus check.** If the manifest's `citation_rule` is
   `public-terminus`, confirm any load-bearing chain this source joins ends
   at a public, independently verifiable source — a grade-C intermediary
   can't be the terminus.
7. **Wire it in.** Link the source to the claims it backs
   (`flip claim add ... --source <id>` or update existing claims), and cite
   it in prose as `[A3]`. Put pull-quotes, misgivings, and capture notes in
   the source page's body — when editing the page, change only what you
   mean to and preserve frontmatter keys you don't own. Log anything notable
   about the capture with `flip log`.

For discovery, use the research and knowledge roles (configured in
`$FLIP_HOME/config.toml`) — they never mint a source by themselves:
- `flip find "<question>"` lists candidate sources; capture one with
  `flip find --capture <n> "<question>"` or `flip add-source <url>`.
- `flip ask "<question>"` returns cited synthesis. It is a **lead, not
  corroboration**: its raw output is saved under `sessions/raw/` and logged, but
  you must separately `flip add-source` and grade the public URLs it cites
  before any claim relies on them.
- `flip recall "<question>"` reads what you already hold locally (captures
  nothing) — check it before acquiring.

(`flip add-source --kind lookup "<question>"` is a deprecated alias for
`flip ask`.)

Do not paste fetched text into the notebook as if it were a source — every
source enters through `flip add-source` so raw bytes, hash, and provenance
are on record; prose citing no source id is opinion. And never `mv` a source
page: `flip rename <id> <new-slug>` is the only sanctioned rename.
