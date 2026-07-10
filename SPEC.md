# flip — the reporter's notebook format

**Status:** draft v0.2 · 2026-07-09
**What this is:** a spec for a consistent, pluggable, git-friendly format for
reporter's-notebook-style research corpora created and maintained by any mix of
humans and agents — plus the tooling and skills that encourage proper use.

flip is the tooling; the **notebook** is the artifact. A notebook is a mostly
inert storage-and-retrieval scheme: plain files, no live service required to
read or trust it. Everything a downstream human or agent needs to understand
the trajectory of a piece of research lives in the notebook.

The format was distilled from a comparative survey of eight in-house notebook
implementations accumulated across two years of reporting and research
projects, and from a review of the external landscape: investigative tooling
(DocumentCloud, Aleph, Datashare, Tropy), PKM systems (Zotero, Obsidian,
Logseq), packaging and provenance standards (BagIt, RO-Crate, Frictionless,
W3C PROV, W3C Web Annotation), web archiving (WARC, ArchiveBox, SingleFile),
AI research agents (NotebookLM, STORM), and intelligence-community source
grading (Admiralty/NATO codes).

flip has **no required dependencies** on any proprietary or in-house system.
Every integration point is pluggable; every notebook is intelligible from its
local files alone.

---

## 1. Principles

1. **Custody.** Gain and keep local archival copies of the information we rely
   on and build upon; never depend on continued public availability.
2. **Reprocessable.** Raw material is preserved verbatim; all processing (OCR,
   HTML→text, transcription) and enrichment are *derivations* that can be
   re-run, re-assessed, and interrogated.
3. **Layered authorship.** Human- and machine-produced material (hypotheses,
   questions, findings, drafts) sits *on top of* sources, clearly typed and
   attributed, never blended into them.
4. **Judged sources.** Source quality is an explicit, recorded judgment:
   authoritativeness, independence, corroboration, freshness.
5. **Traceable reasoning.** Work logs and LLM/tool session logs record how we
   came to information and ideas — the reasoning chain is evidence too.
6. **Timestamped evolution.** Everything is dated; the notebook shows how
   understanding evolved, not just where it ended up.
7. **Inert and portable.** Plain text first (markdown, TOML, JSONL, CSV);
   readable with `less`; diffable with `git`; no required daemon, index, or
   external service.
8. **Canonical notebook, derived renders.** Published artifacts (sites,
   reports, cards) are renders of the notebook; edits flow back to the
   notebook, never directly to a render.
9. **Tools noted.** Every acquisition and enrichment records the tool that did
   it, its version and strategy, and when.
10. **Profiles, not ceremony.** A light scout notebook and a heavyweight
    research review share one format; profiles define the minimum each kind
    must fill. Empty structure is worse than absent structure.

## 2. Definitions

- **Notebook** — one directory conforming to this spec; the unit of custody
  and meaning. Lives inside a host project (`<project>/notebook/`) or
  standalone.
- **Source** — an external artifact we captured: paper, article, dataset,
  filing, transcript, screenshot, API response.
- **Derivation** — a file produced from sources by a recorded process (OCR
  text, parsed tables, transcripts, entity extractions, embeddings).
- **Claim** — a discrete assertion the work makes or relies on, linked to
  sources and a verification status.
- **Session** — one recorded human/agent working episode (an LLM run, a
  research-service sweep, a scout query batch).
- **Render** — a downstream artifact generated from the notebook.
- **Beat** — an optional grouping layer above notebooks: a standing mission
  that spawns and references many notebooks over time (§13).

## 3. Directory layout

```text
<notebook>/
  notebook.toml            # manifest (required)
  notebook.md              # the human heart: prose working memory (required)
  sources/
    ledger.jsonl           # one record per source: id, grading, custody (required if any source)
    _provenance.jsonl      # append-only capture log: who/what/when/how/sha256
    raw/                   # verbatim bytes as captured (pdf, html, warc, json, png)
    text/                  # readable derivatives of raw/ (md/txt), 1:1 by source id
  derived/
    _derivations.jsonl     # append-only processing log: input hashes → output hashes, tool, params
    ...                    # parsed tables, transcripts, entity graphs, extractions
  analysis/
    claims.jsonl           # claim ledger: id, text, status, sources, corroboration
    hypotheses.md          # hypotheses & falsifiers, and what survived (may live in notebook.md)
    ...                    # findings.md, memos, priors.md — graduated sections
  log/
    log.jsonl              # append-only work log (one line per event)
    decisions.jsonl        # append-only decision ledger
    passed.jsonl           # negative evidence: considered and rejected, with reasons
    sessions/              # per-session records: <UTC ts>-<slug>.md (+ raw transcripts)
  drafts/                  # versioned drafts: v0/, v1/, current -> vN  (production profiles)
  renders/                 # generated downstream artifacts (gitignored or committed per policy)
  HANDOFF.md               # cold-start resume view (graduates from notebook.md)
  lessons.md               # end-of-life: what worked, prescriptive, for other notebooks
```

Only `notebook.toml` and `notebook.md` are universally required; profiles
(§12) define the rest. Directories appear when first needed — tooling creates
them lazily, never as empty scaffolding.

### Naming rules

- Notebook file is `notebook.md`, lowercase, always.
- Log/session files are date-prefixed UTC: `2026-07-09T1430-corpus-sweep.md`.
- Source ids are compact and prefixed by kind: `P1` papers, `A1` articles,
  `D1` datasets/documents, `T1` talks/transcripts, `S1` when unkinded.
- Private scratch files use a `_` prefix and are never rendered.

### Detached notebooks

A notebook's visibility can exceed its host repo's: a public repo may have a
private notebook. In that case the notebook detaches to a sibling directory
(`<project>-private/` holding `notebook.md`, `notebook.toml`, and the rest),
and the public repo carries **no reference** to its contents. The manifest's
`host` field records what the notebook is about:

```toml
host = "flip"   # the project this detached notebook documents
```

## 4. The manifest — `notebook.toml`

```toml
slug = "nj-schools"
title = "NJ schools: five years of test-score and performance data"
kind = "scout"                  # profile id, §12
status = "active"               # active | dormant | done | published | archived
created = "2026-07-09"
updated = "2026-07-09"          # tooling maintains

[policy]
visibility = "internal"          # private | internal | client-confidential | public
renders_public = false           # may renders ship?
source_trail_public = false      # may the source list ship?
citation_rule = "public-terminus" # every load-bearing chain must end at a
                                  # public, independently verifiable source

[links]                          # systems this notebook leans on — free-form
                                 # keys, all optional, never load-bearing
corpus = ""                      # e.g. a RAG/retrieval service reference
graph = ""                       # e.g. a knowledge-graph reference
render = ""                      # render target project/path
relations = []                   # sibling projects/notebooks
consumers = []                   # who reads this notebook downstream

[tools]                          # fetchers/processors used, versioned when known
web = "single-file 1.22"
paper = "doi-fetcher 0.3"
transcribe = "whisper 3.1"
```

`visibility` and the citation rule are machine-readable because prose
confidentiality notes were a recurring gap in every implementation surveyed.

## 5. Sources — custody, ledger, provenance

### 5.1 Custody rules

- `sources/raw/` holds **verbatim bytes as captured** — never edited, never
  re-encoded. One file (or one directory for multi-file captures) per source id.
- Web pages: prefer a self-contained capture (SingleFile HTML or WARC) plus
  the extracted-text derivative in `sources/text/`. PDFs and datasets: the
  original file. API pulls: the verbatim response JSON.
- Once captured, a raw file is immutable; recapture creates a new dated entry,
  it does not overwrite.

### 5.2 The capture log — `sources/_provenance.jsonl` (append-only)

One line per acquisition event:

```json
{"ts":"2026-07-09T14:31:02Z","source_id":"A3","url":"https://…","url_used":"https://…",
 "local_path":"sources/raw/A3.html","sha256":"…","bytes":48210,"http_status":200,
 "tool":"single-file","tool_version":"1.22","strategy":"headless","actor":"agent:claude",
 "note":"index page lied; probed URL pattern directly"}
```

This is the fixity record — hash at capture, per file — giving BagIt-grade
custody where it matters without whole-tree manifest churn. `flip export bag`
can emit a real BagIt bag for cold archival.

### 5.3 The source ledger — `sources/ledger.jsonl`

One JSON object per source; current-state, edited in place as judgments
change (git history is the temporal record):

```json
{"id":"A3","kind":"article","title":"…","authors":["…"],"date":"2025-11-23",
 "publisher":"…","url":"https://…","local":"sources/raw/A3.html","text":"sources/text/A3.md",
 "grade":"B","independence":"original","freshness":"fresh","status":"captured",
 "supports":["C2","C7"],"notes":"speaker-bureau republisher avoided; this is the original"}
```

### 5.4 Source-quality model

Two separate judgments, never conflated (after the Admiralty/NATO practice of
grading source reliability apart from information credibility):

**Source reliability** (on the source, in `ledger.jsonl`):

| field | values |
|---|---|
| `grade` | `A` authoritative primary (gov/peer-reviewed/data we extracted ourselves) · `B` official docs, independent journalism, platform docs · `C` vendor/practitioner/commercial/internal LLM synthesis · `?` not yet obtained/judged |
| `independence` | `original` · `republisher` · `derivative` · `self-interested` |
| `freshness` | `fresh` · `dated` (default threshold ~18 months, profile-tunable) |

**Claim credibility** (on the claim, in `analysis/claims.jsonl`, §7). LLM and
retrieval-service outputs are always grade `C` intermediaries; under
`citation_rule = "public-terminus"` a load-bearing chain must end at a public,
independently verifiable source.

## 6. Derivations — processing you can interrogate

Every processed artifact is reproducible and logged in
`derived/_derivations.jsonl` (append-only):

```json
{"ts":"2026-07-09T15:02:11Z","inputs":[{"path":"sources/raw/P2.pdf","sha256":"…"}],
 "outputs":[{"path":"derived/P2-tables.csv","sha256":"…"}],
 "tool":"pdftotext","tool_version":"24.02","cmd":"pdftotext -layout …",
 "params":{},"actor":"agent:claude","quality_notes":"image-only pages 3-4 skipped; OCR needed"}
```

This is a deliberately small PROV profile: inputs (entities) → activity (tool,
cmd, params, actor) → outputs. Rich PROV/RO-Crate graphs can be *generated*
from it; nobody hand-writes RDF mid-reporting. The companion discipline: a
derived data file is a **frozen contract** — never hand-edited; all changes go
back through the recorded process.

Indexes, embeddings, and entity graphs live here too: they are **derived,
disposable, and re-derivable** — never the trusted original. (The recurring
failure in hosted investigative tools is the index quietly becoming the
evidence.)

## 7. Analysis — the layered human/machine material

### 7.1 `notebook.md` — the prose heart

Scaffolded by profile from a section menu; sections are prompts, not a form —
delete what a project doesn't need, and heavy sections **graduate** to their
own file with a pointer left behind.

Canonical section menu (order fixed, membership per profile):

> **the tip** · frame · what the data can/can't say · **hypotheses &
> falsifiers** · sources & provenance · priors ledger · decisions · what's not
> in the piece · workflow notes · **gaps & self-critique** · handoff

Conventions that earned their place across the surveyed implementations:

- Hypotheses are set **before** looking, each with a named falsifier; a
  "what survived the reporting" audit closes the loop.
- Chronological log entries are dated, newest first, and record walls hit and
  pivots — the "why" that git history can't recover.
- Working thesis is rewritten as evidence lands, version-marked (v1, v2…).

### 7.2 `analysis/claims.jsonl` — the claim ledger

For work with load-bearing assertions (research reviews, engagements,
published pieces):

```json
{"id":"C7","text":"AI retail traffic converts ~42% better than non-AI",
 "status":"needs-2nd","load_bearing":true,"sources":["A12"],
 "independent_corroboration":1,"first_asserted":"2026-07-09","actor":"agent:claude",
 "notes":"single vendor study; seek platform data or second measurement"}
```

`status`: `asserted` → `verified` | `needs-2nd` | `unconfirmed` |
`false-positive` | `retracted` | `superseded`. A claim is `verified` only with
the corroboration its profile demands (default: two independent sources or
one grade-A primary).

Fine-grained anchoring (claim → exact span in a source) uses W3C Web
Annotation selectors stored per claim when needed; optional, not required.

## 8. Logs — work, decisions, negatives, sessions

All append-only JSONL; one event per line; every line has `ts` (ISO 8601 UTC)
and `actor` (`human:<name>`, `agent:<name>`, `tool:<name>`).

- **`log/log.jsonl`** — the work log: fetched X, ran Y, hit wall Z. Terse.
- **`log/decisions.jsonl`** — `{ts, id:"D3", question, decision, why,
  alternatives_rejected, actor}`. The "why" is the payload — the "what" is
  recoverable from git, the why isn't.
- **`log/passed.jsonl`** — negative evidence: what was considered and
  rejected, with reason. Prevents rediscovery loops and records the road not
  taken.
- **`log/sessions/`** — one file per working episode:
  `2026-07-09T1420-landscape-scan.md` with frontmatter
  (`actor`, `model`, `effort`, `tools`, `tokens`, `duration`) + the goal, the
  prompt (or pointer to it), key outputs, and a pointer to the full raw
  transcript when kept. LLM synthesis output stored here is a **lead**, grade
  `C`, until promoted through the source ledger.

## 9. IDs and cross-references

- Per-notebook compact ids: `P#/A#/D#/T#/S#` sources · `C#` claims · `D#`
  decisions · `Q#` open questions · `H#` hypotheses.
- Prose cites ids in brackets: `[A3]`, `[C7]` — greppable both directions.
- Cross-notebook references use `<slug>#<id>` (`nj-schools#C7`).
- ids are never reused, even after retraction.

## 10. Hot/cold views

Notebooks grow. The format stays inert; **views are computed**, not stored:
`flip show` assembles the hot view (current focus, open questions, active
claims needing corroboration, stale threads, recent log, latest sessions) from
the ledgers. Nothing is deleted to keep context small — hot vs cold is a
windowed projection.

## 11. Renders and drafts

- Drafts are versioned explicitly: `drafts/v0/`, `drafts/v1/`, `current`
  symlink; each version carries a `changelog.md` naming what changed and which
  finding/decision drove it.
- Renderers are pure: same notebook in, same render out; they write only to
  `renders/<target>/` and never mutate the notebook. Fixes discovered in a
  render flow back as a new draft version, then re-render.
- Editorial draft versions and *publication* snapshots are different concerns;
  a publish operation reads `drafts/current` at the moment of publish.
- Whether `renders/` is committed is a `[policy]` decision; default gitignored.

## 12. Profiles

A profile = required files + notebook.md sections + claim-verification bar.
Everything else is optional everywhere.

| profile | intent | requires beyond core |
|---|---|---|
| `ledger` | bibliography / source spine | sources/ with ledger |
| `scout` | screen an angle fast, editor lens active | hypotheses w/ falsifiers per query · decisions.jsonl · passed.jsonl |
| `research-review` | question-organized survey → publishable | claims.jsonl · sessions/ · drafts/ · full custody · workflow journal |
| `engagement` | confidential client work | research-review + `client-confidential` policy + citation_rule enforced + HANDOFF.md |
| `data-investigation` | dataset-first reporting | derived/_derivations.jsonl · ingest scripts · frozen data contracts |

Profiles are data (a TOML file shipped with flip), not code — projects can
define their own. `kind` in the manifest selects one; `flip doctor` lints
against it.

## 13. Beats — the grouping layer above notebooks

A **beat** is a standing mission that outlives any single notebook: "school
funding in this county," "AI and local news." The relationship is
containment: *a beat contains many notebooks* — scouts that died, reviews
that published, investigations in flight.

The beat layer is a sibling structure, not a notebook profile. It shares the
ledger grammar (JSONL, append-only, actor/ts) but holds different state:

```text
<beat>/
  beat.toml                # mission, cadence, scope
  threads.jsonl            # the thread ledger: arcs (self-initiated
                           #   investigations) and veins (recurring
                           #   typifications monitored reactively), with
                           #   status and priority scores
  coverage.jsonl           # what's been covered, which sources recur
  notebooks/               # or pointers to notebooks living elsewhere
```

Threads spawn notebooks: an arc that gets real graduates from a line in
`threads.jsonl` to a `scout` notebook, and maybe from there to a
`research-review`. The beat keeps cross-notebook memory: recurring wells,
saturation warnings, what was passed on and why.

v0.2 specs the boundary and the containment relationship; the beat layer's
full shape is future work (§17).

## 14. Tooling — the flip CLI

Small, boring, filesystem-only core; no LLM calls and **no network services**
in the library. Fetchers are pluggable externals.

```text
flip new <slug> --kind <profile>     # scaffold manifest + notebook.md sections
flip add-source <url|doi|file|->     # route to a registered fetcher by type,
                                     #   write raw/ + text/, hash, append provenance,
                                     #   open ledger entry with grade "?"
flip log "<text>"                    # append work-log event (actor auto-detected)
flip decide|pass|question ...        # append to the respective ledger
flip claim add|status ...            # claim ledger operations
flip session start|end ...           # session record scaffolding
flip show [--hot|--claims|--stale]   # computed views
flip doctor                          # lint: profile minimums, orphan sources,
                                     #   unhashed raw files, load-bearing claims
                                     #   below verification bar, stale freshness
flip export bag|ro-crate|csl         # interop exports (cold archival, citations)
flip index                           # rebuild the per-user registry (see below)
```

### Pluggable fetchers

`flip add-source` routes by input type to fetchers registered in
`~/.flip/config.toml`:

```toml
[fetchers]
web = "single-file {url} --output {dest}"        # any command; {url}/{dest} templated
paper = "doi-fetch {id} --dir {dest}"
media = "yt-dlp {url} -o {dest}"
file = "builtin:copy"                            # copy + hash, no external tool
```

Whatever runs, the tool name, version, and strategy land in
`_provenance.jsonl` automatically — principle 9 costs nothing when the tool
does it. Organizations with their own capture stacks plug them in here; flip
never hard-codes a fetcher beyond `builtin:copy`.

### The registry

`flip index` scans configured roots and writes `~/.flip/index.jsonl` — one
line per notebook (path, slug, kind, status, updated). A plain file, built by
scanning, no service, no proprietary dependency. Anything richer (concept
registries, dashboards) consumes this file; flip doesn't know about them.

### Skills (the encouragement layer)

Tooling makes correct use *possible*; skills make it *habitual*. Shipped
alongside the CLI as markdown skill definitions usable by any agent runtime:

- `notebook-create` — interview → pick profile → scaffold → seed the tip.
- `notebook-source` — capture + grade discipline (original-vs-republisher
  check, freshness flag, public-terminus check).
- `notebook-log` — session hygiene: record the episode, promote leads to
  sources, route follow-ups to `Q#`.
- `notebook-audit` — pre-publish gate: walk load-bearing claims against the
  verification bar; emit the coverage map (solidly sourced / authorial frame /
  flagged for further reporting).
- `notebook-handoff` — write/refresh HANDOFF.md for cold pickup.
- `notebook-lessons` — end-of-life distillation to lessons.md; feeds the
  cross-notebook compound loop.

## 15. Integration contract

A notebook must remain intelligible from its local files alone; integrations
are referenced, never required, and never proprietary-by-design.

| role | how referenced |
|---|---|
| capture tools (web, papers, media) | `[fetchers]` config + `tool` field in provenance records |
| retrieval/RAG corpus services | `[links] corpus`; raw query outputs land in `log/sessions/`; findings promoted via the source ledger as grade `C` intermediaries |
| knowledge graphs / lead trackers | `[links] graph`; cross-refs by id |
| shared blob/archive stores | provenance records may carry a store id **alongside** the mandatory local copy |
| render targets (sites, reports) | `[links] render`; renderer reads notebook, writes `renders/<target>/` |
| registries / task systems | consume `~/.flip/index.jsonl`; flip has no reverse dependency |

Local copy is mandatory even when a shared store also holds the bytes —
custody is not delegated.

## 16. Git conventions

- One notebook = one directory; embedded in the host repo it documents
  (default) or detached per §3 when visibility demands.
- JSONL ledgers are append-only (except `sources/ledger.jsonl`,
  current-state-with-history-in-git); merge conflicts resolve by union.
- `sources/raw/` is committed by default; use git-lfs or a pointer file above
  a size threshold (profile-tunable, default 25 MB) — the hash in
  `_provenance.jsonl` keeps custody honest either way.
- Renders gitignored by default; `notebook.md` never ships to a render's
  output unless `[policy]` says so.

## 17. Interop (optional, generated)

- **BagIt** bag for cold archival (`flip export bag`).
- **RO-Crate** metadata envelope generated from manifest + ledgers
  (`flip export ro-crate`) — for sharing with the outside world.
- **CSL JSON** from the source ledger for citation managers.
- **Web Annotation JSON-LD** for span-level claim anchors.

Canonical remains the plain-file layout; these are projections. (The repeated
failure mode in the surveyed landscape: the abstract format or the hosted
index becomes the source of truth, and the archive dies with the service.)

## 18. Open questions

- **Profile tunables** — which fields are per-profile-tunable vs fixed?
- **Beat layer** — full shape of `beat.toml`/`threads.jsonl`; how thread
  scoring and review cadence work; when a thread must graduate to a notebook.
- **OCR/transcript quality provenance** — `quality_notes` in derivation
  records is a start; structured per-page/per-segment confidence is future
  work.
- **Corroboration graph** — `independent_corroboration` counts are the v0; a
  real source-independence graph (shared upstream origins detected) is future
  work.
- **Migration** — adapters so existing notebook-shaped corpora join the
  format with their history rather than restarting.
