# Quickstart

flip keeps research honest: every source you rely on is captured locally and
hashed, every judgment about source quality is recorded, every load-bearing
claim is linked to sources and gated before it can be called verified, and
the whole trail is plain files in git. The notebook is a conformant OKF v0.1
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
flip grade F1 --grade A --independence original --notes "state data, extracted ourselves"
# F1 · grade A · original · fresh
```

`A` authoritative primary · `B` official/independent · `C` vendor,
practitioner, or LLM synthesis. `independence` records whether this is the
original or downstream of one — republishers don't count as corroboration,
and neither does a source still graded `?` (capture is custody, not
judgment). `flip source list` shows every source at a glance; any `?`
line still needs judging.

**Claim** when the work starts leaning on an assertion:

```bash
flip claim add "District enrollment fell 4.2% since 2021" --source F1 --load-bearing
# C1 asserted · sources: F1 · corroboration: 1
```

**Verify** — flip enforces the profile's corroboration bar (default: two
independent original sources, or one grade-A primary):

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
way — it moves the page and rewrites every markdown link and `supports` path
notebook-wide, while the id (and every `[F1]` cite) stays put:

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

## Configuring fetchers

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

[research]                                     # a question → leads / cited synthesis
# find = "your-research-tool {query}"
# ask  = "your-research-tool {query}"

[knowledge]                                    # a question → what we already hold locally
# recall = "your-knowledge-tool {query}"
```

`{url}` is the target as given, `{id}` is the target with a leading `doi:`
stripped, `{query}` is a research/recall question, and `{dest}` is the capture
directory `sources/raw/<source id>/`. Any command works. Commands that create
one or more files use `{dest}`; commands that emit the artifact on stdout may
omit `{dest}`, and flip preserves their stdout as `capture.json` or
`capture.txt`. Whatever runs, its name and version when supported land in the
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
deal only in kinds/verbs and the placeholder protocol above.

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

## Next

- [SPEC.md](../SPEC.md) — the full format.
- [AGENTS.md](../AGENTS.md) — the lineage-rule contract and recipes for
  agents working in notebooks.
- [wiki-alignment.md](wiki-alignment.md) — how flip relates to OKF,
  Karpathy's LLM-wiki pattern, and OpenWiki.
- `flip export bag` (BagIt archival), `flip export csl` (citations for
  Zotero and friends), and `flip export okf` (an outside-facing copy of the
  bundle, honoring visibility policy) when a notebook needs to travel.
