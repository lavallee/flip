# Quickstart

flip keeps research honest: every source you rely on is captured locally and
hashed, every judgment about source quality is recorded, every load-bearing
claim is linked to sources and gated before it can be called verified, and
the whole trail is plain files in git. The notebook is a conformant OKF v0.2
knowledge bundle — any markdown tool can browse and edit it.

## Install

From PyPI (the package is `flip-notebook`; the command is `flip`):

```bash
uv tool install flip-notebook
# or
pipx install flip-notebook
```

From source:

```bash
git clone https://github.com/lavallee/flip
cd flip
uv sync
uv run flip --help
```

Requires Python 3.12+. The core is stdlib + click + PyYAML: no network
calls, no LLM calls, no services.

## Create a notebook

```bash
flip new nj-schools --kind scout --title "NJ enrollment dip"
cd nj-schools
```

You get exactly two files — `index.md` (the manifest lives in its
frontmatter; the notebook is an OKF knowledge bundle and this is its root)
and `notebook.md` (prose working memory, scaffolded with section stubs like
"The tip" and "Hypotheses & falsifiers"). Everything else appears lazily as
commands need it. Every `flip` command works from anywhere inside the
notebook.

If you're an agent (or supervising one), set the actor once:

```bash
export FLIP_ACTOR="human:marc"     # or agent:claude, tool:ingest-script
```

## The core loop

**Capture** the moment you rely on something external:

```bash
flip add-source ./districts.csv --note "district enrollment table"
# F1 · sources/raw/F1.csv · references/districts.md (grade ?)
```

The bytes land verbatim in `sources/raw/`, get hashed into the append-only
provenance log, and open a source page in `references/` at grade `?` —
custody and judgment in the frontmatter, your notes in the body.

**Grade** after you've actually read it:

```bash
flip grade F1 --independence independent --basis official-record --base-defined \
  --notes "state data, extracted ourselves"
# F1 · grade A (derived) — the letter is a digest of the evidence description
# F1 · grade A (derived) · independent · official-record · base_defined: true
```

`A` authoritative primary · `B` official/independent · `C` vendor,
practitioner, or LLM synthesis. `independence` records whether this is the
independent or downstream of another source — derivatives never count as
corroboration,
and neither does a source still graded `?` (capture is custody, not
judgment). `flip source list` shows every source at a glance; any `?`
line still needs judging.

Only `--independence`, `--basis` and `--base-defined` move the letter, plus
`--method`, which alone gates B; `--n`, `--vintage` and `--freshness` are
documentation. You don't have to remember that — ask:

```bash
flip grade F1 --explain          # writes nothing
# F1 · grade A (derived) — NJDOE enrollment file
#   because: independence 'independent' + strong basis 'official-record', base not undefined
#   to move it: A is the ceiling
```

If a capture lands with a useless title (a fetcher handing back a binary
payload's first bytes, say), fix it with `flip source retitle F1 "<title>"`
rather than opening the page — flip quotes the YAML, so a title containing a
colon can't break every reader of the notebook at once.

**Claim** when the work starts leaning on an assertion:

```bash
flip claim add "District enrollment fell 4.2% since 2021" --source F1 --load-bearing
# C1 asserted · sources: F1 · corroboration: 1
```

**Verify** — flip enforces the profile's corroboration bar (default: two
sources recorded `independent`, or one whose derived digest is A):

```bash
flip claim status C1 verified
# C1 → verified · corroboration: 1
```

If the bar isn't met, flip refuses with instructions instead of complying.

**Show** the hot view — the resume-here screen, computed from the pages and
ledgers:

```bash
flip show            # open questions, claims needing work, recent log, latest session
flip show --claims   # all claims grouped by status
flip show --stale    # what went cold
```

Along the way, keep the trail: `flip log "hit a wall on X"` for the work log,
`flip decide` for resolved forks (the *why* is the payload), `flip pass` for
things considered and rejected, `flip question add`/`answer`/`list` for open
threads, and `flip session start`/`end` around each LLM run or research
sweep.

**Doctor** before you hand off or publish:

```bash
flip doctor
# WARN missing-required decisions — profile 'scout' requires decisions
#   (it appears with use; required before done/published/archived); create it
# WARN missing-required log/passed.jsonl — ...
```

Doctor lints against the spec (OKF conformance, id/alias integrity, dangling
citations, custody orphans) and the notebook's profile. Profile minimums are
satisfied through use — on the scout above they stay WARNs until the first
`flip decide` and `flip pass` create `decisions/` and the passed ledger,
after which `flip doctor` reports `ok: no findings`. Once you set the
manifest status to `done`, `published`, or `archived`, anything still
missing becomes an ERROR and doctor exits 1: completion requirements, not
creation requirements.

## IDs, filenames, renames

Filenames are human slugs; the immutable id lives in the page's frontmatter
(with `aliases: [<id>]`). Cite ids in prose as `[F1]` or `[C1]` and resolve
them back to files with `flip open`:

```bash
flip open F1
# /work/nj-schools/references/districts.md
$EDITOR $(flip open F1)      # paths are absolute, so this works from any subdirectory
```

When a slug deserves a better name, `flip rename` is the only sanctioned
way — it moves the page and rewrites every markdown link and
`sources[].resource` path notebook-wide, while the id (and every `[F1]`
cite) stays put:

```bash
flip rename F1 district-enrollment-table
# F1: references/districts.md → references/district-enrollment-table.md
# rewrote links in 2 file(s)
```

## Using the notebook as an Obsidian vault

Run `flip obsidian` inside the notebook first — it merge-writes the vault
link config (so links Obsidian authors match the relative markdown links
flip writes) and installs the packaged flip plugin: doctor findings and the
hot view in a sidebar panel, a status bar summary, and open-by-id
navigation. The full walkthrough is [obsidian.md](obsidian.md).

Then open the notebook directory as a vault and it just works:

- Frontmatter renders as the **Properties** panel — re-grading a source by
  editing `grade` there is a legitimate flip operation, validated by the
  next `flip doctor` run.
- `aliases` make id wikilinks resolve: type `[[F1]]` and Obsidian finds
  `references/district-enrollment-table.md`.
- flip's generated links are relative markdown links, so the **graph view**
  lights up; the folder taxonomy (references / claims / decisions /
  questions / sessions) reads as intended structure.
- `.obsidian/` is local editor state: gitignore it; flip never reads it.

Two things to know: `index.md` bodies and `log.md` are **generated** views —
flip rewrites them on every mutating command, so edit pages, not listings —
and flip preserves frontmatter keys it doesn't own, so your own properties
survive its rewrites (and it expects the same courtesy from other tools).

## Configuring integrations

**Fastest start:** `flip config init` writes a starter `~/.flip/config.toml`
whose `web` lane uses **`flip-fetch`** — a zero-dependency helper shipped with
flip — so `flip add-source <url>` works immediately, no external tool to
install:

```console
$ flip config init
wrote ~/.flip/config.toml
next: flip add-source https://example.com  (captures via the bundled flip-fetch)
```

`flip-fetch` is a plain stdlib GET (it extracts the page title and records the
canonical URL); for JavaScript-rendered pages, paywalls, or auth, swap in a
purpose-built fetcher. Local files always copy with no configuration at all.

URLs, DOIs, and anything else route through commands you configure in
`~/.flip/config.toml` (override the directory with `$FLIP_HOME`). The bundled
helper or any public command-line tool works:

```toml
[fetchers]
web = "flip-fetch {url} {dest}"                 # bundled, zero-setup default
# web = "curl --fail --location --silent --show-error {url} --output {dest}/capture"
media = "yt-dlp {url} --output {dest}/%(title)s.%(ext)s"

# social = "your-fetcher {url} {dest}"        # inline table + --via variants also allowed:
# paper  = "your-fetcher {id} {dest}"         #   web = { cmd = "…", needs = ["cookies"] }

[extractors]                                   # raw bytes → a readable text derivative
# pdf = "your-extractor {src} {out}"          # keyed by MEDIA FAMILY, not source kind
# [extractors.pdf]                            #   named lanes work here too:
# text-layer = "pdftotext -layout {src} {out}" #   a lane named after an extraction
# ocr        = "your-ocr-tool {src} {out}"     #   method records that method for you

[research]                                     # a question → leads / cited synthesis
# find = "your-research-tool {query}"
# ask  = "your-research-tool {query}"

[knowledge]                                    # a question → what we already hold locally
# recall = "your-knowledge-tool {query}"
```

`{url}` is the target as given, `{id}` is the target with a leading `doi:`
stripped, `{query}` is a research/recall question, `{dest}` is the capture
directory `sources/raw/<source id>/`, and — for extractors — `{src}` is the raw
artifact and `{out}` the text derivative's destination. Any command works.
Commands that create one or more files use `{dest}`/`{out}`; commands that emit
the artifact on stdout may omit it, and flip preserves their stdout (as
`capture.json`/`capture.txt` for a fetcher, as the derivative itself for an
extractor). Whatever runs, its name and version when supported land in the
provenance log automatically. X/Twitter post URLs are routed to `social`; other
HTTP URLs route to `web`.

A capture command may optionally hand back a small `flip` envelope (a
`flip.json` sidecar in `{dest}`, or a JSON stdout capture with a top-level
`flip` object). flip harvests its all-optional neutral keys — `title`,
`canonical_url`, `strategy`, `retrieved_at`, `status`, `mime`, `from_cache`,
`backend_ref`, and independence/freshness *hints* — onto the page and
provenance. Hints are recorded as a page note, never the grade. This is also how
a shared cache/archive store plugs in: a fetcher that checks the store first can
serve stored bytes with `from_cache: true` and a `backend_ref`, so you don't
re-fetch what you already hold. Omit the envelope and nothing changes.

Integration commands are operator configuration, not part of flip's public
contract. Keep site-specific commands in `$FLIP_HOME/config.toml` or a separate
private integration repository; the public package, documentation, and skills
deal only in kinds/verbs and the placeholder protocol above. `flip config show`
prints the lanes configured on *this* machine and the command behind each —
the answer to "what tooling do I actually have here?", and the place to find
the binary whose `--help` may know more than the one verb flip wires.

**When a fetcher comes back empty-handed.** A command that exits 0 having
written nothing has *found nothing* — the document is gated, withdrawn, or not
served to you. That is a finding, not a broken config, and flip says so, naming
the rungs above (SPEC §5.1), the other lanes you have configured, and two ways
to close the loop:

```console
$ flip add-source 10.1017/S0140525X04000056 --kind paper --record \
    --note "fetcher: found, no full text; archive: no snapshot; publisher API: no OA copy"
P1 · sources/raw/P1/record.json · references/10-1017-s0140525x04000056.md (grade ?)
recorded, not captured — the document is not in custody, so P1 corroborates nothing.
```

`--record` is the ladder's terminus: a citable page for a source that is real,
wanted, and out of reach. It takes no bytes of the document — custody holds
flip's own record of the attempt — so it derives `thin` fidelity and the page
warns above the fold. Use `flip pass` instead when the source is *ruled out*
rather than merely unreachable. And when a capture does land, watch for
`warning: thin capture`: 800 bytes of markup is a consent wall or a JavaScript
shell, and it produces the same hash and the same page as the real document.

## Making a capture readable

Custody holds the bytes. `flip extract <id>` turns them into
`sources/text/<id>.txt` through the `[extractors]` lane for that file's media
family, and writes one row to `derived/_derivations.jsonl`:

```console
$ flip extract F1 --method text-layer
F1 · sources/text/F1.txt · 23193 words · 44 pages · 527.1 words/page · text-only · via pdftotext (text-layer)
```

flip ships no extractor and picks no default — `flip-fetch` can be bundled
because it is stdlib-only, and a PDF/OCR toolchain cannot. Configure one lane
per media family; name a lane after an extraction method
(`text-layer`, `layout-text`, `ocr`, `markup-strip`, `structured`,
`transcript`) and `--via ocr` records `method: ocr` for you.

**Record the method.** It is the reason this command exists. A quotation
recovered by OCR is not the same evidence as one lifted from the publisher's
own text layer — the second is a machine's reading of a picture of the page,
and it can drop a minus sign, a footnote marker, or a whole column without
saying so. The derivation row is the only place a later reader can find out
which one they are holding.

**Two kinds of nothing, kept apart.** An extractor that exits 0 with no words
has found no text — an image-only scan, a form with no content. That is a
finding about the *document*, not a broken config: flip writes a
`not-extracted` row, leaves **no file on disk**, exits 1, and prints the other
lanes you have configured. Under 25 words/page the file *is* written and logged
`thin`, with a loud warning, because that one leaves a plausible-looking `.txt`
behind that looks exactly like a real extraction until you open it.

`sources/raw/` is never touched, and a derivative may be overwritten —
re-running a better lane over the same document is normal. What makes that safe
is that the log is append-only: each row carries the input hash, the tool, the
verbatim command, the method, the output hash and word count, and `supersedes`
naming the derivative it replaced. It is also how flip knows its own last output
from your work: a `sources/text/*.txt` that hashes to no row was written by a
person, and `flip extract` refuses to replace it without `--force`.

**Leads vs. evidence.** `flip find "<q>"` lists candidate sources (capture one
with `--capture <n>` or `flip add-source <url>`). `flip ask "<q>"` returns cited
synthesis — a discovery **lead, grade C, not evidence**: its raw output is saved
under `sessions/raw/` and logged, but you must separately capture and judge its
cited public URLs before a load-bearing claim relies on it. `flip recall "<q>"`
reads what you already hold locally and captures nothing. If a role isn't
configured, flip prints a schematic stanza to adapt.

## Profiles

A profile sets required files, `notebook.md` sections, and the
claim-verification bar. Pick one with `flip new --kind`; list them with
`flip profiles`:

| kind | for | verification bar |
|---|---|---|
| `ledger` | bibliography / source spine | 2 independent (or grade-A) |
| `scout` | screen an angle fast; kill or graduate | 1 independent (or grade-A) |
| `research-review` | question-organized survey headed for publication | 2 independent (or grade-A) |
| `engagement` | confidential client work; policy enforced | 2 independent (or grade-A) |
| `data-investigation` | dataset-first reporting; logged derivations | 1 independent (or grade-A) |

`flip doctor` lints against the chosen profile. Projects can define their own
profiles as TOML under `.flip/profiles/` inside the notebook — profiles are
data, not code.

## Migrating an older notebook

`flip migrate` upgrades a notebook in place — run it from anywhere inside
the old notebook. v0.3 notebooks (JSONL entity ledgers with a
`notebook.toml` manifest) get the full conversion:

```bash
flip migrate
# migrated /work/legacy · 1 sources, 1 claims, 1 decisions, 1 questions, 1 sessions, 1 uid added, 0 beat link rewritten
# entity pages: references/ claims/ decisions/ questions/ sessions/ — run `flip doctor` to audit the result
```

Ids, judgment fields, and append-only history (work log, provenance,
`sources/raw/`) are preserved; the manifest moves into the root `index.md`
frontmatter; each ledger row becomes an entity page. The migration is
resumable if interrupted. Run `flip doctor` afterwards — an old
`notebook.md` typically WARNs about missing profile sections until you add
the headings.

A 0.4 notebook (already page-shaped) gets the profile pass alone: the
manifest gains its `uid` (the stable identity exports and imports carry,
SPEC §4) and a `links.beat` written with the old `#` separator moves to
the canonical `:` (SPEC §9; `#` reads are removed in flip 0.10).

**Carrying a notebook across the 0.8 judgment change.** `migrate` checks the
*pages*, not just the manifest's `flip:` version — the two drift apart, and a
notebook declaring a current profile can still hold source pages full of
pre-0.8 tuples. Where it can translate mechanically it does. Where it can't,
it parks: `independence: original` recorded **custody** ("we hold the original
bytes") while 0.8 records **epistemics** ("independent of its own subject"),
and an exact-commit copy of a project's own README is both original custody
*and* self-reported evidence. So the old letter moves to
`support.pre_08_grade`, the grade resets to `?`, and you re-read the source:

```bash
flip doctor            # leads with `vocabulary-drift`: the count, and the claims it explains
flip migrate           # translates what it can; parks `original`
flip grade A3 --explain # what the letter would take
flip grade A3 --independence self-reported --basis single-operator
```

A parked source corroborates nothing, so **claims resting on one will
demote** — deliberately: a corroboration count drawn from a judgment flip
couldn't read was never evidence of anything. Every surface that shows the
count also names the sources it couldn't count, so a 0 is never mistaken for
a verdict on your evidence.

## Next

- [SPEC.md](../SPEC.md) — the full format.
- [AGENTS.md](../AGENTS.md) — the lineage-rule contract and recipes for
  agents working in notebooks.
- [wiki-alignment.md](wiki-alignment.md) — how flip relates to OKF,
  Karpathy's LLM-wiki pattern, and OpenWiki.
- `flip export bag` (BagIt archival), `flip export csl` (citations for
  Zotero and friends), and `flip export okf` (an outside-facing copy of the
  bundle, honoring visibility policy) when a notebook needs to travel.
