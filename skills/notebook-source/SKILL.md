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
| make a captured PDF readable | `flip extract <id> [--via <lane>] [--method text-layer\|ocr\|…]` — writes `sources/text/<id>.txt` and logs how; raw custody untouched |
| see what tooling you have | `flip config show` — the lanes configured on this machine and the command behind each |
| recheck the world | `flip source recheck <id>` — re-fetch, hash-compare, receipt; never overwrites custody |
| a capture was refused | climb the ladder (SPEC §5.1): alt representation → archive replay → publisher API → browser render → save-as. A 403 is not a verdict on the source |
| the fetcher came back empty-handed | it found nothing — a finding about the document, not a broken config. Climb, ask the tool directly, `--record`, or `flip pass` |
| you can't get it but must cite it | `flip add-source <target> --record --note "<rungs tried, what each returned>"` — a citable page, honestly thin |
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

   | rung | method | try it when | bundled? |
   |---|---|---|---|
   | 1 | `http-get` | always — retries 429/502/503/504 and timeouts with backoff | yes, default |
   | 2 | `archive-replay` | 403/401/dead — a web archive's copy, raw bytes | yes: `--method archive-replay` |
   | 3 | `publisher-api` | a DOI or arXiv id — Crossref → Unpaywall → arXiv | yes: `--method publisher-api` |
   | 4 | `browser-render` / `browser-session` | JS-only pages, consent walls, your own logged-in access | needs a fetcher |
   | 5 | `self-contained-archive` | the page matters visually, or its assets will rot | needs a fetcher |
   | 6 | `human-in-loop` | save it from your own browser, then `flip add-source <file> --kind file` | you |
   | — | `record-only` | the terminus: `flip add-source <target> --record --note "…"` when it is real, wanted, and out of reach | builtin |

   Rungs 1-3 are in the box and need no external tool. Configure them once as
   named lanes (`flip config init` shows the stanzas) and reach them with
   `flip add-source <url> --via archive`. `publisher-api` wants `--email`:
   Unpaywall requires a real address and refuses without one.

   Two notes on what these actually return. `archive-replay` fetches the RAW
   snapshot, so custody holds the document rather than a rendering of it inside
   the archive's viewer, and records `archived_at` — **the evidence is from
   that date, not today**, which is a grading fact. `publisher-api` records
   `status: metadata-only` when no open-access full text was reachable: the
   registry record is worth keeping and is NOT the paper, so doctor calls it a
   thin capture. Don't cite it as though you read the article.

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

   **A fetcher that came back empty-handed found nothing — it is not broken,
   and neither is your config.** A configured command that exits 0 having
   written nothing has reported a finding about the document: gated,
   withdrawn, not served to us. flip says so and names the moves that remain.
   Four are sanctioned, and one is not:

   - **Climb.** The rungs above the one that just ran, and any other lane the
     operator configured — `flip config show` lists them, `--via <name>`
     reaches them. A second `--kind` often has a second coordinate for the
     same document.
   - **Ask the tool for more.** flip wires exactly ONE verb of whatever fills
     a lane. `flip config show` prints the command; that binary's `--help`
     frequently has search, resolution, reference-walking or alternate-source
     verbs flip never calls. Run it yourself, then hand the result back
     through `flip add-source <file> --kind <kind>` so custody, hash and
     provenance still happen.
   - **Record it.** `flip add-source <target> --record --note "<rungs tried,
     what each returned>"` opens a citable page for a document you do NOT
     hold: `record-only` method, `thin` fidelity, grade `?`, and a warning at
     the top of the page. Use it when the source is real, wanted, and out of
     reach — you need to name it in prose and must not imply you read it.
   - **Close it.** `flip pass "<what>" --reason "<rungs tried>"` when the
     ladder is genuinely exhausted and the source is ruled out rather than
     merely unreachable.

   What is **not** sanctioned: improvising your own fetch — a hand-rolled
   HTTP call, a scraped URL pasted into prose, a "captured" publisher page
   that is really a JavaScript shell. It leaves no custody, no hash, and no
   row saying what was tried, which is the exact hole the notebook exists to
   close. If flip's tooling genuinely can't reach something, that is a finding
   to record, not a rule to route around.

3. **Check what actually landed.** A capture that returns 200 with 800 bytes
   is a consent wall or a JS shell, and it produces the same hash, the same
   ledger row, and the same grade `?` as the real document. `flip add-source`
   says `warning: thin capture` the moment it lands, and `flip doctor` keeps
   naming it as `thin-capture` until custody holds the document. Both are
   telling you to open the file in `sources/raw/` *now* — the warning is
   useless once the thin bytes have been cited. Never grade a source you have
   not confirmed you actually captured.

4. **If it's a PDF (or a scan, or audio), derive the text through flip.**
   ```bash
   flip extract <id> --method text-layer|layout-text|ocr|markup-strip|structured|transcript
   ```
   This is the step that used to happen in a shell, outside the notebook, and
   left no record. `flip extract` writes `sources/text/<id>.txt` through the
   `[extractors]` lane for the file's media family (`pdf`, `html`, `docx`,
   `audio` — the input *format* picks the tool, not the source kind) and
   appends one row to `derived/_derivations.jsonl` with the input hash, the
   tool, the verbatim command, the method, and the output hash and word count.
   `sources/raw/` is never touched.

   **Record the method — it is why the command exists.** A quotation recovered
   by OCR is not the same evidence as one lifted from the publisher's own text
   layer: the second is a machine reading a picture of the page, and it can
   drop a minus sign, a footnote marker, or an entire column without saying so.
   Name a lane after a method (`[extractors.pdf].ocr`) and `--via ocr` records
   it for you. flip never guesses a method, so an unnamed one is recorded as
   nothing at all and `flip doctor` asks (`unvocabularied-extraction`).

   **Two kinds of nothing, and neither is your config's fault.** An extractor
   that exits 0 with no words has found no text — an image-only scan, a form
   with no content. flip logs `not-extracted`, writes **no file**, exits 1, and
   prints the other lanes on this machine. Under 25 words/page it *does* write
   the file, logs `fidelity: thin`, and warns loudly — that one leaves a
   plausible-looking `.txt` on disk that reads like a real extraction until you
   open it. Open it. Then re-run through an OCR lane; a text-layer tool will
   never find words in a scan, however many times it is asked.

   flip ships no extractor and picks no default lane (a stdlib-only web fetcher
   can be bundled; a PDF/OCR toolchain cannot). If none is configured, flip
   prints a stanza for `$FLIP_HOME/config.toml` — adapt it, don't route around
   it with a shell loop whose output nothing can trace.

   A derivative may be overwritten; the append-only log is what makes that
   safe, and it is also how flip tells its own last output from your work. A
   `sources/text/*.txt` that hashes to no row was written by a person, so
   `flip extract` refuses it without `--force` and `flip doctor` names it
   `unlogged-derivative`.
5. **Chase the original.** Before grading, check whether this evidence is
   independent or derivative. If it republishes another source, capture that
   original too
   and grade the republisher accordingly — republishers and derivatives do
   not count toward claim corroboration.
6. **Read it, then grade it** (grading is a judgment made after reading, not
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
7. **Public-terminus check.** If the manifest's `citation_rule` is
   `public-terminus`, confirm any load-bearing chain this source joins ends
   at a public, independently verifiable source — a grade-C intermediary
   can't be the terminus.
8. **Wire it in.** Link the source to the claims it backs
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
