# flip — the reporter's notebook format

**Status:** draft v0.20 · 2026-08-18
**What this is:** a spec for a consistent, pluggable, git-friendly format for
reporter's-notebook-style research corpora created and maintained by any mix of
humans and agents — plus the tooling and skills that encourage proper use.

flip is the tooling; the **notebook** is the artifact. A notebook is a mostly
inert storage-and-retrieval scheme: plain files, no live service required to
read or trust it. Everything a downstream human or agent needs to understand
the trajectory of a piece of research lives in the notebook.

As of v0.4, **a flip notebook is a conformant
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
(OKF v0.2) knowledge bundle at rest** — not an export target. flip is an
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
  forecasts/<slug>.md      # type: Forecast (FC#) / Cluster (CL#) — §7
  sessions/                # type: Work Session — one page per episode
    <UTC stamp>-<slug>.md
  analysis/                # graduated prose: hypotheses.md, findings.md, …
                           #   (concept pages: any type fits)
  evaluation/              # non-entity working files: harnesses, scoring runs,
                           #   checks — never entity pages, no frontmatter owed
  sources/
    raw/                   # verbatim bytes as captured (non-md; OKF-unconstrained)
    text/                  # readable derivatives of raw/, 1:1 by source id
                           #   `<source id>.txt`, written by `flip extract` (§5.5);
                           #   overwritable, because every write is logged
    _provenance.jsonl      # append-only capture log: who/what/when/how/sha256
  derived/
    _derivations.jsonl     # append-only processing log: inputs -> tool/cmd/method
                           #   -> outputs, with hashes both sides (§5.5)
    ...                    # parsed tables, transcripts, extractions
  log/
    log.jsonl              # append-only work log (one event per line)
    passed.jsonl           # negative evidence: considered and rejected
  drafts/                  # versioned drafts: v0/, v1/, current -> vN
  renders/                 # generated downstream artifacts (gitignored by default)
  HANDOFF.md               # cold-start resume view (graduates from notebook.md)
  NEXT_STEPS.md            # optional: forward-looking work, bounded prose
  lessons.md               # end-of-life distillation, for other notebooks
```

Only `index.md` and `notebook.md` are universally required; profiles (§13)
define the rest. Directories appear when first needed.

**OKF conformance:** every non-reserved `.md` file carries frontmatter with a
`type`; `index.md` and `log.md` follow OKF's reserved-file structures;
everything under `sources/raw/`, `derived/`, and the `_*.jsonl` ledgers is
non-markdown sidecar content, which OKF explicitly leaves unconstrained.

### notebook.md — working memory is synthesis

Working memory means **prose**: the current understanding, the live tensions,
what changed and why — thought written down, not records copied over.
Ledgered entities are cited by id (`[A3]`, `[C7]`, `[D2]`) and never
re-listed in notebook.md: the pages are canonical and one `flip open` away,
the generated listings already exist (§10), and a copy starts drifting from
its original the moment either moves. The failure mode is real and expensive:
a measured notebook.md reached 63.5 KB by duplicating 25 decision pages and
301 reference listings into its own body — an index wearing the costume of
thought, charging every reader (agents most of all) the whole ledger's tokens
on every open while saying nothing the ledgers didn't. `flip doctor` warns
once notebook.md passes 24 KB, because past that size the file has almost
certainly stopped being synthesis.

### NEXT_STEPS.md — forward-looking work, recognized

`NEXT_STEPS.md` is an optional root file for forward-looking work: bounded
prose about what to do next — open moves, priorities, parked intentions, in
the operator's own order. It entered the spec by observation, not design: in
seven independent autonomous runs over real notebooks, all seven invented
exactly this file, while the spec'd HANDOFF.md appeared in three of seven.
When every run routes around the spec in the same direction, the hole is in
the spec. The two files answer different questions and do not merge:
**HANDOFF.md remains the cold-pickup surface** — where things stand, for a
reader arriving cold — and may point at NEXT_STEPS.md for what to do about
it. Like notebook.md, it is synthesis that cites ids and re-lists nothing.

`evaluation/` is recognized on the same evidence: a **non-entity working
directory** alongside `analysis/` for harnesses, scoring runs, and checks.
The distinction is the point — `analysis/` holds concept pages (typed
frontmatter, H# ids resolve there), while files under `evaluation/` are
working material: no frontmatter is owed, doctor does not read them as
concept pages, and no listing is generated over them.

### Naming rules

- **Entity filenames are human slugs, not ids**: `references/
  lecun-jepa-keynote.md`, `claims/ai-traffic-converts-42pct.md`. The stable
  id lives in frontmatter (§9). Slugs are `^[a-z0-9][a-z0-9-]*$`, derived
  from the title/text at creation. A collision takes the id-qualified form
  (`a261-index`) rather than a counter, because a counter names nothing —
  one measured corpus held eight distinct sources whose entire slug identity
  was `index-3` … `index-10`; a bare counter remains the fallback where no id
  is available, and existing counter-suffixed files stay valid. `flip rename`
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
okf_version: "0.2"
flip: "0.9"                 # flip profile version this notebook conforms to
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
  the extracted-text derivative in `sources/text/` (§5.5). PDFs and datasets:
  the original file. API pulls: the verbatim response JSON.
- Once captured, a raw file is immutable; recapture creates a new dated
  entry, it does not overwrite.
- **The envelope carries metadata; a document lands as its own file.** A
  capture tool that hands document bytes back inside a JSON string field has
  packed a payload where metadata goes, and the mistake compounds: JSON
  escaping inflates the bytes ~2.5×, and the "text derivative" of the wrapper
  is mojibake (measured: 627 MB of PDF bytes escaped into JSON strings across
  one corpus, one 104 MB `capture.json` wrapping a 41.6 MB PDF). flip
  materializes such payloads to their own file **at capture time, before
  provenance is written**, so every recorded hash reflects what actually
  landed in custody; a payload whose bytes were already lost to a lossy
  decode upstream is left in place as evidence rather than corrupted further,
  for doctor to name.

**Capture methods — the ladder.** `strategy` in the capture log records *how*
the bytes were obtained, from a fixed vocabulary; the *actor* is already
recorded separately as `tool`/`tool_version`. Recording the method is what
makes two notebooks comparable when they were built on different deployments:
`archive-replay` means the same thing whoever implemented it, while a tool
name is local trivia. In escalation order:

| method | the bytes came from |
|---|---|
| `copy` | a local file, copied verbatim |
| `http-get` | a plain GET of the live URL |
| `http-alt-representation` | a canonical/print/embed variant of the same URL |
| `archive-replay` | a third-party web archive |
| `publisher-api` | a publisher or registry API (Crossref, Unpaywall, arXiv…) |
| `media-extract` | a media/transcript extractor |
| `browser-render` | a headless browser that executed the page |
| `browser-session` | a browser render carrying an authenticated session |
| `self-contained-archive` | one standalone file with assets inlined |
| `human-in-loop` | a person saved it and handed flip the file |
| `record-only` | nowhere — the document was out of reach; custody holds flip's own record of the source and of the attempt |

Two of these carry facts the method itself establishes. `archive-replay`
records **`archived_at`** — the snapshot's date, which is when the evidence is
from and is not when it was retrieved; a claim resting on an archived page
rests on the page as it was that day, and grading should say so. A
`publisher-api` capture that reached only a registry record, not the full
text, records **`status: metadata-only`**: the record is worth keeping and is
not the document, so it derives `thin` fidelity rather than passing as the
article.

**The order is a ladder, and a refusal is where the work starts.** A 403 is a
decision about *this* request, not a verdict on the source: the rungs above it
exist precisely for that case, and an acquisition that stops at the first one
has not established that the source is unavailable — only that one method
didn't work. Statuses that mean *later, not never* (429, 502, 503, 504,
timeouts) get backoff-retry on the same rung; a 403/404 does not, because
repeating an unchanged request that was refused is noise. When the ladder is
genuinely exhausted, that is a finding: `flip pass` records it, and a failed
acquisition writes its own capture-log row, so "searched, gone" stays
distinguishable from "did not look".

**An empty-handed capture tool is reporting, not malfunctioning.** A configured
command that exits 0 having written nothing has said something specific: at
this rung, for this target, there was nothing to capture. That is a finding
about the *document* — gated, withdrawn, not served to us — and it is not the
same event as a command that could not run or exited nonzero. An implementation
must not present the first as a configuration defect: doing so points the
reader at a config that is fine, and the predictable result is that they
abandon the configured tooling and improvise an acquisition with no custody, no
hash, and no record of what was tried. What it must do instead is name the
moves that remain: the rungs above, the lanes the operator has actually
configured (the only tooling flip is permitted to know about — §16), the record
capture below, and `flip pass`.

**`record-only` — the ladder's terminus, written down.** A source that cannot
be captured may still have to be *citable*: named, given an id, and pointed at.
A record capture takes no bytes of the document, because none were reachable;
what enters custody is flip's own record of the source and of the attempt,
which must carry a note saying what was tried and what each rung returned. It
is not a rung anything climbs *to* — it is where the work stands when the
ladder ran out. It always derives `thin` fidelity whatever the record weighs,
its page opens at grade `?` (so it corroborates nothing), and the page says
above the fold that the document is not in custody. A later capture of the
document supersedes it. `flip pass` remains the move for a source ruled *out*;
a record is for one that is real, wanted, and out of reach.

**Acquisition conduct — a default stance, not a constraint.** flip's own
tooling ships one opinion about how to fetch. It is a starting position chosen
for the common case, and every part of it is configurable by the operator, who
owns the result. flip does not enforce a conduct policy and does not try to.

The default assumes *closely directed* capture: a named document a person or
their agent is about to read, judge, and cite — an extension of manual effort
rather than crawling. From that assumption:

- **A User-Agent is a compatibility hint, not an access control.** The default
  presents a browser string. Blanket UA blocking is a blunt platform default
  aimed at bulk scrapers, and directed single-document capture is bycatch in
  that fight; the string has been negotiated fiction since browsers began
  claiming to be `Mozilla/5.0`.
- **Conduct is judged by volume and access, not by self-description.** The
  default fetches one named document, follows no links, and paces per host.
- **Higher rungs are unimplemented, not forbidden.** Authenticated capture is
  a first-class method (`browser-session`) for material you have legitimate
  access to — a subscription, an institutional login, your own systems.

A deployment with different needs — announcing itself to a partner API, pacing
far slower for a fragile host, moving faster against its own infrastructure —
changes the policy and takes responsibility for it. That is the operator's
call, not the format's.

**What does not vary is the record.** `user_agent`, `strategy` and `attempts`
are written to the capture row as they were actually used, whatever the policy
was. This is not a restriction on conduct; it is what the format is *for*. A
notebook that misreported how its bytes were obtained would be worthless to
whoever later has to trust it — most often its own author. An implementation
may fetch however its operator decides; it may not misdescribe what it did.

Custody is also **not** republication: holding a copy for citation says
nothing about the right to redistribute the bytes, which
`policy.source_trail_public` and the export filters govern separately (§17).

**Fidelity is derived, never stored** — like the source grade (§5.4). From the
method plus the recorded size and mime: `faithful` (assets inlined, rendered,
or a verbatim copy) · `text-only` (the document's text, linked assets not
captured) · `thin` (succeeded and brought back almost nothing — a consent
wall, a JS shell, an error page served as 200) · `unknown` (no method, or one
outside the vocabulary). `thin` is the one that matters: custody, a sha256 and
a capture row all look identical to a real capture, so doctor names it rather
than leaving a reader to notice.

### 5.2 The capture log — `sources/_provenance.jsonl` (append-only)

One line per acquisition event:

```json
{"ts":"2026-07-09T14:31:02Z","source_id":"A3","url":"https://…","url_used":"https://…",
 "local_path":"sources/raw/A3/page.html","sha256":"…","bytes":48210,"http_status":200,
 "tool":"single-file","tool_version":"1.22","strategy":"self-contained-archive",
 "attempts":2,"actor":"agent:claude",
 "note":"index page lied; probed URL pattern directly"}
```

This is the fixity record — hash at capture, per file. `flip export bag`
emits a real BagIt bag for cold archival.

Rows for acquisitions that landed **no bytes** carry no `sha256` and have no
entity page, by design — the row *is* the finding — and `status` says which
kind of nothing happened:

| `status` | what it records |
|---|---|
| `failed` | the command could not run, or exited nonzero — a broken toolchain |
| `not-captured` | the command ran clean and found nothing — a fact about the document |

Consumers that walk the ledger looking for captures skip both; doctor does not
read either as a missing page.

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
independence: independent
support:
  basis: measured
  method: "verbatim transcript, timestamped against the recording"
freshness: fresh
status: captured
---
# LeCun keynote, Global AI Frontiers Symposium

Capture notes, pull-quotes, misgivings — anything a reader of this source
should know before trusting it.
```

`aliases` always contains the id, so typing `[[A3` suggests this page in
wikilink-aware editors while the filename stays readable (§9 on what aliases
honestly buy). `status: captured` says bytes of the source are in custody; a
**record capture** (§5.1) writes `status: recorded` instead and says so in the
body, because what is held is the record of a source, not the source.

### 5.4 Source-quality model — the support tuple

Judgment is a *description of the evidence*, not a letter (v0.8, after the
principle "a grade is a summary, never a store"). Grading a source records
the **support tuple** on its page:

| key | values / meaning |
|---|---|
| `independence` | the tuple's spine, required to be judged: `independent` (third party, own collection) · `corroborated` (matches other independent evidence) · `self-reported` (the subject on itself) · `derivative` (republishes another source — a lead, never provenance) |
| `support.basis` | what kind of evidence: `official-record` · `platform-data` · `measured` · `survey` · `panel` · `single-operator` · `synthesis` (incl. LLM output) · `spoken-management-remarks` (exists only in speech — cross-verify ≥2 independent transcript hosts) |
| `support.n` | sample/coverage **as stated, a string** — `"5 respondents (85–100 of 110–125)"`. A string because an integer n silently masquerades as the base. |
| `support.method` | how the evidence was produced, one line |
| `support.base_defined` | **the first question to ask of any number**: is the measured quantity itself specified (population, metric definition, cuts)? Explicit `false` caps the digest at C. |
| `support.vintage` | when the underlying data is from (`YYYY[-MM]`) — not when you read it |
| `freshness` | `fresh` · `dated` (default threshold ~18 months, profile-tunable) |

**`grade` is derived, never authored** — a letter digest recomputed from the
tuple (doctor flags drift): `A` = independent + strong basis
(official-record/platform-data/measured), base not recorded undefined ·
`B` = independent/corroborated with basis and method recorded · `C` = every
other recorded judgment · `D` = derivative · `?` = unjudged. A pre-0.8
authored letter survives migration as `support.seeded: legacy-grade` — the
digest returns it until a real grading replaces the seed (doctor lists
seeds as expected-until-touched). `flip grade --explain` prints the
derivation: only `independence`, `support.basis` and `support.base_defined`
move the letter (plus `support.method`, which alone gates B); `support.n`,
`support.vintage` and `freshness` are documentation.

**Pre-0.8 `independence` is a missing judgment, not a weak one** (v0.16). The
key changed *axis*, not spelling: pre-0.8 it recorded **custody** ("we hold
the original bytes, not a copy"), 0.8 records **epistemics** ("is this
evidence independent of its own subject"). An exact-commit copy of a
project's own README is original custody *and* self-reported evidence, so the
translation cannot be made mechanically. A page still carrying `original`,
`republisher` or `self-interested` is therefore **not judged**: it derives
`?`, corroborates nothing, and doctor names it. `flip migrate` maps
`republisher`/`self-interested` (same axis) but only *parks* `original` —
the authored letter moves to `support.pre_08_grade`, the digest resets to
`?`, and a human has to re-read the source. This demotes claims that rested
on such a source, which is the point: a corroboration count drawn from a
judgment flip could not read was never evidence of anything. Every surface
that reports a corroboration count also names the sources it could not count,
because a wrong number is worse than a missing one — only the missing one
prompts a look.

**Liveness and provenance state** (optional, evidence-backed):

- `pipeline: live | dormant | orphaned | transferred:<steward>` with a
  **mandatory `pipeline_evidence` receipt** — an enum alone is not
  self-evidencing, and `transferred` vs `orphaned` drive opposite consumer
  behavior. Liveness belongs to the source, not the claim.
- `provenance_state` — where the chain-walk behind this source ended:
  `PRIMARY-REACHED · PRIMARY-GATED · PRIMARY-LOST` (archive check recorded)
  `· PRIMARY-NEVER-PUBLISHED` (the *normal* terminal for commercial data —
  name the closest public derivative, never silently promote it)
  `· PRIMARY-EXISTS-PRIVATE · PRIMARY-OPEN` (legal mid-pass; doctor refuses
  done/published while a load-bearing claim rests on one).

**The refresh receipt** (`flip source recheck <id>`): a page timestamp
says the page changed; `last_checked` says the world was checked.
Recheck re-fetches the canonical coordinate into a temp area (custody is
never overwritten), hash-compares against the capture ledger, appends a
`recheck` event ({result: unchanged|changed|gone, sha256_now,
sha256_captured}), and on drift sets `drifted:` — doctor warns on the
source (`source-drift`) and on load-bearing claims resting on it
(`drifted-evidence`). A drift worth keeping is a fresh capture; an
unchanged recheck clears the flag. Cached synthesis without a checked-at
receipt is a claim about the past wearing present tense.

**Claim credibility** lives on the claim (§7). LLM and retrieval-service
outputs are `synthesis`-basis intermediaries; under `citation_rule:
public-terminus` a load-bearing chain must end at a public, independently
verifiable source. **Unjudged sources never corroborate:** capture is
custody, not judgment.

### 5.5 Text derivatives — `sources/text/` and the derivation log

Custody holds the bytes; a **text derivative** makes them readable. One file
per source, `sources/text/<id>.txt`, produced by `flip extract <id>` from an
`[extractors]` command (§15) and logged as one row in
`derived/_derivations.jsonl`. Nothing about a derivative is required: a source
with none is a complete source.

**Extraction methods.** `method` in the derivation row records *how* the text
was recovered, from a fixed vocabulary — the same discipline §5.1 applies to
acquisition, one layer down, and for the same reason. **A quotation recovered
by OCR is not the same evidence as one lifted from the publisher's own text
layer**: one is a transcription of the document, the other is a machine's
reading of a picture of it, and the second can silently drop a minus sign, a
footnote marker, or a whole column. Until a notebook could say which, every
quotation looked equally solid.

| method | the text came from |
|---|---|
| `text-layer` | the document's own embedded text, as its producer wrote it |
| `layout-text` | that text plus geometric reconstruction of reading order |
| `ocr` | the page rendered to raster and recognized — a reading, not the text |
| `markup-strip` | markup reduced to prose |
| `structured` | an office/structured format's own text |
| `transcript` | speech recognized from media |

Unlike §5.1's these are **not a ladder**: they do not escalate, they apply to
different documents, and the right one is a fact about the input. The row
already records the *actor* (`tool`, `tool_version`, `cmd`), so `method` is
where the method belongs — methods travel between deployments, tool names are
local trivia. An implementation must not invent one: where no method is known,
none is recorded, and doctor asks for it (`unvocabularied-extraction`). A lane
*named* after a method supplies it.

**Fidelity is derived, never authored** — as with capture fidelity (§5.1) and
the source grade (§5.4). From the word count and the page count:
`text-only` (a real derivative) · `thin` (**under 25 words per page**) ·
`empty` (no text at all) · `unknown` (a `method` outside the vocabulary, so
what this text is cannot be read off the record). The threshold is calibrated,
not guessed: on a measured corpus real extractions ran 391–994 words/page and
silent failures 0–10.8, with nothing in between.

**Near-nothing is two distinct events**, exactly as `failed` and
`not-captured` are in the capture log:

- **No text at all.** An extractor that exits 0 having produced no words has
  *reported a finding about the document* — an image-only scan, a form with no
  content. It is not a defect in the config, and presenting it as one sends the
  reader to debug a lane that is fine. The row records `status: not-extracted`,
  **no output file is written**, and the refusal names the operator's own other
  lanes (§16) rather than leaving them to be remembered.
- **Almost no text.** Under 25 words/page the file *is* written and logged
  `thin`, and the warning is loud at extraction time, because unlike the empty
  case this one leaves a plausible-looking `.txt` on disk with a sha256 and a
  derivation row behind it. An image-only scan, a text layer the tool declined
  to trust, and an extractor silently skipping pages are indistinguishable from
  each other and from success, unless someone opens the file.

**Immutability, and what makes overwriting safe.** `sources/raw/` is never
touched by extraction. A derivative is *not* raw and may be overwritten —
re-running a better lane over the same document is the normal case, not an
exception — and what makes that safe is that the log is append-only. Every
extraction appends: inputs (path, sha256, bytes), the tool and its version and
the **verbatim command template**, the lane and the method, outputs (path,
sha256, bytes, words), pages and words/page where known, and `supersedes` —
the sha256 of the output this one replaces. Fidelity is **not** among them: it
is derived on every read, like capture fidelity and the source grade. A claim quoting
the old text can still be traced to the run that produced it.

That log is also how flip distinguishes its own last output from someone
else's work: **if the file on disk hashes to no row, a person wrote it**, and
re-extracting is refused without an explicit override. Doctor names such a file
(`unlogged-derivative`), a thin one (`thin-derivative`), a derivation that
won't say how (`unvocabularied-extraction`), and a captured document with no
derivative at all (`missing-derivative`, an expected-until-use notice).

That last one deliberately does **not** consult machine configuration. Doctor
reads the notebook; a check that fired only where a lane happened to be
installed would give two readers of the same committed notebook different
findings, and would go silent for exactly the reader least able to notice the
text was missing. "This capture has no readable derivative" is true whatever
is installed, and it presumes no tool — reading the bytes is a legitimate
answer, and so is deciding a source never needed text. Only the advice in the
message changes with what the operator has configured.

**On demand, not automatic.** `flip add-source`'s contract is custody.
Extraction is a derivation with its own ledger, its own failure modes, and its
own cost — an OCR pass over a long scan is a minutes-long, gigabyte-scale job —
so it is a separate verb, opt-in inline at capture, nudged once when a document
lands and a lane exists, and named by doctor thereafter.

**flip ships no extractor and defines no default lane.** The bundled
`flip-fetch` can exist because it is stdlib-only; a PDF or OCR extractor cannot,
and the package must not acquire an opinion about PDF libraries (§16). The
starter config carries a fully commented `[extractors]` stanza, and every
refusal names the operator's own file and lanes.

### 5.6 Custody storage — where the bytes live in a git repo

Custody is bytes, often large ones, and git remembers every version of
everything forever. What a git-managed notebook does with `sources/raw/` is a
policy decision the operator owns — flip does not build paternalistic
software, and like the acquisition stance (§5.1) this is **a default with
worked alternatives, not a rule**: an opinion for the common case, and every
part of it is the operator's to change.

**The default: track `sources/raw/` with git-LFS.** Custody stays versioned,
cloneable, and inside the same repository as the judgments that rest on it;
the working tree carries real bytes; history carries pointers instead of
payloads, so the repo never swallows its own archive. This is the stance to
deviate from knowingly.

Two worked alternatives, each honest about what it trades:

- **Ledger-committed custody.** gitignore `sources/raw/` and commit the
  provenance ledger (`sources/_provenance.jsonl`) plus a sha256 manifest of
  the raw tree. Custody stays local, integrity stays provable — anyone
  holding the bytes can verify them against the committed hashes — and the
  repo stays small. The trade: a clone is not custody; the bytes travel by a
  separate channel (`flip export bag`, a share, a blob store).
- **Committed custody, wholesale.** Commit `sources/raw/` as ordinary git
  objects. Every clone is a full custody copy — the strongest availability
  story there is — and the cost compounds silently and permanently: a
  measured corpus reached a **931 MB `.git`** carrying a 104 MB blob in
  history, and git history cannot be cheaply unwritten — rewriting it
  invalidates every clone, every commit ref, every collaborator's checkout.

**Decide at `flip new` time.** The whole reason this is a creation-time
decision is the last line above: the default failure mode is not choosing,
capturing for months under git's own default (wholesale commit), and
discovering the weight only when the repo is already too heavy to move —
at which point every option involves rewriting history. `flip doctor` warns
when it finds raw custody bytes committed as ordinary git objects (the
custody-in-git warning, so the notebook that never chose gets told while
choosing is still cheap); a repo that chose wholesale commit on purpose is
the operator's call, taken with its cost stated.

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
7. **Attribution everywhere.** Every ledger event records its `actor`, and
   every entity page records OKF's `generated: {by, at}` (§5.2 of the OKF
   spec) — who produced the content and when. Actor strings are
   `human:<name>` / `agent:<name>` / `tool:<name>`; OKF's trust tiers key
   off the `human:` prefix, which flip's convention matches.
8. **Renders are never edited.** Fixes flow to the notebook and re-render.

Extension vocabulary summary — flip's frontmatter keys beyond OKF v0.2's
(`type`/`title`/`description`/`resource`/`tags`/`sources`/`generated`/
`verified`/`status`/`stale_after`): `id`, `aliases`, `grade`,
`independence`, `freshness`, `local`, `sha256` (on export), `date`,
`authors`, `publisher`, `load_bearing`, `independent_corroboration`,
`first_asserted`, `question`, `alternatives_rejected`, `model`, `tools`,
`started`, `ended`, `resolves_via`, `formulations`, `answered`,
`answered_by`, `closed`, `closed_by`, `closed_reason`, `review_by`,
`reopen_when`, `absence`, `derives_from`, `universe`, `stop`,
`does_not_redo`, `for`, `roi_low`, `roi_high`, `consumed` — plus
extension keys *inside* OKF structures: `method`,
`against`, and `note` on `verified` events, and `sharpened`/`note` on
`formulations` entries. flip's `status` vocabularies
(claim, question, and commission statuses, notebook lifecycle) extend OKF
§5.4's advisory `draft|stable|deprecated` values — plus `role` on a claim's
`sources` entries (§7). OKF consumers must preserve and may ignore all of
them.


### Disciplines — declared standards, slot composition (v0.14)

A **discipline** is a named, versioned policy standard — what a notebook
is *held to*, distinct from its kind (what it's *making*) and its beat (a
loose topic / multi-notebook bundle; beats and disciplines are different
things and do not converge). One TOML per discipline — built-in,
`$FLIP_HOME/disciplines/`, or notebook-local; single-file or directory
form — declaring: `kind` (`regime|overlay|frame|frame-regime`), the
classes it `governs`, the **slots** it owns (named policy areas — open
strings, with the registry below as shared vocabulary), `gates`
(`enforced` block; `attested` record a third party's already-run
verification and never block), advisory `checks`, namespaced
`vocabulary`, graceful `depends_on`, and declared `conflicts` that the
manifest must resolve (`[discipline_resolve]`) — never silently merged.
A check is a doctor check code (the stable registry every finding
already prints) or a simple field predicate
(`{class, field, requires: present|absent|one_of}`); there is
deliberately no expression language.

**Composition**: partition the gates by slot — one owner per slot per
notebook, the owner blocks; union the rubrics — every declared
discipline's checks run, non-owners emitting labeled advisory findings,
never silently discarded. Substrate policies compose strictest-wins;
epistemic policies are never auto-merged. **Dormancy**: a manifest with
no `disciplines:` key behaves exactly as before — implicitly
`["lineage@1"]` (plus `"forecasting@1"` when forecasts/ exists) with no
new findings; the machinery wakes only on explicit declaration.

**Versioning**: `MAJOR.MINOR`. `1.x` is reserved for self-descriptions
of enforcement flip itself guarantees (`lineage@1.0`,
`forecasting@1.0`); `0.x` marks authored disciplines still earning
stability (`systematic-screening@0.1`, and everything domain experts
write via `flip discipline new`). Pins: `id@MAJOR` takes the highest
available minor; `id@MAJOR.MINOR` is exact; a newer minor than an exact
pin is a visible WARN — the standard never moves silently. Exports carry
the declaration: the identity of the *standard* travels with the bundle.

**Starter slot registry** (open — shared names, not a closed enum):
`custody` · `grading` · `corroboration` · `release` · `staleness` ·
`resolution` · `calibration` · `two-object` · `screening` ·
`sourcing.tier` · `evidence_standing` · `citation_role` ·
`corrections.trigger` · `attribution` · `disclosure`.

Kinds may `require` slots (`requires = [{slot, default}]`) — a kind
names the policy *area* its output needs filled, never a specific
discipline; the default is a suggestion, informational until the
notebook declares disciplines.

## 7. The working record — claims, questions, forecasts, commissions

```markdown
---
type: Claim
id: C7
aliases: [C7]
description: "AI retail traffic converts ~42% better than non-AI"
status: needs-2nd
load_bearing: true
sources:
  - { id: A12, resource: /references/single-vendor-conversion-study.md, title: Single-vendor conversion study }
independent_corroboration: 1
first_asserted: 2026-07-09
generated: { by: agent:claude, at: 2026-07-09T14:31:02Z }
---
AI retail traffic converts ~42% better than non-AI.[^A12]

_Single vendor study; seek platform data or a second measurement._

[^A12]: [Single-vendor conversion study](../references/single-vendor-conversion-study.md)
```

`status`: `asserted` → `verified` | `needs-2nd` | `unconfirmed` |
`false-positive` | `retracted` | `superseded`. A claim is `verified` only
with the corroboration its profile demands (default: two sources whose
recorded `independence` is `independent`, or one whose derived digest is A),
counting only judged sources. A quantitative claim SHOULD carry its number
as data — `value` (a string; ranges and "~42" are legal) and `unit` — so
the format's own exports can ship it; prose alone can't.
`independent_corroboration` is stored for consumers but recomputed by the
tooling — doctor flags drift — and it is **absent, not zero, when the axis
does not apply** (citation roles, below). `sources` is OKF v0.2 §5.1
provenance: one entry per cited source, `{id, role?, resource, title?}`, where
`id` is the machine-stable source id and `resource` the followable
bundle-absolute page path (a dangling cite — legal, §6.1 — keeps just its
`id`). Per-claim
attribution follows the OKF footnote idiom: the assertion carries `[^A12]`
markers keyed to `sources[].id`, and the generated definition lines at the
body's end double as relative links, so link-graph tools (Obsidian) keep
their edges. Both generated parts are regenerated on status/source changes;
labels are always id-shaped, so hand-authored footnotes survive.
Fine-grained span anchoring may use W3C Web Annotation selectors; optional.

#### Citation roles — what a citation is FOR

`sources[].role` says what a citation *does* for the claim that makes it. Two
values, and the role belongs to the **citation**, not to the claim and not to
the source page: the same paper is what one claim is about and a witness for
the next one.

| role | means | corroborates? | the audit that applies |
|---|---|---|---|
| `evidence` | a witness to what the claim asserts. **The default**, and the meaning of the key's absence | yes, when the source page is judged and `independent` | a second independent source |
| `subject` | the claim is **about** this source — it is what makes the claim true or false | never | a severe `attribution` test (§7.1) |

```yaml
sources:
  - { id: P18, role: subject, resource: /references/ssrn-3026941.md, title: "Kahan & Peters (2017), Rumors of the Nonreplication…" }
  - { id: A9, resource: /references/npr-em-dash.md, title: "NPR (2025), Inside the unofficial movement…" }
# no independent_corroboration key when every entry is role: subject
```

The corroboration bar is sound for a claim about the world: agreement between
causally *independent paths* to the same fact is evidence — two witnesses to a
crash, two labs measuring a constant. It is unsound for a claim about a
document. "The rebuttal answers Ballarini & Sloman and never mentions Persson"
is made true or false by the rebuttal; a second source could only ever be a
second *reading* of it, which is an independent reader rather than an
independent path. That addresses reader error, and corroboration is a check on
source error. So a `subject` citation is excluded from the count.

**And the count goes away rather than to zero.** A claim that cites something,
all of it `subject`, carries **no `independent_corroboration` key at all**.
`0` there is the same wrong number §5.4 already refuses for an uncountable
source: it reads as *the evidence is thin* when the truth is *this axis does
not apply here*, and a wrong number is worse than a missing one — only the
missing one prompts a look. A claim citing **nothing** keeps its `0`, and the
difference is the whole rule: absent means **inapplicable**, never **unmet**.
Every surface obeys it — `flip claim add`/`status`/`source add|rm` and
`flip show --claims` print `corroboration: n/a (subject)`, `flip ws show`
prints `corroboration n/a (subject)`, and the JSON projections **omit** the
key (render/2 carries `subjects: [ids]`, so a renderer can say why).

**What replaces the bar.** `flip claim status <C#> verified` on a claim citing
only subjects accepts a **severe, surviving `attribution` test against every
cited subject** in place of the count — the audit the situation actually
admits, and one any reader can re-run against the same custody, which is
exactly what makes it the right check where a second source is impossible in
principle rather than merely absent. Nothing else is loosened: a claim with any
`evidence` citation faces the ordinary bar, and A2's adversarial/recomputation
path is unchanged. A severe attribution *failure* still refuses `verified`
through the exposure gate (§7.1) before any of this is consulted.

**Anti-abuse, stated rather than enforced.** A role is authored, so `subject`
can be used to duck a bar a claim should have faced. flip's answers are that
the role is legible on the page and in every export, that an unreadable role
reads as `evidence` (so a typo can never quietly excuse a claim — doctor's
`bad-enum` names it), and that doctor's `unaudited-claim` names a load-bearing
claim carrying a subject citation with no attribution test on record: the
audit that IS available, not taken. **flip checks that the test is present,
never that it is true** — the same limit §7.1 declares for every field of a
test record. Roles need no migration: `evidence` is the default and every
citation written before 0.16 already has it, so existing pages round-trip
byte-identical. `citation_role` is a slot name in the §6 registry, so a
discipline can hold a notebook to a stricter policy than flip's.

**Verification methods** (`verified:`) widen the honest ways a claim earns
its status without softening the bar. The key is OKF v0.2 §5.2's
verification-event list, append-only — records are added, never edited —
each `{by, at, method, against?, note?}`: `by`/`at` are OKF's (consumers
derive trust tiers from the `human:` prefix), and `method` is flip's
extension: `adversarial` (a skeptic pass that sought
disconfirming evidence), `independent-sources` (documents the corroboration
reasoning), or `recomputation` (the result re-derived independently). A claim
passes the `verified` gate when **either** the profile's corroboration bar is
met **or** at least one `adversarial`/`recomputation` record exists;
`independent-sources` records the reasoning but never satisfies the gate
alone (the recomputed count does). `flip claim verify <C#> --method …` writes
them; doctor's `unaudited-claim` fires only when a load-bearing claim has
neither corroboration nor any verification record nor anything on record that
went looking for the error — or, on a claim citing a `subject`, when the
attribution test that stands in for corroboration has never been run. OKF
consumers preserve-and-ignore.

`against` is **where the verifying thing is named**, and it is not restricted
to source ids: a session id, a script path, or a derivation record all belong
there. A `recomputation` clears the gate on its own, so it has to be
locatable — doctor's `unlocatable-recomputation` fires on a recomputation
record with an empty `against`. A recomputation nobody can reach is an
assertion with better manners, and it is common for the *citations* on such a
claim to be self-reported sources contributing nothing while the actual
evidence lives in a session page: `against` is how the claim points at it.

#### Absence claims — the null with its coverage attached

"Looked and found nothing" is an assertion the work leans on, and its
evidentiary weight IS its search coverage — an ungraded "no evidence of X"
manufactures certainty exactly the way a synthetic total manufactures
precision. `flip claim add --absent-from corpus | named_surfaces | world
[--surface "<where looked>" …]` marks a claim as an absence and scopes it
(`absence: {scope, surfaces?}` in frontmatter, the same vocabulary the
passed ledger enforces in §8): `corpus` speaks only for what the notebook
holds; anything wider MUST name the surfaces searched. The claim then lives
the full claim life — cited in prose, probed (`flip claim test` against a
searched surface is "re-run the search"), superseded when the thing is
later found. Doctor's `world-absence` names a load-bearing absence scoped
to `world`: no search can witness a world-absence, so the honest scope is
the surfaces actually checked — the scope stays legal (an operator may take
responsibility for the reach; flip does not build paternalistic software),
it just doesn't pass unremarked. Routine empty probes during pursuit belong
on the question (`flip question note --zero-yield`, §7) or in the passed
ledger; a claim is for the null an ANSWER rests on.

#### Derivation — what a claim rests on

A claim built on other claims declares it: `flip claim add --derives-from
<C#>` or `flip claim derives add|rm <C#> <C#…>` writes a `derives_from:`
list — a derivation edge, not a citation (the ancestor is not evidence FOR
the claim; it is load the claim stands on). Unknown ids, non-claims,
self-edges, and cycles are refused at write time. Doctor walks the chain:
**`inherited-unsupported`** (WARN) names every ancestor a load-bearing
claim rests on that cannot carry it — discredited (status
`false-positive`/`retracted`, exposure `refuted`/`misattributed`) or bare
(no evidence citations, no gating verification, no surviving severe test) —
because an unsupported link contaminates everything built on it silently
otherwise; `dangling-derivation` flags an edge to an id no claims/ page
carries, on any claim. The render/2 projection carries `derives_from`, so
a renderer can show the chain.


### 7.1 Stance and exposure — the attitude, and the test record

`status` is truth-tracking and is right for facts. It cannot say two things a
reporter's notebook has to say, and both failures are the same failure: it
fuses **what a claim's evidential situation is** with **what position the
notebook takes toward it**.

- *Every un-verified claim reads alike.* A claim whose cited paper turns out
  not to contain it and a claim nobody has ever tested both sit outside
  `verified` and render identically. They are not the same situation and the
  next actions are opposite — repair the citation, versus run the experiment.
  A notebook that flattens them will read a citation failure as a hypothesis
  failure.
- *There is no room to hold a position the evidence has not reached.* Pursuing
  an original line of thinking is neither asserting a fact nor retracting one;
  it is putting a hypothesis on Peirce's "docket of cases to be tried" (CP
  5.602), the ordinary way inquiry starts. Nor can the notebook record that
  someone **else** believes something it takes to be false — and a widely-held
  false belief is a real causal force whose structure points at interventions,
  so it is data.

Two orthogonal axes, both optional, both silent in a notebook that does not
use them:

| axis | key | authored or derived |
|---|---|---|
| **exposure** — what has been asked of the claim | `tests:` (authored, append-only) → `exposure` (derived, never stored) | described, then computed |
| **stance** — what position is taken, and by whom | `stances:` (authored, append-only) | authored |
| **rivalry** — what answers the same question | `rivals:` (authored) and `superseded_by:` | authored |

#### Reading the sources, and where flip departs from them

Everything below cites a captured primary with a page or paragraph number.
That is not decoration. An earlier draft of this section attributed to Mayo a
graded spectrum she does not have and to Peirce an admission gate he explicitly
denies, and both errors made the design more permissive than its sources. The
rule the project now runs on: a framework name with no captured quote behind it
is a lead, never a justification, and where flip departs it says so in its own
voice.

**Mayo has one failing verdict, not a ladder.** *Statistical Inference as
Severe Testing* p.5, the weak severity requirement: "One does not have evidence
for a claim if nothing has been done to rule out ways the claim may be false.
If data x agree with a claim C but the method used is practically guaranteed to
find such agreement, and had little or no capability of finding flaws with C
even if they exist, then we have bad evidence, no test (BENT)." Both halves of
that sentence — nobody looked, and somebody looked with something blunt — land
in one verdict. flip's word for it is her acronym: `bent`.

**An unrecorded severity grades low, not neutral.** SIST p.201: "But if it
cannot be computed, it's also awful, since the onus on the researcher is to
satisfy the minimal requirement for evidence… If we cannot compute the severity
even approximately, I'll say it's low, along with an explanation as to why:
It's low because we don't have a clue how to compute it!" So a claim nobody has
tested does not render as a blank waiting to be filled in. It renders as the
worst reading this axis has, and every surface that shows the verdict shows the
reason with it — the second half of her prescription and the half that is easy
to drop.

**Severity is relative to a specified error, and the capability condition runs
both ways.** SIST p.65: an inference is warranted "having passed a severe test
(a test that C probably would have failed, if false *in a specified manner*)."
SIST p.16, Arguing from Error: "There is evidence an error is absent to the
extent that a procedure with a very high capability of signaling the error, *if
and only if* it is present, nevertheless detects no error." The "only if" is a
second, separate condition: a probe that fires whether or not the error is
there discriminates nothing, however carefully it was run.

**Peirce's price is verifiability, not economy.** The economy of research
cannot gate anything, and reading it as a gate inverts him. CP 1.136, the
sentence immediately after "Do not block the way of inquiry": "Although it is
better to be methodical in our investigations, and to consider the economics of
research, yet there is no positive sin against logic in trying any theory which
may come into our heads." CP 7.220 makes cheapness a reason to give a
hypothesis *precedence* in the inductive procedure "even if it be barely
admissible for other reasons." What does gate is CP 5.197: "Any hypothesis,
therefore, may be admissible… provided it be capable of experimental
verification, and only insofar as it is capable of such verification." And it
asks for something sharper than "what would move you" — CP 2.89: verification
"must consist in basing upon the hypothesis predictions as to the results of
experiments, especially those of such predictions as appear to be otherwise
least likely to be true"; CP 1.120: "The best hypothesis… is the one which can
be the most readily refuted if it is false. This far outweighs the trifling
merit of being likely."

**The joint result, and the reason both are cited at all.** Peirce wants the
prediction that would be least likely to come out right if the hypothesis were
false. Mayo wants the probe that would not have signalled had the error been
absent. Those are one condition approached from opposite ends, seventy years
apart, by people with nothing else in common: **a claim owes an observation
that comes out differently depending on whether it is right.** `falsifier` on a
stance is that observation promised; `if_absent` on a test is that observation
delivered. Nothing else in this section is a joint result and nothing else is
claimed to be.

**Letting go is comparative.** Lakatos, *Falsification and the Methodology of
Scientific Research Programmes*, p.69: "a degenerating problemshift is no more a
sufficient reason to eliminate a research programme than some old-fashioned
'refutation' or a Kuhnian 'crisis'… such an objective reason is provided by a
rival research programme which explains the previous success of its rival and
supersedes it by a further display of heuristic power." Nothing in this section
fires on a timer. A claim is let go of by naming what beat it.

**Where flip departs from all three, in its own voice.** (1) The probe taxonomy
is flip's. Mayo has no notion of an attribution error, because in her setting
the claim and its evidence are the same object; separating "the paper does not
say this" from "the world is not like this" is this section's own contribution
and its whole origin. (2) `untestable` is Peirce's admissibility condition (CP
5.197), not a degree of Mayo's severity: it says the claim as posed does not go
on the docket. (3) flip checks the *presence* of `error`, `would_detect`,
`if_absent` and `against`, never their truth — no more than it can check
`support.method`. A severe test here means somebody wrote four specific things,
and somebody who writes four plausible lies gets a severe test. (4) Lakatos
also requires the successor to explain its predecessor's successes; that is a
judgment about content, so flip reports every rival comparison and enforces
none of them.

#### The test record

`tests:`, one entry per test run, append-only:

| field | what it is |
|---|---|
| `probe` | the class of error looked for: `attribution` (does the cited source contain the proposition?) · `substance` (is it true of the world?) · `scope` (does it hold outside the conditions its evidence covers?) |
| `error` | the specific way of being wrong. **Required** — severity is severity for a specified error (SIST p.65) |
| `would_detect` | how the error would have shown up had it been present (SIST p.16, the "if") |
| `if_absent` | what the probe would have shown *instead*, had the error not been there (SIST p.16, the "and only if") |
| `result` | `survived` · `failed` · `inconclusive` · `untestable` (the claim *as posed* admits no test) |
| `against` | what did the testing: a source id, a session page, a script path |
| `note`, `at`, `by` | documentation |

Three probes, not four. `derivation` was a fourth and is gone: a claim true of
its inputs that does not follow from them is a real failure, but its repair is
`substance`'s repair, and an enum value that changes nothing about the next
action is a word the operator learns for free. The three that remain each have
a *different* repair — fix the citation, supersede the claim, narrow the claim
— which is the test a value has to pass to stay.

`tests:` is **not** `verified:`. That key is OKF v0.2 §5.2's and its entries are
verification *events*, so a test that found the error cannot live there without
an OKF consumer reading a refutation as a confirmation.

**A test's `severity` is derived**, and it has two values: `severe` when all
four authored conditions are present and the test reached a verdict, and
`bent` otherwise. `bent` is Mayo's word and it is deliberately not a softer one
— an earlier draft called it `weak`, which reads as a rung below severe and
invites exactly the gradient SIST p.5 refuses. `inconclusive` and `untestable`
are always bent.

**`exposure` is derived, never stored** (the rule that makes `grade` a summary
rather than an opinion, §5.4). Five values:

| exposure | means |
|---|---|
| `bent` | no severe test on record — nobody looked, or what ran could not have caught the error, or two severe tests of one probe contradict each other so the audit itself failed. One verdict for all three, and the **worst** reading here, not a neutral floor |
| `severely-tested` | a test that would probably have caught the error ran, and did not catch it. The strongest thing this axis says |
| `misattributed` | a severe **attribution** test failed: wrong about what a source says, and *silent* on whether the proposition is true |
| `refuted` | a severe substance or scope test failed: wrong about the world, or about its own reach |
| `untestable` | an attempt concluded the claim as posed admits no test — Peirce's admissibility, not a degree of testedness |

Precedence: a severe failure with no severe survival on the same probe decides,
and which probe failed decides the word; a probe that both severely failed and
severely survived is a failed audit and reads `bent`; then severe survivals;
then `untestable`; then `bent`. `flip claim exposure <C#>` prints the
derivation the way `flip grade --explain` does, **including which road into
`bent` was taken**, because a verdict without its reason is the half of SIST
p.201 that is easy to ship. A page that **stores** `exposure` or `severity` is
a doctor ERROR (`stored-exposure`).

Three exposure terms were removed when this section was corrected, and each
removal is a correction rather than a tidy-up: `untested` and `weakly-tested`
merged into `bent` because Mayo gives them one verdict, and `contested`
disappeared because two severe tests disagreeing is not a stable middle an
operator can sit in — it is a failed audit, and the readings "go out the window"
(SIST p.201) until somebody says which test was not the test it claimed to be.

#### Stance

`stances:`, append-only, `{stance, holder, because, falsifier?, sources?, at,
by}` — what is *done* with the claim:

| stance | means | falsifier |
|---|---|---|
| `pursuing` | worked from ahead of the evidence, because it would explain something | **required** |
| `holding` | the notebook's position; it would defend this | optional |
| `abstaining` | a position considered and deliberately *not* taken — distinct from no stance, which means nobody has decided | optional |
| `rejecting` | taken to be false, and kept because someone holds it or its failure is informative — **not** `status: retracted`, which withdraws the notebook's own assertion | **required** |

`because` is always required: a stance word alone is an enum without evidence.
**`pursuing` and `rejecting` cost a `falsifier`**, on the ground given above —
CP 5.197's verifiability condition, asking for CP 2.89's prediction "otherwise
least likely to be true", not the economy of research. The rejecting half is
CP 1.135's corollary read in the other direction: a rejection with no way back
barricades the road exactly as a dogma does. flip cannot audit whether a
falsifier is any good, and does not pretend to; it refuses the stance until one
is written and it asks for the right thing while refusing. The falsifier is the
promise; `flip claim test` is the receipt.

**`holder` defaults to the reserved value `notebook`.** Any other holder
records that *someone else* takes this position, which is how a belief the
notebook rejects is kept as data rather than argued with: the notebook's
`rejecting` and a population's `holding` sit on one page without overwriting
each other. The limit is honest and stated: a free-text holder is an assertion
*about* those people, so `sources` on the record is where the evidence that
they hold it goes (doctor's `unsourced-holder`), and a **prevalence** — "62% of
X believe P" — is its own Claim with its own sources and grades, cited from
here. Stance records who, not how many.

#### Rivalry, and how a claim is let go of

`rivals:` is a list of `{claim, because, at, by}` — other claims the notebook
has named as answering the same question. It exists because a stance sits on
one claim, so "C7 is doing worse than C12" is meaningless until something says
the two are answering the same thing, and no tool can infer that: two claims
can share every source and answer different questions, or share none and answer
the same one. `because` carries the question in the operator's words. The link
is written to **both** pages — a comparison only one side can see is not a
comparison, and the incumbent is the page anyone worried about the incumbent
opens.

`superseded_by:` names the claim that won. **`status: superseded` cannot be
reached any other way:** `flip claim status <C#> superseded` is refused, and
`flip claim supersede <C#> --by <C#> --because …` writes the pointer, registers
the rivalry and sets the status in one move. That refusal is Lakatos p.69 as a
CLI behaviour — a bare status change records only that the notebook got tired
of a claim, and getting tired is the one reason he says is not a reason. If
nothing has replaced it, the honest statuses are `retracted` or `unconfirmed`;
if it is wrong but worth keeping, `rejecting` keeps it as data. Superseding by
a claim that is not itself severely tested is allowed and *named* in a note:
that is a swap, and the operator may know something the exposures do not.

#### Interaction with the rest of §7

The two axes are independent of `status` and of each other by construction: a
claim can be `severely-tested` *and* `rejecting`, or `bent` *and* `pursuing`,
and both are ordinary. Two interactions are enforced. **`flip claim status <C#>
verified` is refused when the exposure is `misattributed` or `refuted`** — a
severe test that went looking for the error and found it is a stronger fact
than any count of sources agreeing, and a plausible citation is exactly what
makes a source *countable*. Tests can only ever close that gate, never open it:
a test record is authored by the same hand that authored the claim, and letting
a described test satisfy the bar would let a notebook verify itself by writing
a sentence. And **`superseded` requires a successor**, above.

There is one place a test does open a gate, and it is the exception that shows
the rule. A claim citing only `subject` sources (§7) faces a corroboration bar
that is **inapplicable rather than unmet** — no second witness to what one
document says can exist — so a severe, surviving `attribution` test stands in
for the count there. That is not a described test satisfying a bar it could
have met another way; it is the only audit the situation admits, taken. The
worry above still holds and is answered the same way it is everywhere else in
this section: flip checks the test is on record, never that it was any good,
and says so rather than pretending otherwise.

`attribution` is the probe this whole role distinction points at, and the
pairing is not a coincidence. The probe exists because Mayo has no notion of an
attribution error — in her setting the claim and its evidence are the same
object — and a `subject` citation is precisely the case where they *are* the
same object. Where that is true, "does the source say this?" is not a lesser
check than "is it true of the world?"; it is the whole question.

**No credence lives here**, and the two-object rule is why. Claims carry
grades, never probabilities (a `probability` on a Claim is doctor ERROR
`two-object`), and a Forecast earns its number by being *resolvable* — dated,
with `resolution_criteria` and a mandatory `annul_if`, scored on resolution. A
credence on a standing claim resolves never, accrues no credibility, and can
only ever flatter. It would also re-flatten what this section un-flattens:
0.3 can mean "nobody has looked" or "severely tested and it half-failed", and
those need different next actions. The honest way to price a belief in a claim
is to open the forecast that would settle it (`bears_on: claim:C7`), which
costs a resolution date and an annulment clause.

#### doctor

All seven are silent on a claim carrying none of `stances:`, `tests:` or
`rivals:` — the axis is opt-in, and a lint that fires because a feature exists
teaches operators to tune doctor out.

| code | level | fires when |
|---|---|---|
| `stored-exposure` | ERROR | a page stores `exposure` or `severity` |
| `unpriced-stance` | ERROR on load-bearing, else WARN | `pursuing` or `rejecting` with no falsifier (hand-edited: flip refuses to write one) |
| `misattributed-citation` | WARN active, ERROR once done/published | a claim a severe attribution test found wrong about a source, still citing it. On a `subject` citation the advice inverts: **do not unlink it** — a claim without the document it is about has nothing left to be true of, so only the wording can go |
| `unexamined-position` | WARN | the notebook is `holding` **or `pursuing`** a load-bearing claim whose exposure is `bent` |
| `losing-to-a-rival` | WARN | the notebook is still working from a claim a severe test found wrong, while a **declared** rival is `severely-tested` |
| `no-declared-rival` | WARN | a load-bearing claim is being pursued with nothing on record that could have beaten it |
| `unsourced-holder` | WARN | a belief attributed to someone with nothing cited to show they hold it |

Plus `bad-enum` on any out-of-vocabulary stance, probe or result.

Two of those deserve their reasoning in the spec rather than only in the code.

**`unexamined-position` fires on both positions on purpose.** An earlier
version fired on `holding` alone, so an operator could silence the notebook's
only warning about untested belief by switching the stance word to `pursuing` —
which at the time was a state with no exit, nothing pointing out of it and no
tests required to stay in it. The design had an incentive gradient running
downhill toward its own blind spot, and its test suite certified the gradient.
The finding is now about the claim's *exposure*; the stance changes the wording
of the advice and nothing else, and the only way to clear it is to record a
test that could have come out the other way.

**`no-declared-rival` is a fact about the record, and says so.** Comparative
elimination relocates the burden onto declaring your own competition, and the
operator most likely to be stuck is the least likely to name a rival: Lakatos
could rely on a community to supply rivals, a solo notebook cannot. So the
check does not claim "there is no alternative" — it cannot know that. It says
*nothing on record could ever have won*, so no amount of evidence can make this
claim lose to anything, which is a true statement about the notebook and is the
condition under which the comparative criterion is inoperable. It is a WARN
forever, it asks for the best alternative the operator can state *even one they
think is wrong*, and it is suppressed when `unexamined-position` already fired,
because a claim nobody has tested has a nearer problem than a claim nobody has
a challenger for. What it cannot do is make a named rival a real one; a
placeholder satisfies it, exactly as a ritual falsifier satisfies the stance
gate, and the answer is the same in both cases — flip records presence, the
reader judges content, and the record is at least inspectable.

### 7.2 Decisions and questions — the question journey

Decisions and questions follow the same shape: `decisions/<slug>.md`
(`type: Decision` — `question`, decision text, why, `alternatives_rejected`)
and `questions/<slug>.md` (`type: Question` — `status: open | answered |
closed | dormant`, settled pages keep their history in git). Questions
SHOULD carry `resolves_via: [<surface>, …]` — the surfaces that could
answer them; an open question without a watching surface is a wish, and
`flip show` marks it `unwatched`. **Questions are re-posed
append-only**: `flip question repose <Q#> "<new formulation>"` keeps the id,
slug, and status; the new formulation becomes the current description and body
lead, while the superseded text is preserved in a `formulations:` history list
(`{text, date, actor}` — plus `sharpened: [scope | falsifiability |
decomposability | evidence-anchored]` and `note` when the re-pose says what
it sharpened; recorded, never scored) and a dated **Re-posed** body section,
and a `question-repose` event lands in the log — so `flip open Q#` always
shows the full journey.

**Evidence accretes on the question between re-poses.** `flip question note
<Q#> "<text>"` appends a dated **Evidence** section to the page body without
touching status — with `--answers as-worded | narrower | adjacent` recording
the scope verdict (did this evidence answer the question as worded, or a
narrower or adjacent one? a narrower answer stays on an OPEN question
rather than closing it), `--source <id>` citing evidence that must resolve,
and `--zero-yield saturated | bad-reformulation | corpus-gap |
entity-collision` recording an empty probe WITH its cause — a zero round
without a cause is indistinguishable from saturation, and only tagged
zero rounds may count toward a stop decision. Noting is legal at any
status: evidence arriving after an answer is exactly what reopen triggers
watch for.

**A question has more honest ends than answered.** `flip question close
<Q#> --reason split | yielded | counter-example | dead-end | superseded`
records the other ends (`closed_reason:` on the page; answered pages refuse
closing — reopen first). `flip question dormant <Q#> --until YYYY-MM-DD`
parks an open question with a `review_by:` date; dormant is not dead — the
question leaves the everyday roster and `flip show` resurfaces it once the
date arrives (`dormant · review due`). **Answers carry their un-stop
conditions**: `--reopen-when "<condition>"` on `answer` and `close` arms
written observable conditions (`reopen_when:` on the page) — `resolves_via`
names what could answer a question, `reopen_when` names what would un-answer
it; `flip show` lists armed pages under **REOPEN TRIGGERS ARMED**, and
`flip question reopen <Q#> --because "<what fired>"` restores `open` while
the whole journey — the old answer included — stays on the page.


### 7.3 Forecasts — `forecasts/<slug>.md` (FC#) and clusters (CL#)

A backward notebook fights staleness; a forward notebook **accrues
credibility through resolution**. The two-object rule is the load-bearing
split, machine-enforced by doctor: **claims carry grades, never
probabilities; forecasts carry probabilities, never grades.**

A Forecast (`type: Forecast`) commits to what a watched surface will show
by a date: `question`, `resolution_criteria` (edge cases pre-answered),
`resolves_by` (dated — there are no undated forecasts), `resolves_via`
(surfaces), `resolution_source_ladder` (ranked fallbacks — a forecast
resolves on what the desk can *see*), `resolver`, `probability` and
`confidence` (two scalars in [0,1], never merged), `base_rate` (a string
carrying its own numerator/denominator — outside view first),
`predictability` (`white|gray-light|gray-dark|black`), `annul_if`
(**mandatory** — the written condition under which the question stops
meaning anything), typed `bears_on` refs (`claim:`/`cluster:`/
`question:`), `generated_by`, `horizon` (the planning horizon informed —
distinct from `resolves_by`), `opened`/`freeze`, `status`
(`open|resolved-yes|resolved-no|void|superseded`), and an append-only
`updates:` list.

`flip forecast resolve FC3 yes|no|void` flips status, appends the closing
update, logs the event, and appends one row to the append-only
**`log/resolutions.jsonl`** (topic · bears_on · prior · evidence ·
posterior · shift · confidence · source). The record is scored two ways,
always labeled: **sharpness** (resolved-yes share) and **Brier** (mean
squared error, reported only at ≥5 resolutions). `flip forecast due`
lists what a sweep should check; declined generated questions are logged
with reasons, and the **fold** disposition (`--fold-into FC2`) records a
decline whose substance survives as another forecast's annulment clause
or criteria.

A Cluster (`type: Cluster`, CL#) holds an unresolvable decision question
(`scored: false`, `probability: null` by construction) over ordered proxy
Forecasts, with any `inference_link` pointing at a **Claim** page — the
inference from proxies to decision is itself a gradeable claim, and class
purity holds at the file level. The `forward-set` kind carries the
discipline extras: at least three dated forecasts and a naive baseline
declared in `baseline.md` **before** the first resolution — the only time
declaring it is worth anything.

### 7.4 Commissions — bounded follow-up work as a contract

```markdown
---
type: Commission
id: K1
aliases: [K1]
description: "refresh the tracker rows against the 2026 snapshot"
status: dispatched
universe: "the 180 active rows as of the R1 baseline"
stop: "every row re-checked once or marked unobtainable"
does_not_redo: "no re-discovery of rows already lineage-audited"
for: Q3
roi_low: "+0.5 completeness"
generated: { by: agent:claude, at: 2026-08-12T14:31:02Z }
---
refresh the tracker rows against the 2026 snapshot

## Dispatched 2026-08-12
```

A **commission** (`commissions/<slug>.md`, ids K#) is follow-up work
written as a contract BEFORE dispatch: the input `universe` it consumes,
the deliverable it produces (the page body), the written `stop` condition,
and the `does_not_redo` boundary — all four required, because continuation
chains that carried them consumed prior outputs without re-discovery and
chains without them re-searched what they already held. `for` links the
question or thread served (must resolve). The ROI band (`roi_low`,
`roi_high`) is optional, free text, directional, and **never additive
across commissions**; the working convention is to quote the LOW bound as
the expectation and the range as upside — executed estimates to date held
at their low bound. Lifecycle: `proposed → dispatched → returned |
declined`, terminal states closed (new work gets a new contract);
`flip commission status <K#> returned --consumed "<what prior output it
consumed>"` records the receipt that keeps a chain auditable. Nothing in
flip dispatches anything — the page records the contract and its outcome,
and the state machine stays in the agent (§1). Commissions ride
flip-render/2.

## 8. Logs — events, sessions, views

- **`log/log.jsonl`** (append-only) — the work log: fetched X, ran Y, hit
  wall Z. `{ts, text, actor}`, one per line. **`log.md`** at the bundle root
  is its generated, newest-first OKF view.
- **`log/passed.jsonl`** (append-only) — negative evidence: considered and
  rejected, with reason. Prevents rediscovery loops. An absence assertion
  carries its scope — `absent_from: corpus | named_surfaces | world` — and
  only `corpus` may be asserted without naming the surfaces checked
  (`surfaces: [...]`): a true statement about a corpus must not travel as a
  false statement about the world.
- **`sessions/<stamp>-<slug>.md`** — one entity page per working episode
  (`type: Work Session`; frontmatter: `generated: {by, at}`, `model`,
  `tools`, `started`, `ended`, `transcript: {id, local}`): the goal, the
  prompt (or pointer), key outputs, pointer to the
  raw transcript when kept. LLM synthesis recorded here is a **lead**, grade
  `C`, until promoted through `references/`.

### Transcripts — the conversation, kept and citable

Claims and graded sources are the **residue** of thinking, not the thinking. A
conversation is where a position actually got built: where the objection
landed, where the framing turned over, which of two readings survived. A
notebook that keeps only conclusions cannot later show anyone — including its
own author — why the conclusion has the shape it does.

So a transcript is kept as a **source**, not as an attachment:

- The bytes land in `sources/raw/` under ordinary custody (§5.1): immutable,
  hashed, one capture row. The method is **`human-in-loop`** — a person was in
  the conversation and handed flip the file, which `copy` alone would
  understate.
- The page carries `medium: conversation` (the marker transcript-aware
  commands route on), optional `participants` and `model`, and a `T#` id — the
  talk/transcript class, because what is cited is an exchange, not a document.
- Grading is unchanged. A transcript is `self-reported` evidence about the
  world and grades `C` at best. What it is genuinely *primary* evidence of is
  the conversation itself, which is what it gets cited for.

**Excerpts** pin a named passage inside the capture, so a claim rests on the
exchange that produced it rather than on the whole file. An excerpt records
`{label, lines, sha256, words}` in the page's `excerpts:` list, and its quote
is **derived from the raw file, never authored** — an excerpt a writer could
hand-edit would be a quotation flip vouched for and could not check. Because
raw captures are immutable, the line range stays meaningful for the life of
the notebook and the stored hash is what proves the copy on the page is the
passage that was pinned. The label doubles as the page anchor, so
`references/<slug>.md#<label>` resolves in any renderer that slugifies
headings.

Labels are stable, because claims cite them: re-pinning an existing label is
refused, and unpinning is refused while any claim still cites it. `flip doctor`
names the three ways a pin stops meaning what it said — `unbacked-excerpt`
(custody gone), `excerpt-drift` (stored quote no longer hashes), and
`dangling-excerpt` (a claim cites a label nothing pins, so the citation
quietly widens from one exchange to the whole conversation).
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
- **Excerpt refs are `<id>§<label>`** (`T1§relevance-null`): a citation of one
  pinned passage inside a transcript (§8). `§` is the separator because `:` is
  taken by handles and `#` was retired as a ref separator in 0.10; labels are
  slug-shaped so they double as page anchors. Qualified and pinned compose in
  that order (`muse:T1§relevance-null`). An excerpt ref **collapses to its
  base id** everywhere evidence is counted: a claim resting on two passages of
  one conversation has two citations and one source, and only the second
  number reaches corroboration (§7). A malformed label is an error rather than
  a dropped suffix — silently dropping it would cite the whole transcript
  while reading as one exchange.
- **Cross-notebook references are `<handle>:<id>`** (`recipes:A3`), where
  the handle is a name *you* bound in the enclosing workspace table (§18) —
  not the notebook's slug, though the slug is the default suggestion.
  Resolution is exact and loud (`flip resolve`, `flip open`): a bare id
  resolves within the containing notebook; `handle:id` resolves through the
  nearest workspace table; unknown handles and unknown ids are errors,
  never guesses. One sanctioned extension: a bare id used under a workspace
  root but outside any notebook resolves iff exactly one bound notebook
  carries it — ambiguity is an error listing the qualified forms to use.
- **`#` as the ref separator is removed** (the pre-0.5 form,
  `<notebook-slug>#<id>`): as of flip 0.10 `handle#id` no longer resolves —
  it fails the ref grammar like any other malformed reference. Writers emit
  only `:`; `flip migrate` still rewrites stored `#` refs (e.g. `links.beat`),
  and doctor flags a stored `#` so it gets migrated.
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

**Generated listings are bounded.** A directory listing is a sign, not the
roster. Past `INDEX_LIST_CAP` (50) entries, a generated `index.md` lists the
newest entries and counts the rest in an overflow footer that names the list
command serving the full roster — measured: a 301-source `references/
index.md` ran 73 KB, ~18 K tokens spent on a directory sign. Hot-view
rosters cap at `HOT_ROSTER_CAP` (8) lines per section with the same footer —
measured: one steady-state hot view was 74 % armed-trigger roster, burying
the single actionable claim. The caps bound only the prose projections:
counts stay exact, the list commands (`flip source|claim|question|commission
list`) carry the complete roster, and every `--json` surface is complete —
an agent that needs everything asks for data, not prose.

**Regeneration is incremental, and byte-identical to the full rebuild.** A
mutating command names the entity directories it touched; unchanged
directories keep their listings, with the root `index.md` body's counts
served from **`.flip/viewcache.json`** — a derived count cache and nothing
more. Measured motivation: the full rebuild re-parses every page on every
mutation, so one `flip log` append cost 1.06 s at 301 sources and 19.8 s at
10,300 pages. The cache is machine-local state like the rest of `.flip/`
(§17): it never ships, and it is safe to delete at any time — absent or
corrupt, every count is recounted from the pages, so it can only ever save
work, never change output.

**The cache is verified, not trusted**, because the generated views are not a
function of the entity pages alone. Every entry carries a cheap fingerprint
of the directory it describes — how many entity files it holds and the newest
mtime among them, one directory scan and no parsing — and an entry whose
fingerprint no longer matches is a miss. This is what keeps the invariant
true when flip is not the only writer, which is the normal case and not the
exception: pages are hand-editable by contract (§3), the reference client
writes them (§20), `flip import --update` replaces them wholesale (§18), and
git checks them out. The questions entry additionally remembers the earliest
pending `review_by` date, because a dormant question resurfaces on the
morning its review comes due with nothing on disk having changed (§7) — an
entry that could not expire itself would freeze a count the calendar had
already made wrong. Only an incremental caller ever writes the cache; a full
rebuild leaves it untouched, so read-only projections (`flip export`) neither
create a side file nor refresh one, and the next mutation re-grounds any
stale entry through the fingerprint.

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

## 13. Kinds — outcomes and profiles, one registry

A notebook's `kind` answers "what are you making" (v0.8). Two families
share one registry and one manifest key:

- **Outcome kinds** (`lit-review`, `decision-packet`, …) are named for the
  output you'd tell a colleague you're making. Each is one TOML —
  built-in, `$FLIP_HOME/kinds/<id>.toml` (or `<id>/kind.toml`; the loader
  treats both forms identically), or notebook-local — carrying a
  **collection contract**: the assets and fields that must accumulate for
  the output to assemble, each entry naming the render section that needs
  it (`assembled_by` — a field no render needs is doctor-findable cargo
  cult) and whether it is *prospective* (cannot be honestly backfilled,
  e.g. inclusion criteria frozen before screening). `flip doctor` reports
  unmet contract entries (`kind-gap`) as WARNs while the notebook is
  active, ERRORs once done/published.
- **Profiles** (below) are rigor-shaped kinds: required files +
  notebook.md sections + claim-verification bar, no collection contract.

The open notebook is first-class: start with any profile (or `scout` by
default) and **adopt an outcome kind late** — `flip kind adopt lit-review`
records the crystallization in the log and prints a **gap manifest**, each
gap tiered honestly: `recoverable` (add it now) ·
`reconstructible-with-loss` (record it non-contemporaneously) ·
`unrecoverable-by-construction` (prospective entries adopted late — the
retrofit is priced before it's promised). `flip kind new <id>` scaffolds a
commented single-file kind for domain experts to fill; `flip kind
list`/`show` inspect the registry. Substrate discipline (custody, grading,
corroboration) applies identically under every kind.

### Profiles

A profile = required files + notebook.md sections + claim-verification bar.
Everything else is optional everywhere.

| profile | intent | requires beyond core |
|---|---|---|
| `ledger` | bibliography / source spine | references/ |
| `scout` | screen an angle fast, editor lens active | hypotheses w/ falsifiers per query · decisions/ · log/passed.jsonl |
| `research-review` | question-organized survey → publishable | claims/ · sessions/ · drafts/ · full custody · workflow journal |
| `engagement` | confidential client work | research-review + `client-confidential` policy + citation rule enforced + HANDOFF.md |
| `data-investigation` | dataset-first reporting | derived/_derivations.jsonl · ingest scripts · frozen data contracts |
| `pursuit` | one question under pursuit | questions/ · claims/ · drafts/question-plan.md · log/; scaffolds the primary question as Q1 and a dated **question plan** (answer shapes before retrieval · prior · holdings · routes + stop rule · plan revisions); notebook.md bands the answer (direct / adjacent / unresolved) |

Profiles are data (TOML shipped with flip; notebook-local `.flip/profiles/`
overrides), selected by `kind` in the manifest. Profile minimums are
**completion requirements, not creation requirements**: missing paths WARN
while status is `active`/`dormant` and ERROR once `done`/`published`/
`archived`. The notebook.md **section menu** (scaffolded by kind, sections
graduate to their own files when they outgrow a heading): *the tip · frame ·
answer (banded honestly: direct / adjacent / unresolved — an honest null is a
legal answer) · assessment (confidence ≠ coverage ≠ usefulness, never
collapsed) · what the data can/can't say · hypotheses & falsifiers · sources &
provenance · priors ledger · decisions · what's not in the piece · workflow
notes · gaps & self-critique · handoff*. Conventions that earned their place:
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
separator; the pre-0.5 `#` form no longer resolves as of 0.10, though doctor
still flags a stored `#` and `flip migrate` rewrites it), and appends a
coverage event. Kill decisions are first-class too: `flip beat thread drop TH3
--reason …` records why in the page and the coverage ledger — negative
coverage prevents re-scouting dead angles.

A beat root is distinguishable from a notebook root (`flip_beat:` vs
`flip:` in the index frontmatter); notebook commands inside a child
notebook resolve to the notebook, `flip beat …` commands walk up to the
beat. In a workspace (§18), handles bind *notebooks* only — a beat root is
not bindable, but workspace discovery walks through it to the real
notebooks under `notebooks/`. Beat-level doctor, saturation warnings ("this
well is over-visited"), and richer coverage roll-ups are future work (§19).

### 14.1 Running a beat on a loop

A beat is already a standing mission, so it is where a **loop policy** lives:
an optional `auto:` block in the beat manifest, and one computed view over it.

```yaml
auto:
  selection: [in-flight, commissioned, due, open-question, thread]
  stop: no unblocked item this pass
  authority: capture, grade, claim, publish; never delete custody
  materiality: a reader-relevant public change, not a status edit
  surfaces: [the public site, the shared worklist]
  cadence: daily
```

Every key is **policy that a reader honours, not behaviour flip enforces**.
`selection` is the exception, because it is the one key flip computes with: it
orders the lanes of `flip beat next`, and a lane outside the vocabulary is
refused rather than ignored — a mission running a policy nobody wrote is the
one failure an autonomous pass cannot notice from the inside. Unknown keys
ride along verbatim, like every other manifest.

**`flip beat next`** answers the question a pass opens with: *what should I
pick up?* It ranks what the beat and its notebooks already record — load-
bearing claims whose bar is unmet (`in-flight`), commissions dispatched and
not returned (`commissioned`), forecasts at their date and questions off
dormancy (`due`), the open-question roster, and un-graduated threads by triage
score — each row carrying the reason it is there. Computed, never stored, like
triage. Order is deterministic within a lane, so two agents reading one corpus
choose the same item. A directory under `notebooks/` that cannot be read is
*reported*, never skipped: to the caller, "skipped it" and "found nothing in
it" look identical, and only one is a reason to go look.

This exists because re-grounding was the measured cost of running a corpus on
a loop — orienting cold in a 507-page notebook ran ~40K tokens of generated
views before any research happened, and every pass paid it again.

**flip does not run the loop, and holds no cadence.** A harness — a cron job,
an agent runtime, a person at a terminal — decides when to wake, what budget a
pass carries, and whether its authority is real; `cadence:` records the
intent so the harness and the agent read one policy instead of two. The
contract a harness needs is small: invoke something, read `flip beat next
--json`, do the work, and leave the ledgers as the receipt. Nothing in this
section names a runtime, and nothing in flip schedules anything.

Deliberately not here yet: **pass accounting**. A mission's `materiality`
prose is exactly the kind of anti-gaming rule that ought to be machine-checked
— a pass that edited a status and called it progress should be visible as one
— but deriving that honestly from the event log needs a session receipt this
version does not define, and a check that guessed would give false confidence
about the thing it exists to doubt. See §19.

## 15. Tooling — the flip CLI

Small, boring, filesystem-only core; **no network calls and no LLM calls in
the library**. Fetchers are pluggable externals. Dependencies: click, PyYAML
(reading human/editor-authored frontmatter faithfully outweighs dependency
purity; flip's own writer emits a deterministic strict subset).

Two global options precede any subcommand: `--notebook <path>` (env
`FLIP_NOTEBOOK`) pins the notebook root instead of walking up from the current
directory — refusing loudly if the pin and the directory disagree — and
`--actor <who>` sets attribution for the command, overriding `FLIP_ACTOR`
(precedence: `--actor` > `FLIP_ACTOR` > detected default). There is no other
actor flag.

```text
flip cli [--json]                    # compact map of every command (group path,
                                     #   purpose, key flags), generated from the tree
flip config init                     # write a starter config.toml (bundled flip-fetch web lane)
flip config show [--json]            # the lanes configured on this machine — what flip
                                     #   can actually run, and the command behind each
flip new <slug> --kind <profile>     # scaffold manifest + notebook.md (auto-binds
                                     #   under a workspace root)
flip add-source <url|doi|file|->     # capture: fetch/copy → raw/, hash, provenance,
                                     #   open a references/ page at grade "?" (--via <variant>)
flip add-source <target> --record    # the ladder's terminus: a citable page for a
            --note "<rungs tried>"   #   document that is out of reach (§5.1, thin)
flip extract <id> [--via <lane>]     # derive sources/text/<id>.txt from custody via
            [--method <m>] [--force] #   an [extractors] lane; one derivation row per
                                     #   run, raw/ untouched (§5.5)
flip find "<question>"               # research: list candidate leads (--capture <n>)
flip ask "<question>"                # research: cited synthesis → sessions/raw/ (a grade-C lead)
flip recall "<question>"             # knowledge: read what we already hold locally
flip grade <id> …                    # record judgment on a source page
flip grade <id> --explain            # why it derives that letter; writes nothing
flip source retitle <id> "<title>"   # rewrite a capture's title, YAML quoted
flip log "<text>"                    # append a work-log event (+ regen log.md)
flip decide|pass|question …          # decisions/questions pages; passed ledger
flip question note|close|dormant|    # the question journey (§7): evidence accretes,
              reopen …               #   honest ends, review dates, reopen triggers
flip claim add|status|list …         # claims pages; verification bar enforced
flip claim derives add|rm …          # derivation edges: what a claim rests on (§7)
flip commission add|status|list …    # contract pages: universe/stop/does-not-redo (§7.4)
flip session start|end …             # session pages
flip show [--hot|--claims|--stale]   # computed views (--json for agents)
flip open <ref>                      # resolve a ref (A3, recipes:A3) to its page path
flip resolve <ref> [--json]          # same resolution with provenance: id, handle,
                                     #   path, notebook root/slug, uid, title (§9)
flip rename <id> <new-slug>          # move a page + rewrite links notebook-wide
flip ws init|list|add|rename|rm      # workspace table: bind handles to notebooks (§18)
flip ws show [--open|--claims|--json] # merged roster across bound notebooks (§18)
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
                                     #   links.beat '#' → ':'); scans PAGES too —
                                     #   a current manifest over pre-0.8 source
                                     #   tuples is still work to do (§5.4)
flip export bag|csl|okf|json|ro-crate # projections (§17); json = flip-render/1
```

`flip claim verify <C#> --method …` records a verification (§7);
`flip question repose <Q#> "<text>"` re-poses append-only (§7).

### Integration roles (pluggable externals)

flip shells out to external tools through a small set of **roles**, each a
namespaced table in `~/.flip/config.toml` and a thin command protocol. flip
defines the protocol; the tools that fill a role live only in user
configuration, never in the package. Placeholders: `{url}` the target as
given · `{id}` the target with a leading `doi:` stripped · `{query}` a
research/recall question · `{dest}` the capture directory · `{src}` a raw
artifact to extract from · `{out}` a text derivative's destination. Commands
that write files receive `{dest}`/`{out}`; stdout-only commands may omit it and
their stdout is preserved. The library makes **no network or LLM calls itself**
— it only runs what you configure.

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
  flip may not know what fills a lane, but it may **read the operator's config
  back to them**: `flip config show` lists the configured lanes and the command
  behind each, and a capture that comes back empty-handed names the lanes and
  kinds that exist on that machine (§5.1). This is the only honest way to point
  an agent at tooling flip is forbidden to name — and it is the moment to say
  that flip wires exactly ONE verb of whatever fills a role, so a tool with more
  surface should be asked directly and its result handed back through
  `flip add-source`.
- **`[extractors]` — extract.** Raw bytes → a readable text derivative
  (§5.5). `flip extract <id>` routes by **media family** — `pdf`, `html`,
  `docx`, `audio` — because the input format picks the tool, not the source
  kind: a PDF is a PDF whether it was captured as a paper, a file, or a
  dataset. Same config forms as `[fetchers]` (bare string, inline table, named
  variants via `--via`), and a variant named after an extraction method
  supplies that method. **Nothing is bundled and there is no default lane**: a
  stdlib-only web GET can ship inside flip, a PDF/OCR toolchain cannot, and the
  package must not carry an opinion about PDF libraries. The starter config
  carries a commented stanza; an unconfigured lane errors with the operator's
  own file path and a stanza to paste. A lane that exits 0 with no text is an
  *empty extraction* — a finding about the document, not a broken config — and
  the refusal, like an empty capture's, reads the operator's other lanes back
  to them.
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

Two of those keys are trust boundaries, not pass-throughs. **`strategy` is a
claim about the capture method and is validated against the §5.1 vocabulary
at the boundary** — the same check `--strategy` faces — because what
fetchers actually report outside the vocabulary is their own name (a
measured corpus held `direct`, `googlebot`, `pdf`: tool trivia, not
methods), and the tool's name already lands in `tool`. An out-of-vocabulary
claim is refused with the vocabulary in hand, not recorded for doctor to
flag later.

A refusal is not a failure, and the ledger must not say it was. The
acquisition succeeded — the fetcher looked and delivered — so the capture is
logged with status **`refused`**, carrying the files it fetched with their
hashes and the word it reported. Recording the bytes is what keeps them from
becoming orphan custody the operator can only clear by hand; `refused` is
what keeps them out of every consumer that walks the ledger for captures.
No entity page is opened, so nothing can cite them, and the refusal names
where they are so the operator can re-run or delete after fixing the fetcher.

**A fetcher that makes no claim records no method**: the
provenance row simply carries no `strategy` key, and fidelity derives
`unknown` (§5.1). Absence is the honest record — an earlier fallback
invented a placeholder word here, which put a claim nobody made into the
ledger and made flip mint findings its own doctor then flagged (85 of them
across one measured corpus). And a document is never accepted as an envelope
field: binary payloads found in an envelope's content strings are
materialized to their own file at capture (§5.1) — the envelope carries
metadata; the document lands as itself.

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
| text extractors (PDF, OCR, transcription) | `[extractors]` config keyed by media family + `tool`/`cmd`/`method` in `derived/_derivations.jsonl`; nothing bundled, no default lane — the `method` vocabulary (§5.5) travels, the tool name does not |
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
- **`flip export json [--out <path>|-]`** — the **`flip-render/1`** JSON
  projection: one stable, versioned, deterministic view of the notebook
  (identity; sources; claims incl. `verifications`; questions incl.
  `formulations`; decisions; session summaries; a log tail) for renderers and
  site generators. A *projection*, not an API — renderers get stable ids
  (`C7`, `A3`) to anchor and link back, and detect staleness by comparing a
  render's recorded `uid`+`updated` against the live notebook. Policy-filtered
  exactly like `export okf`: refuses unless `visibility: public` or
  `--include-private`; when `source_trail_public` is false, custody detail
  (titles, URLs, capture times, sha256 fixity, the whole work log) is withheld
  to judgment stubs (grade / independence / freshness) — anything derived from
  withheld data is withheld data. Deterministic key order and id-sorted
  entities make it diffable; only `generated` varies.
  **`flip-render/2`** is a superset (`--render-version 2`): support tuples,
  pipeline and provenance state on sources; `value`/`unit`, `absence`, and
  `derives_from` on claims; question journey keys (`closed_reason`,
  `review_by`, `reopen_when`); `forecasts`; `commissions` (§7.4 — the
  `consumed` receipt rides only with the full source trail, following the
  sessions/log policy: it is free text about what a run consumed and can
  name work-trail material the same export withholds); `work` (§10); and
  **`drafts`** (§11) — both the flat shape and
  the versioned `drafts/v1/` shape, with a `current` symlink skipped so a
  version is never emitted twice. `drafts` rides the private lane only: it is
  populated under `--include-private` and empty otherwise, because drafts are
  unfinished prose that `export okf` already withholds from outside-facing
  bundles, and going public must not publish them. The key is always present
  under /2 so consumers can iterate without a key check.
  One vocabulary note for `flip-render/1` consumers: the question `status`
  value domain widened at profile 0.9 (`closed`, `dormant` join
  `open`/`answered`); /1 keeps its shape byte-stable and never gains the
  interpreting keys, so a /1 consumer must treat any status other than
  `open` as settled work rather than assuming not-answered means open.
- **BagIt** bag for cold archival (`flip export bag`).
- **CSL JSON** from references for citation managers (`flip export csl`).
- **RO-Crate** envelope, **W3C Web Annotation** anchors: future projections.

### What travels, and import

Identity travels with the bundle; local state does not. `uid` and `origin`
ride in the root `index.md` frontmatter, so every export and bag carries
them; `.flip/` (id reservations, the workspace table, the derived view
cache — §10) and workspace handles never ship — the receiving side chooses
its own handle.

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
- `flip ws show [--open | --claims] [--json]` — the merged **roster** (a
  computed view over existing data, no new ledger): across every bound
  notebook, its kind/status/updated-age plus its open questions (with
  re-pose counts) and load-bearing claims still below the bar with no
  gating verification. `--open`/`--claims` narrow to one lane. `ws list`
  stays the plain binding table; `flip new` under the workspace root
  auto-binds the fresh notebook (slug-derived handle, `-2` on collision).

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
  profiles). OKF v0.2 moved toward flip — `sources` with credibility
  signals, `generated`, `verified` are core now — which sharpens the
  question: the still-open remainder is custody (local bytes, hashes at
  capture), explicit grading, corroboration bars, and negative evidence.
- **Obsidian plugin** — thin metadata surface over `flip … --json` (§12).
- **OCR/transcript quality provenance**; **corroboration graph** (shared
  upstream origins detected); **migration adapters** for pre-flip notebook
  corpora.
