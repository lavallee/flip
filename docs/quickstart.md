# Quickstart

flip keeps research honest: every source you rely on is captured locally and
hashed, every judgment about source quality is recorded, every load-bearing
claim is linked to sources and gated before it can be called verified, and
the whole trail is plain files in git.

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

Requires Python 3.12+. The core is stdlib + click: no network calls, no LLM
calls, no services.

## Create a notebook

```bash
flip new nj-schools --kind scout --title "NJ enrollment dip"
cd nj-schools
```

You get exactly two files — `notebook.toml` (the manifest) and `notebook.md`
(prose working memory, scaffolded with section stubs like "The tip" and
"Hypotheses & falsifiers"). Everything else appears lazily as commands need
it. Every `flip` command works from anywhere inside the notebook.

If you're an agent (or supervising one), set the actor once:

```bash
export FLIP_ACTOR="human:marc"     # or agent:claude, tool:ingest-script
```

## The core loop

**Capture** the moment you rely on something external:

```bash
flip add-source ./districts.csv --note "district enrollment table"
# F1 · file · sources/raw/F1.csv (grade ?)
```

The bytes land verbatim in `sources/raw/`, get hashed into the append-only
provenance log, and open a ledger row at grade `?`.

**Grade** after you've actually read it:

```bash
flip grade F1 --grade A --independence original --notes "state data, extracted ourselves"
```

`A` authoritative primary · `B` official/independent · `C` vendor,
practitioner, or LLM synthesis. `independence` records whether this is the
original or downstream of one — republishers don't count as corroboration,
and neither does a source still graded `?` (capture is custody, not
judgment). `flip source list` shows the whole ledger at a glance; any `?`
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

**Show** the hot view — the resume-here screen, computed from the ledgers:

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
# WARN missing-required log/decisions.jsonl — profile 'scout' requires
#   log/decisions.jsonl (it appears with use; required before
#   done/published/archived); create it
# WARN missing-required log/passed.jsonl — ...
```

Doctor lints against the notebook's profile. Profile minimums are satisfied
through use — on the scout above they stay WARNs until the first
`flip decide` and `flip pass` create its decision and passed ledgers, after
which `flip doctor` reports `ok: no findings`. Once you set the manifest
status to `done`, `published`, or `archived`, anything still missing becomes
an ERROR and doctor exits 1: completion requirements, not creation
requirements.

## Configuring fetchers

Local files copy with no configuration. URLs, DOIs, and anything else route
through commands you configure in `~/.flip/config.toml` (override the
directory with `$FLIP_HOME`). Example, using
[SingleFile CLI](https://github.com/gildas-lormeau/single-file-cli) for
self-contained web captures:

```toml
[fetchers]
web = "single-file {url} --output {dest}"
paper = "doi-fetch {id} --dir {dest}"
media = "yt-dlp {url} -o {dest}"
```

`{url}` is the target as given, `{id}` is the target with a leading `doi:`
stripped, `{dest}` is the capture directory `sources/raw/<source id>/`. Any
command works; whatever runs, its name and version land in the provenance
log automatically. If a fetcher isn't configured, `flip add-source` tells
you the exact stanza to add.

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

## Next

- [SPEC.md](../SPEC.md) — the full format.
- [AGENTS.md](../AGENTS.md) — conventions and recipes for agents working in
  notebooks.
- `flip export bag` (BagIt archival) and `flip export csl` (citations for
  Zotero and friends) when a notebook needs to travel.
