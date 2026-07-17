# flip — the reporter's notebook format

**Status:** draft v0.8 · 2026-07-16
**What this is:** a spec for a consistent, pluggable, git-friendly format for
reporter's-notebook-style research corpora created and maintained by any mix of
humans and agents — plus the tooling and skills that encourage proper use.

flip is the tooling; the **notebook** is the artifact. A notebook is a mostly
inert storage-and-retrieval scheme: plain files, no live service required to
read or trust it. Everything a downstream human or agent needs to understand
the trajectory of a piece of research lives in the notebook.

As of v0.4, **a flip notebook is a conformant
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
(OKF v0.1) knowledge bundle at rest** — not an export target. flip is an
*extension profile* of OKF, not a competing format: it adds the provenance
vocabulary and generation discipline that OKF deliberately leaves open, so
that LLM-built wikis preserve lineage (§6). Any OKF consumer can browse a
live notebook; any OKF-literate agent can contribute to one, and `flip
doctor` audits the result.

The format was distilled from a comparative survey of eight in-house notebook
implementations, and from the external landscape: investigative tooling
(DocumentCloud, Aleph, Datashare, Tropy), PKM systems (Zotero, Obsidian,
Logseq), packaging and provenance standards (BagIt, RO-Crate, Frictionless,
W3C PROV, W3C Web Annotation), web archiving (WARC, ArchiveBox, SingleFile),
the LLM-wiki pattern (Karpathy's framing, OKF, LangChain's OpenWiki), and
intelligence-community source grading (Admiralty/NATO codes).

flip has **no required services** and only two library dependencies (click,
PyYAML). Every integration point is pluggable; every notebook is intelligible
from its local files alone.

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
7. **Inert and portable.** Plain text first (markdown + YAML frontmatter,
   JSONL); readable with `less`; diffable with `git`; browsable by any OKF
   consumer or markdown editor; no required daemon, index, or service.
8. **Canonical notebook, derived renders.** Published artifacts (sites,
   reports, public bundles) are renders of the notebook; edits flow back to
   the notebook, never directly to a render.
9. **Tools noted.** Every acquisition and enrichment records the tool that did
   it, its version and strategy, and when.
10. **Profiles, not ceremony.** A light scout notebook and a heavyweight
    research review share one format; profiles define the minimum each kind
    must fill. Empty structure is worse than absent structure.
11. **Graceful co-editing.** Humans and agents work in the same files. The
    format favors representations both edit well — one entity per file,
    frontmatter for metadata, prose for thought — and the tooling validates
    after the fact instead of gatekeeping before.

## 2. Definitions

- **Notebook** — one directory conforming to this spec; the unit of custody
  and meaning; a valid OKF knowledge bundle. Lives inside a host project
  (`<project>/notebook/`) or standalone.
- **Entity page** — one markdown file with YAML frontmatter representing one
  source, claim, decision, question, or session. Entity pages are OKF
  *concepts* and the canonical record for their entity.
- **Event ledger** — an append-only JSONL sidecar recording things that
  happened (work log, captures, derivations, rejections). Never rewritten.
- **Source** — an external artifact we captured: paper, article, dataset,
  filing, transcript, screenshot, API response.
- **Derivation** — a file produced from sources by a recorded process.
- **Claim** — a discrete assertion the work makes or relies on, linked to
  sources and a verification status.
- **Session** — one recorded human/agent working episode.
- **Render** — a downstream artifact generated from the notebook.
- **Beat** — an optional grouping layer above notebooks: a standing mission
  that spawns and references many notebooks over time (§14).

## 3. Directory layout

```text
<notebook>/
  index.md                 # bundle root (required): manifest frontmatter (§4)
                           #   + generated directory listing
  notebook.md              # the prose heart: working memory (required)
  log.md                   # generated view of the work log (OKF reserved file)
  references/              # sources — one entity page per source
    <slug>.md              #   type: Source; custody + judgment frontmatter
    index.md               #   generated listing
  claims/<slug>.md         # type: Claim (+ generated index.md)
  decisions/<slug>.md      # type: Decision (+ generated index.md)
  questions/<slug>.md      # type: Question (+ generated index.md)
  sessions/                # type: Work Session — one page per episode
    <UTC stamp>-<slug>.md
  analysis/                # graduated prose: hypotheses.md, findings.md, …
                           #   (concept pages: any type fits)
  sources/
    raw/                   # verbatim bytes as captured (non-md; OKF-unconstrained)
    text/                  # readable derivatives of raw/, 1:1 by source id
    _provenance.jsonl      # append-only capture log: who/what/when/how/sha256
  derived/
    _derivations.jsonl     # append-only processing log
    ...                    # parsed tables, transcripts, extractions
  log/
    log.jsonl              # append-only work log (one event per line)
    passed.jsonl           # negative evidence: considered and rejected
  drafts/                  # versioned drafts: v0/, v1/, current -> vN
  renders/                 # generated downstream artifacts (gitignored by default)
  HANDOFF.md               # cold-start resume view (graduates from notebook.md)
  lessons.md               # end-of-life distillation, for other notebooks
```

Only `index.md` and `notebook.md` are universally required; profiles (§13)
define the rest. Directories appear when first needed.

**OKF conformance:** every non-reserved `.md` file carries frontmatter with a
`type`; `index.md` and `log.md` follow OKF's reserved-file structures;
everything under `sources/raw/`, `derived/`, and the `_*.jsonl` ledgers is
non-markdown sidecar content, which OKF explicitly leaves unconstrained.

### Naming rules

- **Entity filenames are human slugs, not ids**: `references/
  lecun-jepa-keynote.md`, `claims/ai-traffic-converts-42pct.md`. The stable
  id lives in frontmatter (§9). Slugs are `^[a-z0-9][a-z0-9-]*$`, derived
  from the title/text at creation (collisions get `-2`, `-3`); `flip rename`
  changes a slug and rewrites every link to it.
- Session files are UTC-stamped: `2026-07-10T1430-corpus-sweep.md`.
- Private scratch files use a `_` prefix and are never rendered or listed.
- `index.md` and `log.md` are OKF-reserved names: never used for entities.

### Detached notebooks

A notebook's visibility can exceed its host repo's: a public repo may have a
private notebook. The notebook then detaches to a sibling directory
(`<project>-private/`), and the public repo carries **no reference** to its
contents. The manifest's `host` key records what the notebook is about.

### Workspaces

Many notebooks can share one vault or repo. The shared root is a
**workspace root**: it carries `.flip/workspace.toml`, a local table binding
short handles to notebook paths so qualified cross-notebook refs
(`recipes:A3`) resolve (§18). The table is machine-local state — it never
ships in any export or bag.

## 4. The manifest — root `index.md` frontmatter

OKF sanctions frontmatter on exactly one index: the bundle root. That is
flip's manifest slot — notebook identity lives where any OKF consumer
already looks, and where Obsidian shows it as editable properties.

```markdown
---
okf_version: "0.1"
flip: "0.5"                 # flip profile version this notebook conforms to
slug: nj-schools
uid: nb-7k3m9p2x             # stable machine identity; travels with the bundle
title: "NJ schools: five years of test-score data"
kind: scout                  # profile id, §13
status: active               # active | dormant | done | published | archived
created: 2026-07-09
updated: 2026-07-10          # tooling maintains
host: ""                     # set only for detached notebooks
origin: ""                   # provenance of an imported copy (`flip import`)
visibility: internal         # private | internal | client-confidential | public
renders_public: false
source_trail_public: false
citation_rule: public-terminus
links:                       # systems this notebook leans on — free-form, optional
  corpus: ""
  render: ""
relations: []
consumers: []
tools:                       # fetchers/processors used, versioned when known
  web: "single-file 1.22"
---
# NJ schools: five years of test-score data

* [References](references/) - 12 captured sources with custody and grading
* [Claims](claims/) - 4 claims with status and citations
…
```

The body below the frontmatter is the **generated** OKF directory listing —
flip regenerates it on every mutating command; hand-edits to the body don't
survive. Frontmatter keys flip doesn't know are preserved on rewrite.

Two identity keys arrived with profile 0.5:

- **`uid`** — a stable, machine-generated notebook identity: `nb-` plus
  eight characters of a vowel-free base32 alphabet
  (`0123456789bcdfghjkmnpqrstvwxyz`), e.g. `nb-7k3m9p2x`. Minted once, by
  `flip new` (or by `flip migrate` for older notebooks), and never edited:
  an existing uid is identity and is never re-minted. It is metadata only —
  it appears in no link or filename — and it **travels with the bundle**:
  exports carry it in the root frontmatter, `flip import` preserves it, and
  every copy of a notebook (including forks) shares the lineage uid, which
  is how `flip import --update` recognizes "the same notebook" (§17).
- **`origin`** — provenance of an imported copy, written by `flip import`:
  the source path and import date. Empty (and omitted from the emitted
  frontmatter) on notebooks that were never imported.

## 5. Sources — custody, entity pages, provenance

### 5.1 Custody rules

- `sources/raw/` holds **verbatim bytes as captured** — never edited, never
  re-encoded. One file (or one directory for multi-file captures) per source.
- Web pages: prefer a self-contained capture (SingleFile HTML or WARC) plus
  the extracted-text derivative in `sources/text/`. PDFs and datasets: the
  original file. API pulls: the verbatim response JSON.
- Once captured, a raw file is immutable; recapture creates a new dated
  entry, it does not overwrite.

### 5.2 The capture log — `sources/_provenance.jsonl` (append-only)

One line per acquisition event:

```json
{"ts":"2026-07-09T14:31:02Z","source_id":"A3","url":"https://…","url_used":"https://…",
 "local_path":"sources/raw/A3/page.html","sha256":"…","bytes":48210,"http_status":200,
 "tool":"single-file","tool_version":"1.22","strategy":"headless","actor":"agent:claude",
 "note":"index page lied; probed URL pattern directly"}
```

This is the fixity record — hash at capture, per file. `flip export bag`
emits a real BagIt bag for cold archival.

### 5.3 The source entity page — `references/<slug>.md`

The canonical record of a source is its page; frontmatter carries what a
machine needs, the body carries what a human wrote:

```markdown
---
type: Source
id: A3
aliases: [A3]
title: "LeCun keynote, Global AI Frontiers Symposium"
description: "Primary transcript for the 'LLMs useless in five years' quote"
resource: "https://example.com/lecun-keynote"
date: 2025-10-27
authors: ["Yann LeCun"]
publisher: example.com
local: sources/raw/A3/page.html
grade: B
independence: original
freshness: fresh
status: captured
---
# LeCun keynote, Global AI Frontiers Symposium

Capture notes, pull-quotes, misgivings — anything a reader of this source
should know before trusting it.
```

`aliases` always contains the id, so typing `[[A3` suggests this page in
wikilink-aware editors while the filename stays readable (§9 on what aliases
honestly buy).

### 5.4 Source-quality model

Two separate judgments, never conflated (after the Admiralty/NATO practice):

**Source reliability** (frontmatter on the source page):

| key | values |
|---|---|
| `grade` | `A` authoritative primary (gov/peer-reviewed/data we extracted ourselves) · `B` official docs, independent journalism, platform docs · `C` vendor/practitioner/commercial/LLM synthesis · `?` not yet judged |
| `independence` | `original` · `republisher` · `derivative` · `self-interested` |
| `freshness` | `fresh` · `dated` (default threshold ~18 months, profile-tunable) |

**Claim credibility** lives on the claim (§7). LLM and retrieval-service
outputs are always grade `C` intermediaries; under `citation_rule:
public-terminus` a load-bearing chain must end at a public, independently
verifiable source. **Ungraded sources never corroborate:** a source still
graded `?` counts toward nothing — capture is custody, not judgment.

## 6. The flip profile — lineage rules for LLM-built wikis

This is the "extension to OKF" in one section: the parameters and principles
that make an agent-generated knowledge bundle *auditable* rather than merely
plausible. flip's tooling enforces them; any producer can honor them without
flip.

1. **Capture before cite.** A concept page may only cite what the bundle has
   custody of (a `references/` page backed by raw bytes and a provenance
   event) — or the citation is visibly dangling (legal in OKF; `flip doctor`
   counts them).
2. **Judgment is explicit and separate from capture.** Grading a source is a
   recorded act by a named actor; capture-time defaults confer nothing.
3. **Claims carry status.** Machine-generated assertions enter as `asserted`;
   `verified` is gated by the profile's corroboration bar, mechanically.
4. **Generation is logged.** Every LLM/tool episode that wrote pages gets a
   session page (§8): actor, model, tools, goal, outputs. The reasoning chain
   is part of the bundle.
5. **Events append, views regenerate.** History lives in append-only JSONL;
   `index.md` bodies and `log.md` are disposable projections of it.
6. **Unknown keys survive.** Any tool editing a page preserves frontmatter it
   doesn't understand (OKF's consumer rule, applied to writers).
7. **Attribution everywhere.** Every event and every entity page records its
   `actor` (`human:<name>` / `agent:<name>`).
8. **Renders are never edited.** Fixes flow to the notebook and re-render.

Extension vocabulary summary — flip's frontmatter keys beyond OKF's
(`type`/`title`/`description`/`resource`/`tags`/`timestamp`): `id`,
`aliases`, `actor`, `grade`, `independence`, `freshness`, `status`, `local`,
`sha256` (on export), `date`, `authors`, `publisher`, `load_bearing`,
`sources`, `supports`, `independent_corroboration`, `first_asserted`,
`question`, `alternatives_rejected`, `model`, `tools`, `started`, `ended`.
OKF consumers must preserve and may ignore all of them.

## 7. Claims — `claims/<slug>.md`

```markdown
---
type: Claim
id: C7
aliases: [C7]
description: "AI retail traffic converts ~42% better than non-AI"
status: needs-2nd
load_bearing: true
sources: [A12]
supports: [/references/single-vendor-conversion-study]
independent_corroboration: 1
first_asserted: 2026-07-09
actor: agent:claude
---
AI retail traffic converts ~42% better than non-AI.

_Single vendor study; seek platform data or a second measurement._

# Citations
[1] [Single-vendor conversion study](../references/single-vendor-conversion-study.md)
```

`status`: `asserted` → `verified` | `needs-2nd` | `unconfirmed` |
`false-positive` | `retracted` | `superseded`. A claim is `verified` only
with the corroboration its profile demands (default: two independent
sources or one grade-A primary), counting only judged sources.
`independent_corroboration` is stored for consumers but recomputed by the
tooling — doctor flags drift. `sources` holds ids (machine-stable);
`supports` holds bundle paths (OKF-traversable); the `# Citations` block is
the human/agent-readable edge list. Fine-grained span anchoring may use W3C
Web Annotation selectors; optional.

Decisions and questions follow the same shape: `decisions/<slug>.md`
(`type: Decision` — `question`, decision text, why, `alternatives_rejected`)
and `questions/<slug>.md` (`type: Question` — `status: open | answered`,
answered pages keep their history in git).

## 8. Logs — events, sessions, views

- **`log/log.jsonl`** (append-only) — the work log: fetched X, ran Y, hit
  wall Z. `{ts, text, actor}`, one per line. **`log.md`** at the bundle root
  is its generated, newest-first OKF view.
- **`log/passed.jsonl`** (append-only) — negative evidence: considered and
  rejected, with reason. Prevents rediscovery loops.
- **`sessions/<stamp>-<slug>.md`** — one entity page per working episode
  (`type: Work Session`; frontmatter: `actor`, `model`, `tools`, `started`,
  `ended`): the goal, the prompt (or pointer), key outputs, pointer to the
  raw transcript when kept. LLM synthesis recorded here is a **lead**, grade
  `C`, until promoted through `references/`.
- Provenance and derivation ledgers stay under `sources/` and `derived/`
  (§5.2, and `derived/_derivations.jsonl` records inputs → tool/cmd/params →
  outputs with hashes, a deliberately small PROV profile).

## 9. IDs, filenames, and links

- Every entity has a compact, immutable id in frontmatter: `P#/A#/F#/T#/S#`
  sources (papers / articles / files-datasets / talks / unkinded) · `C#`
  claims · `D#` decisions · `Q#` questions · `H#` hypotheses. Prefixes are
  disjoint, so a bare `[A3]` or `[D2]` cite is unambiguous. Ids are never
  reused, even after retraction.
- **Filenames are slugs; ids resolve through frontmatter.** Prose cites ids
  in brackets (`[A3]`, `[C7]`) — greppable both directions; `flip open A3`
  and any frontmatter scan resolve them. **Honest aliases:** `aliases:
  [<id>]` feeds Obsidian-style autocomplete — typing `[[A3` suggests the
  page — but does not make a raw `[[A3]]` resolve on its own (those editors
  resolve paths and filenames, not aliases). `flip doctor` says exactly
  this when an alias is missing.
- flip-generated links are **relative markdown links** (`../references/
  <slug>.md`) — valid OKF edges that also resolve in Obsidian, GitHub, and
  every markdown renderer. Humans may write `[[wikilinks]]` in prose bodies;
  they're inert text to OKF consumers and flip treats them as prose, not
  edges.
- `flip rename <id> <new-slug>` is the only sanctioned rename: it moves the
  file and rewrites every relative link and listing entry notebook-wide.
- **Cross-notebook references are `<handle>:<id>`** (`recipes:A3`), where
  the handle is a name *you* bound in the enclosing workspace table (§18) —
  not the notebook's slug, though the slug is the default suggestion.
  Resolution is exact and loud (`flip resolve`, `flip open`): a bare id
  resolves within the containing notebook; `handle:id` resolves through the
  nearest workspace table; unknown handles and unknown ids are errors,
  never guesses. One sanctioned extension: a bare id used under a workspace
  root but outside any notebook resolves iff exactly one bound notebook
  carries it — ambiguity is an error listing the qualified forms to use.
- **`#` as the ref separator is deprecated** (the pre-0.5 form,
  `<notebook-slug>#<id>`): readers still accept `handle#id` with a warning;
  writers emit only `:`; `flip migrate` rewrites stored `#` refs. `#` reads
  are removed in flip 0.10.
- Binding a notebook also adds **qualified aliases** (`recipes:A3`) to its
  entity pages, right after the bare id, so workspace-wide autocomplete can
  disambiguate (§18). Same honesty rule as above: aliases suggest, they
  don't resolve raw wikilinks.

## 10. Views

Views are computed, never canonical: `flip show` assembles the hot view
(open questions, claims needing corroboration, stale sources, recent log,
latest session) from pages and ledgers; `index.md` bodies and `log.md` are
their at-rest equivalents, regenerated by flip on every mutating command.
Nothing is deleted to keep context small — hot vs cold is a projection.

## 11. Renders and drafts

- Drafts are versioned explicitly: `drafts/v0/`, `drafts/v1/`, `current`
  symlink; each version carries a `changelog.md` naming what changed and
  which finding/decision drove it.
- Renderers are pure: same notebook in, same render out; they write only to
  `renders/<target>/` and never mutate the notebook.
- Whether `renders/` is committed is a policy decision; default gitignored.

## 12. Working with humans (the Obsidian criterion)

Success for flip is humans and agents collaborating gracefully **in the same
files**. The format is designed so a vanilla markdown knowledge tool —
Obsidian is the reference case — is already a first-class flip client:

- Frontmatter renders as Obsidian **Properties**; a human re-grading a
  source in the properties panel is a legitimate flip operation, validated
  by the next `flip doctor` run.
- `aliases` feed id autocomplete (typing `[[A3` suggests the page — §9);
  relative links light up the graph view; the folder taxonomy (references /
  claims / decisions / questions / sessions) reads as intended structure.
- flip must **round-trip foreign formatting**: editors rewrite YAML styling;
  flip preserves key order where it can, unknown keys always, and never
  fights over whitespace.
- `.obsidian/` (and editor config generally) is local state: gitignored,
  never required, never read by flip.
- Roadmap, not requirement: a thin Obsidian plugin surfacing what vanilla
  properties can't — verification-bar status, corroboration counts, dangling
  citations, doctor findings inline — driven by `flip show --json` /
  `flip doctor --json`.

## 13. Profiles

A profile = required files + notebook.md sections + claim-verification bar.
Everything else is optional everywhere.

| profile | intent | requires beyond core |
|---|---|---|
| `ledger` | bibliography / source spine | references/ |
| `scout` | screen an angle fast, editor lens active | hypotheses w/ falsifiers per query · decisions/ · log/passed.jsonl |
| `research-review` | question-organized survey → publishable | claims/ · sessions/ · drafts/ · full custody · workflow journal |
| `engagement` | confidential client work | research-review + `client-confidential` policy + citation rule enforced + HANDOFF.md |
| `data-investigation` | dataset-first reporting | derived/_derivations.jsonl · ingest scripts · frozen data contracts |

Profiles are data (TOML shipped with flip; notebook-local `.flip/profiles/`
overrides), selected by `kind` in the manifest. Profile minimums are
**completion requirements, not creation requirements**: missing paths WARN
while status is `active`/`dormant` and ERROR once `done`/`published`/
`archived`. The notebook.md **section menu** (scaffolded by kind, sections
graduate to their own files when they outgrow a heading): *the tip · frame ·
what the data can/can't say · hypotheses & falsifiers · sources & provenance
· priors ledger · decisions · what's not in the piece · workflow notes ·
gaps & self-critique · handoff*. Conventions that earned their place:
hypotheses set before looking, each with a named falsifier and a
"what survived" audit; dated log entries newest-first recording walls and
pivots; a working thesis rewritten as evidence lands, version-marked.

## 14. Beats — the grouping layer above notebooks

A **beat** is a standing mission that outlives any single notebook: "school
funding in this county." *A beat contains many notebooks* — scouts that
died, reviews that published, investigations in flight — and holds the
cross-notebook memory that makes the eleventh notebook cheaper than the
first. A beat is itself an OKF bundle; same grammar as a notebook, different
state:

```text
<beat>/
  index.md                 # beat manifest frontmatter (flip_beat: "0.1",
                           #   slug, mission, status, cadence) + generated listing
  beat.md                  # prose working memory (type: Beat): the mission,
                           #   standing sources, what "covered" means here
  threads/<slug>.md        # type: Thread — one page per thread (+ generated index.md)
  log/log.jsonl            # append-only beat work log (log.md generated view)
  coverage.jsonl           # append-only: one event per notebook outcome or
                           #   coverage-relevant act {ts, thread, notebook?, note, actor}
  notebooks/<slug>/        # child notebooks (default home; a thread page may
                           #   point anywhere via its `notebook` key)
```

**Threads** are the beat's unit of attention — an entity page like any
other (`id: TH#`, `aliases`), in two kinds: **arc** (a self-initiated
investigation pulled over time) and **vein** (a recurring story-type
monitored reactively). Frontmatter: `kind: arc | vein`, `status: open |
active | dormant | done | dropped`, `scores` (see below), `notebook:
<slug>` once graduated, `next_review: <date>` for dormancy. The body is the
thread's running rationale.

**Triage is computed, not stored.** `flip beat show` ranks open/active
threads by a weighted sum of five 0–1 scores in frontmatter — `payoff`
(what it's worth if it lands), `access` (can we actually get the material),
`urgency` (does it decay), `connection` (does it compound other threads),
`uniqueness` (would anyone else do it) — with default weights
.30/.25/.20/.15/.10, overridable in the beat manifest (`weights:`). A
missing score reads as 0.5; ranking never mutates pages.

**Graduation is the beat's core act**: `flip beat graduate TH3 <slug>
--kind scout` creates a notebook (scaffolded per §13) under `notebooks/`,
stamps the thread `status: active` + `notebook: <slug>`, links the notebook
manifest back (`links: {beat: "<beat-slug>:TH3"}` — the canonical `:`
separator; pre-0.5 `#` links are still read, with a doctor WARN, until 0.10;
`flip migrate` rewrites them), and appends a coverage event. Kill decisions are first-class too: `flip beat thread drop TH3
--reason …` records why in the page and the coverage ledger — negative
coverage prevents re-scouting dead angles.

A beat root is distinguishable from a notebook root (`flip_beat:` vs
`flip:` in the index frontmatter); notebook commands inside a child
notebook resolve to the notebook, `flip beat …` commands walk up to the
beat. In a workspace (§18), handles bind *notebooks* only — a beat root is
not bindable, but workspace discovery walks through it to the real
notebooks under `notebooks/`. Beat-level doctor, saturation warnings ("this
well is over-visited"), and richer coverage roll-ups are future work (§19).

## 15. Tooling — the flip CLI

Small, boring, filesystem-only core; **no network calls and no LLM calls in
the library**. Fetchers are pluggable externals. Dependencies: click, PyYAML
(reading human/editor-authored frontmatter faithfully outweighs dependency
purity; flip's own writer emits a deterministic strict subset).

```text
flip config init                     # write a starter config.toml (bundled flip-fetch web lane)
flip new <slug> --kind <profile>     # scaffold manifest + notebook.md
flip add-source <url|doi|file|->     # capture: fetch/copy → raw/, hash, provenance,
                                     #   open a references/ page at grade "?" (--via <variant>)
flip find "<question>"               # research: list candidate leads (--capture <n>)
flip ask "<question>"                # research: cited synthesis → sessions/raw/ (a grade-C lead)
flip recall "<question>"             # knowledge: read what we already hold locally
flip grade <id> …                    # record judgment on a source page
flip log "<text>"                    # append a work-log event (+ regen log.md)
flip decide|pass|question …          # decisions/questions pages; passed ledger
flip claim add|status|list …         # claims pages; verification bar enforced
flip session start|end …             # session pages
flip show [--hot|--claims|--stale]   # computed views (--json for agents)
flip open <ref>                      # resolve a ref (A3, recipes:A3) to its page path
flip resolve <ref> [--json]          # same resolution with provenance: id, handle,
                                     #   path, notebook root/slug, uid, title (§9)
flip rename <id> <new-slug>          # move a page + rewrite links notebook-wide
flip ws init|list|add|rename|rm      # workspace table: bind handles to notebooks (§18)
flip import <src> [--as <handle>]    # bring a shared notebook / okf export / bag
            [--into <dir>]           #   into the workspace under a handle you own;
            [--update <handle>]      #   --update = replace-if-uid-matches (§17)
flip doctor [--json]                 # lint: conformance, profile minimums, orphan
                                     #   custody, under-verified claims, id/alias
                                     #   integrity, link rot, foreign-edit drift
flip doctor --workspace [--fix]      # lint the shared space instead (§18); --fix
                                     #   binds strays, backfills uids, regens aliases
flip index                           # per-user registry (~/.flip/index.jsonl)
flip migrate                         # v0.3 ledgers → pages; 0.4 → 0.5 (mint uid,
                                     #   links.beat '#' → ':')
flip export bag|csl|okf|ro-crate     # projections (§17)
```

### Integration roles (pluggable externals)

flip shells out to external tools through a small set of **roles**, each a
namespaced table in `~/.flip/config.toml` and a thin command protocol. flip
defines the protocol; the tools that fill a role live only in user
configuration, never in the package. Placeholders: `{url}` the target as
given · `{id}` the target with a leading `doi:` stripped · `{query}` a
research/recall question · `{dest}` the capture directory. Commands that write
files receive `{dest}`; stdout-only commands may omit it and their stdout is
preserved. The library makes **no network or LLM calls itself** — it only runs
what you configure.

- **`[fetchers]` — capture.** A target (`url`/`id`/`file`) → local bytes +
  custody. `flip add-source` routes by kind. `builtin:copy` (local files) and
  the bundled `flip-fetch` (a stdlib web GET) are the only shipped capture
  helpers — `flip config init` writes a starter config that wires `flip-fetch`
  to the `web` lane, so capture works with no external tool; everything else is
  operator-configured.
  A key's value may be a bare command string, an inline table
  (`{ cmd = "…", needs = [...] }`), or a table of named variants selectable with
  `--via <name>`. X/Twitter post URLs classify as `social` so a
  cookie-authenticated lane can preserve them separately from the ordinary
  `web` fetcher. Whatever runs, the tool, best-effort version, and strategy land
  in `_provenance.jsonl` automatically — principle 9 costs nothing when the tool
  does it.
- **`[research]` — acquire.** A *question* → candidate leads (`flip find`) or
  cited synthesis (`flip ask`). Synthesis is a **lead, grade C, not evidence**:
  its raw output lands under `sessions/raw/` for custody and a log breadcrumb is
  written, but its cited URLs become sources only when captured with
  `flip add-source`. This role never opens a `references/` page on its own.
- **`[knowledge]` — recall.** A *question* → what the deployment already holds
  locally (`flip recall`). Read-only; lands nothing unless `--record`.

#### Return envelope (optional, capture only)

A fetcher may hand structured knowledge back to flip by emitting a `flip.json`
sidecar in `{dest}` — or a JSON stdout capture — carrying a top-level `flip`
object. flip harvests its neutral, **all-optional** keys and drops the rest:
`title`, `canonical_url`, `retrieved_at`, `strategy`, `status`, `mime`,
`from_cache` (True when served from a shared store rather than freshly fetched),
`sub_resources`, `backend_ref` (opaque store/corpus id, passed through to
provenance), and `independence_hint` / `freshness_hint`. Title and canonical URL
flow onto the page; strategy/retrieved_at/status/mime/from_cache/backend_ref into
provenance. **Hints are recorded as a page note, never the grade** — grading
stays a judgment made after reading (SPEC §5.4). An absent envelope changes
nothing; a strict producer, a tolerant consumer.

This is how a shared blob/archive store plugs in without flip knowing it exists:
a capture command may check the store first and, on a hit, serve the stored
bytes (still writing the mandatory local copy) with `from_cache: true` and
`backend_ref` set — the store id rides *alongside* local custody (§16), and
nothing is re-fetched.

### The registry

`flip index` scans configured roots and writes `~/.flip/index.jsonl` — a
plain file, built by scanning, no service. One row per notebook (path,
slug, `uid`, kind, status, updated, title); a directory carrying
`.flip/workspace.toml` adds one workspace row (`{"path", "workspace":
true, "notebooks": {handle: relpath}}`). Anything richer consumes this
file; flip has no reverse dependency.

### Skills (the encouragement layer)

Shipped as plain `SKILL.md` files usable by any agent runtime (and declared
as a spindle package): `notebook-create`, `notebook-source`, `notebook-log`,
`notebook-audit`, `notebook-handoff`, `notebook-lessons` — procedural
checklists that make the §6 lineage rules habitual.

## 16. Integration contract

A notebook must remain intelligible from its local files alone; integrations
are referenced, never required, and never proprietary-by-design.

The public distribution specifies integration roles and the fetcher
placeholder protocol only. Site-specific command names, defaults, and
operational guidance belong in user-owned configuration or a separate private
integration repository; they are not part of flip's public source, package,
documentation, or portable skills.

| role | how referenced |
|---|---|
| capture tools (web, papers, media) | `[fetchers]` config + `tool`/`strategy` in provenance; optional return envelope enriches the page |
| research multiplexers / SERP tools | `[research]` config (`find`/`ask`); candidate leads for `add-source`; synthesis raw → `sessions/raw/`, a grade-`C` lead promoted via `references/` only when captured |
| local knowledge / retrieval corpora | `[knowledge]` config (`recall`); read-only; `links:` in the manifest for durable cross-refs |
| knowledge graphs / lead trackers | `links:`; cross-refs by id |
| shared blob/archive stores | a capture command serves stored bytes on a hit; the envelope's `from_cache` + `backend_ref` land in provenance **alongside** the mandatory local copy — no re-fetch |
| render targets | renderer reads the notebook, writes `renders/<target>/` |
| OKF consumers (visualizers, catalogs, editors, other agents) | read the notebook directly — it is a bundle; strict-producer/tolerant-consumer |
| registries / task systems | consume `~/.flip/index.jsonl`; no reverse dependency |

## 17. Exports (generated projections)

- **`flip export okf <dest>`** — now a **policy filter**, not a format
  transform: copy the bundle for outside consumption, honoring `visibility`
  (refuse unless `public` or `--include-private`) and `source_trail_public`
  (strip custody detail to judgment stubs), with `--announce` writing an
  OpenWiki-style `<!-- FLIP:START/END -->` marker block into a host repo's
  AGENTS.md. Never write into an `openwiki/` directory — coexist beside it;
  OpenWiki documents the code, flip documents the investigation.
- **BagIt** bag for cold archival (`flip export bag`).
- **CSL JSON** from references for citation managers (`flip export csl`).
- **RO-Crate** envelope, **W3C Web Annotation** anchors: future projections.

### What travels, and import

Identity travels with the bundle; local state does not. `uid` and `origin`
ride in the root `index.md` frontmatter, so every export and bag carries
them; `.flip/` (id reservations, the workspace table) and workspace handles
never ship — the receiving side chooses its own handle.

**`flip import <src>`** is the reverse projection: bring a shared notebook
into the enclosing workspace (§18) from a notebook directory, an OKF export
(`flip export okf` output), or a BagIt bag (payload `data/`; fixity is not
re-verified on import — validate the bag first if you care). The copy lands
under the workspace, binds to a handle you own (`--as`, default the
bundle's slug; `--into` picks the directory), and records provenance:
`origin` is stamped with the source and date, and a `uid` is minted only
when the source predates uids. **Entity ids are never rekeyed** — citations
inside the bundle stay valid, and your own notes reference it as
`handle:id`. `--update <handle>` is replace-if-uid-matches: the same
lineage refreshes in place (local `.flip/` id reservations survive);
anything else refuses — merging diverged copies is out of scope. The
source must be a separate directory: a src that is, contains, or lives
inside the bound copy is refused before anything is touched.

## 18. Workspaces — many notebooks, one root

A **workspace** is a directory (an Obsidian vault, a repo, a research
share) holding many notebooks. Its root carries `.flip/workspace.toml`:

```toml
# flip workspace table — maintained by `flip ws`; hand edits are read but
# comments are not preserved on rewrite.

[workspace]
version = "0.1"

[notebooks]
gardening = "plots/gardening-notes"
recipes = "recipes"
```

Two tables of scalars, nothing else: `[workspace].version` and
`[notebooks]` mapping **handle → workspace-relative posix path**. flip
reads it with a real TOML parser (hand edits are fine) and rewrites it
deterministically (sorted handles, JSON-escaped paths, comments not
preserved).

**Handles are importer-owned petnames** — the same model as git remote
names. The notebook's manifest slug is only the default suggestion
(collisions get `-2`, `-3`); the binding is yours, lives only in your
table, and never ships with the bundle (§17). Handle syntax is
deliberately narrower than slugs — `^[a-z][a-z0-9-]*$`, always a TOML bare
key, always unambiguous before the `:` in a ref (§9).

**The `flip ws` commands** maintain the table:

- `flip ws init` — declare the *current directory* a workspace root (no
  walk-up; refuses if the table exists or the cwd is itself a notebook
  root), scan below for notebooks, and bind each under its slug.
  Discovery is bounded: dot-dirs and export copies (BagIt bags, OKF
  exports) are pruned, a notebook inside a notebook is counted once, and
  beat roots are walked *through* to the notebooks under `notebooks/` —
  handles bind notebooks only (§14).
- `flip ws add <path> [--as <handle>]` / `flip ws rm <handle>` — bind one
  notebook already on disk / unbind a handle. `rm` never deletes files;
  it removes the binding and that handle's qualified aliases.
- `flip ws rename <old> <new>` — rebind, then rewrite `old:ID` refs
  workspace-wide: prose cites, wikilinks, link labels, and frontmatter
  values, mechanically anchored so `other-old:A3` and `old:notafile.md`
  are never touched. Captured bytes (`sources/`, `derived/`, `renders/`),
  export copies, and fenced code blocks are never edited (inline code
  spans are an accepted limitation); `links.beat` is protected
  structurally (a beat slug is not a workspace handle).
- `flip ws list [--json]` — the bound rows: handle, path, slug, uid,
  title, status (`ok` / `missing` / `not-a-notebook`).

**Alias maintenance.** Every bind, rename, unbind, and import keeps entity
pages' `aliases` honest: the bare id always present, the qualified
`handle:id` right after it when bound, stale handles' qualified aliases
removed. Foreign aliases and all other frontmatter survive verbatim; pages
are rewritten only when the alias list actually changed.

**Workspace doctor.** `flip doctor --workspace` (implied when run under a
workspace root outside any notebook) lints the shared space and exits 1 on
ERRORs: `bad-workspace-file` (unparseable table — duplicate handles are a
TOML parse error and surface here), `handle-syntax`,
`dangling-workspace-entry` (path missing or not a notebook) — ERRORs;
`missing-uid`, `duplicate-uid` (same lineage bound twice),
`unregistered-notebook` (on disk but not in the table), `stale-alias` (a
qualified alias whose handle no table binds to the notebook — handles from
an enclosing or nested workspace's table are legitimate, never stale), and
the aggregated informational pair `ambiguous-id` / `slug-collision` (bare
ids or filename stems living in ≥ 2 bound notebooks) — WARNs.
`--fix` (workspace mode only) binds unregistered notebooks, backfills
missing uids, and regenerates qualified aliases; it never edits a broken
table.

Inside any single notebook, nothing changes: bare ids, `flip doctor`,
and every notebook command behave identically whether or not a workspace
exists above.

## 19. Open questions

- **Profile tunables** — which fields are per-profile-tunable vs fixed?
- **Beat layer, phase 2** — beat-level doctor; saturation warnings over
  coverage.jsonl; cross-beat lessons roll-up; when a thread *must* graduate
  (today it's judgment; should high-score staleness force the question?).
- **OKF profile standing** — whether flip's extension vocabulary should be
  proposed upstream (the W3C Holon CG is exploring formal-semantics
  profiles; OKF v0.1 has no provenance scheme, and flip has a worked one).
- **Obsidian plugin** — thin metadata surface over `flip … --json` (§12).
- **OCR/transcript quality provenance**; **corroboration graph** (shared
  upstream origins detected); **migration adapters** for pre-flip notebook
  corpora.
