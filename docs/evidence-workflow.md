# Evidence workflow

This is the detailed operating guide for evidence inside a flip notebook. flip
keeps research honest: every source you rely on is captured locally and
hashed, every judgment about source quality is recorded, every load-bearing
claim is linked to sources and gated before it can be called verified, and
the whole trail is plain files in git. The notebook is a conformant OKF v0.2
knowledge bundle — any markdown tool can browse and edit it.

Start with [Getting started](getting-started.md) for installation or
[CLI quickstart](quickstart.md) for the first successful notebook. This page
starts once a notebook and work session already exist.

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

**When the claim is *about* a source, cite it with `--about` instead.** A
claim like "the rebuttal never mentions Persson" is made true or false by the
rebuttal; a second source could only be a second *reading* of the same
document, which is not a second path to the fact. So a subject citation never
counts, the claim carries **no corroboration number at all** (`n/a (subject)`,
never `0` — absent means the axis doesn't apply, not that the evidence is
thin), and what it owes instead is an attribution test anyone can re-run
against the same bytes:

```bash
flip claim add "The rebuttal answers Ballarini & Sloman (2017), not Persson" --about P1 --load-bearing
# C2 asserted · sources: P1 · corroboration: n/a (subject)
flip claim test C2 --probe attribution --error "…" --would-detect "…" --if-absent "…" \
  --against P1 --result survived
```

**Show** the hot view — the resume-here screen, computed from the pages and
ledgers:

```bash
flip show            # open questions, claims needing work, recent log, latest session
flip show --claims   # all claims grouped by status
flip show --stale    # what went cold
```

Along the way, keep the trail: `flip log "hit a wall on X"` for the work log,
`flip decide` for resolved forks (the *why* is the payload), `flip pass` for
things considered and rejected, `flip question add` for open
threads, and `flip session start`/`end` around each LLM run or research
sweep. Questions have a whole journey of their own — the next section after
positions covers it.

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

## A position, and what was asked of it

`status` tracks what is *known* about a claim. It cannot say that you are
working from one ahead of its evidence, or that an audience holds something
this notebook rejects — and forcing either through the status flattens them
together, so a claim whose cited paper turns out not to contain it and a claim
nobody has ever tested both sit outside `verified` and read identically. Two
append-only lists on the claim page keep them apart. Both are optional; a
notebook that doesn't use them never grows the keys.

**What was asked of it** — `flip claim test` is where a test that *found* the
error goes, which `flip claim verify` structurally cannot record, since a
verification is a confirmation:

```bash
flip claim test C1 --probe attribution \
  --error "the cited table does not contain this figure" \
  --would-detect "the number is absent from the extracted text" \
  --if-absent "the figure appears in row 14 as stated" \
  --against F2 --result survived
# C1 · attribution test survived (severe) · exposure: severely-tested
```

A test is **severe** only when four things are on the record: the error it
looked for, how that error would have shown up, what you would have seen
*instead* had the error been absent, and what did the testing. A probe that
fires whether or not the error is there discriminates nothing, however
carefully it was run, and `--if-absent` is the field that says so. Anything
less reads `bent` — bad evidence, no test — and that is one verdict rather
than the bottom rung of a ladder. The three probes (`attribution` ·
`substance` · `scope`) are separate because each has a different repair:
failing to find the claim in its source says nothing about whether the world
is that way.

**What is done with it, and by whom:**

```bash
flip claim stance C1 pursuing --because "explains the 2021 discontinuity nothing else does" \
  --falsifier "the discontinuity survives in districts that never changed reporting"
flip claim stance C1 holding --because "reported consistently in interviews" \
  --holder "district administrators" --source A7
# C1 · holding (held by district administrators) · exposure: severely-tested · 2 stance(s) on record
```

`pursuing` and `rejecting` are refused without a `--falsifier`: a position
worked from is admissible insofar as it predicts something that could come out
the other way, and flip asks for the prediction least likely to hold if the
position is wrong. It cannot audit whether your falsifier is any good and
doesn't pretend to — the falsifier is the promise, `flip claim test` is the
receipt. `--holder` defaults to the reserved value `notebook`; naming anyone
else records a belief the notebook does **not** share, so its own `rejecting`
and a population's `holding` live on one page without overwriting each other.

**`exposure` is derived from the test record and never stored** — the same
discipline as the grade, and printed with its whole derivation:

```bash
flip claim exposure C1
# C1 · exposure severely-tested (derived, never stored) · status asserted
#   because: a test that would probably have caught the error ran, and did not catch it
#   tests on record:
#     attribution · survived · severe — named the error, says how it would have shown up, …
#   notebook stance: pursuing — explains the 2021 discontinuity nothing else does
#     would be moved by: the discontinuity survives in districts that never changed reporting
#   next: severely-tested is the ceiling here; corroboration is a separate axis
```

The five readings are `bent` · `severely-tested` · `misattributed` ·
`refuted` · `untestable`. `misattributed` is deliberately silent about the
world: being wrong about what a source says is not a verdict on the fact. A
claim nobody has tested reads `bent` with that as its stated reason, not a
neutral-sounding default — the onus is on whoever made the claim, and nobody
has discharged it yet. Exposure can only *close* the verification gate, never
open it: `verified` is refused on a `misattributed` or `refuted` claim
whatever the corroboration count says, because a test that went looking for
the error and found it outranks a count of sources agreeing.

**Letting go is comparative.** There is no route to `status: superseded` that
doesn't name the successor:

```bash
flip claim supersede C1 --by C2 --because "C2 explains what C1 did and the 2019 case too"
# C1 → superseded by C2 · C2 explains what C1 did and the 2019 case too
```

That writes `superseded_by`, registers the two as rivals, and sets the status
in one move (`flip claim rival` declares the comparison on its own). A bare
`flip claim status C1 superseded` is refused, and the refusal names the honest
alternatives: `retracted` if the notebook simply withdraws it, or
`stance rejecting` if it is wrong and still worth keeping as data.

## The question journey

A question is not a to-do item that flips to done. Real pursuit accretes
evidence between reformulations, produces answers narrower than the ask,
parks and resumes, and sometimes ends without an answer at all. The page
records all of it (SPEC §7.2):

```bash
flip question add "What's driving the enrollment decline?" --resolves-via "NJ DOE fall snapshot"
# Q1 open · … · watches: NJ DOE fall snapshot

flip question note Q1 "charter transfers explain about half" --answers narrower --source F2
# Q1 evidence noted (open) · answers: narrower
```

Evidence lands on the question's page as a dated section **without closing
it** — `--answers as-worded | narrower | adjacent` is the scope verdict,
and a narrower answer on an open question is exactly the honest state. An
empty probe is recorded WITH its cause, because a single zero-yield round
is indistinguishable from saturation:

```bash
flip question note Q1 "county registry search returned nothing" --zero-yield corpus-gap
```

Re-pose when the question itself sharpens (`flip question repose Q1
"which districts lost K-5 enrollment to charters since 2023?" --sharpened
scope`) — the old formulation is preserved, never overwritten. And a
question has more honest ends than answered:

```bash
flip question close Q1 --reason split         # or: yielded | counter-example | dead-end | superseded
flip question dormant Q2 --until 2027-01-15   # parked; `flip show` resurfaces it when due
flip question answer Q3 --note "aging out + transfers" --reopen-when "2026-27 fall file posts"
flip question reopen Q3 --because "the fall file posted; totals restated"
```

Answers carry their un-stop conditions: `flip show` lists armed
`--reopen-when` triggers, and reopening restores the question with its
whole journey — the old answer included — still on the page.

Two companions to the journey: an **absence claim** makes "looked and
found nothing" a citable assertion carrying its search coverage
(`flip claim add "no district-level FOIA release exists" --absent-from
named_surfaces --surface "state OPRA portal" --surface "district sites"` —
the null's weight IS its coverage), and a **commission** writes bounded
follow-up work as a contract *before* dispatch — input universe, stop
condition, does-not-redo boundary — so continuation runs consume prior
output instead of re-searching it (`flip commission add … --universe …
--stop … --does-not-redo … --for Q1`).

## Keeping the conversation

Claims and graded sources are the residue of thinking, not the thinking. When
the position actually got built in a conversation, keep the conversation:

```bash
flip session transcript landscape-scan --file ./conversation.md \
  --participant human:marc --model claude-fable-5
# sources/raw/T1.md  (120 lines)
# captured as T1 · references/conversation.md · linked from sessions/…-landscape-scan.md
flip transcript excerpt T1 --lines 88-104 --label relevance-null
# T1§relevance-null · lines 88-104, 34 words, sha256 234e7b313e37
```

The transcript enters under ordinary custody — immutable bytes, a hash, one
capture row — with method `human-in-loop`, because a person was in the
conversation and handed flip the file. A claim then cites `T1§relevance-null`
and travels with the words it came from; the quote is read out of the capture
and hashed, never taken from you, so a pinned passage is always the words it
says it is. Several passages of one conversation are several citations and
**one** source, and only the source reaches corroboration. `flip transcript
list` shows what is pinned and `flip transcript unpin` removes one — refused
while a claim still cites it, since labels are load-bearing once cited.

A claim about what was *said* in the conversation is `--about` it: a
conversation is the only witness to itself.

## The passage, not just the document

Any held source can carry pins the way a transcript does. Pin the words a claim
rests on, by quote or by line range, and cite the pin:

```bash
flip source passage pin F2 --label surplus --quote "setting aside \$5,585,576"
# F2§surplus
#   line 41, 3 words, sha256 9f2c…
#   pinned on the text derivative (…, text-layer) — a derivative: …
flip claim add "The audit sets aside \$5,585,576." --about F2§surplus
flip source passage read F2§surplus --json
```

The quote must occur in the held copy, and a miss names the nearest match. The
pin records which copy it read — the raw capture, or the text derivative and
the extraction that made it — because extraction can drop content, and the
SHA-256 of the words and of that copy. Every read re-derives the words and
checks them; doctor reports a pin whose copy is gone (`unbacked-excerpt`) or
whose words moved (`excerpt-drift`, repaired with `--relocate` when the same
words are still there).

When one source republishes another, record it, and the two count once:

```bash
flip source origin A15 --republishes A14 --because "same wire story, byline and text"
```

A check made by applying a written rule names it with `--basis
<kind>:<id>@<version>#<digest>` on `flip claim verify|test|status`. The basis is
stored and evented; it never moves a gate.

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

## Next

- [Integrations](integrations.md) — URL/DOI capture, extraction, and research lanes.
- [Migration](migration.md) — upgrading older notebooks.
- [Obsidian](obsidian.md) — use the notebook as a vault.
- [Agent reference](agent-reference.md) — complete lineage contract and recipes.
- [SPEC.md](../SPEC.md) — the full format.
- `flip export bag` (BagIt archival), `flip export csl` (citations for
  Zotero and friends), and `flip export okf` (an outside-facing copy of the
  bundle, honoring visibility policy) when a notebook needs to travel.
