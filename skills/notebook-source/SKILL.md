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
| grade a source | `flip grade <id> --independence independent\|corroborated\|self-reported\|derivative --basis … [--n … --base-defined\|--base-undefined]` — the letter is derived |
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
2. **Chase the original.** Before grading, check whether this evidence is
   independent or derivative. If it republishes another source, capture that
   original too
   and grade the republisher accordingly — republishers and derivatives do
   not count toward claim corroboration.
3. **Read it, then grade it** (grading is a judgment made after reading, not
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
4. **Public-terminus check.** If the manifest's `citation_rule` is
   `public-terminus`, confirm any load-bearing chain this source joins ends
   at a public, independently verifiable source — a grade-C intermediary
   can't be the terminus.
5. **Wire it in.** Link the source to the claims it backs
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
