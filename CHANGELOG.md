# Changelog

All notable changes to the flip spec and tooling are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.18.0] — 2026-08-12

The question-journey release (profile 0.9, design receipts in the
project's own notebook). Everything here promotes what a month of
manual, explicitly-guided pursuit practice already did by hand — dated
evidence updates on open questions, scope verdicts, reopen conditions,
coverage-scoped nulls, four-field commission contracts — into typed,
doctor-checked records, informed by a literature/code review of how the
field pursues, stops, and grades research questions. Hardened by an
adversarial review pass before merge: eight findings confirmed with live
repros (a commission status command that could mutate foreign entity
pages; doctor asserting phantom derivation edges; hand-edited review
dates parking questions forever), all fixed, each pinned by a regression
test — see the Fixed section.

### Added

- **The question journey.** A question page can now tell its whole story:
  `flip question note Q#` accretes dated `## Evidence` sections without
  touching status — `--answers as-worded|narrower|adjacent` records
  whether evidence answered the question *as worded* (a narrower answer
  stays on an open question instead of closing it), and `--zero-yield
  saturated|bad-reformulation|corpus-gap|entity-collision` records an
  empty probe WITH its cause, because a single zero round is
  indistinguishable from saturation and only tagged zero rounds may count
  toward stopping. `flip question close --reason
  split|yielded|counter-example|dead-end|superseded` records the honest
  ends that aren't answers; `dormant --until` parks with a review date
  (`flip show` resurfaces it when due); `--reopen-when` on answer/close
  arms written un-stop conditions (`flip show` lists them under REOPEN
  TRIGGERS ARMED), and `reopen --because` restores open with the whole
  journey — old answer included — still on the page. `repose` gains
  `--sharpened scope|falsifiability|decomposability|evidence-anchored`
  (+`--note`): instrumentation on the formulation history, recorded and
  never scored.
- **Absence claims.** `flip claim add --absent-from
  corpus|named_surfaces|world [--surface …]` makes "looked and found
  nothing" a first-class claim carrying its search coverage — the null's
  evidentiary weight IS its coverage, the same rule the passed ledger
  already enforced. Doctor's `world-absence` names a load-bearing absence
  scoped to `world` (no search can witness one).
- **Derivation edges.** `flip claim add --derives-from C#` / `flip claim
  derives add|rm` declare what a claim RESTS ON (cycles refused). Doctor
  walks the chain: `inherited-unsupported` surfaces every ancestor a
  load-bearing claim leans on that cannot carry it; `dangling-derivation`
  flags edges to missing pages.
- **Commission contracts.** `commissions/<slug>.md` (ids K#): bounded
  follow-up work written as a contract before dispatch — input universe,
  deliverable, stop condition, does-not-redo boundary, all required;
  optional ROI band whose low bound is the quoted expectation. Lifecycle
  `proposed → dispatched → returned|declined`; returns carry `--consumed`,
  the receipt that keeps continuation chains auditable. Nothing
  dispatches; pages record contracts and outcomes.
- **Render contract.** flip-render/2 gains `commissions`, question journey
  keys (`closed_reason`/`review_by`/`reopen_when`), and claim
  `absence`/`derives_from`; render/1 stays byte-stable.

### Changed

- Profile `flip:` 0.8 → 0.9 (all additive; `flip migrate` restamps a 0.8
  notebook without touching pages). Question statuses extend to
  `open|answered|closed|dormant`; `questions list` gains `--status`.
- flip-render/1 keeps its shape byte-stable (now pinned by contract
  tests), but the question `status` value domain widened: /1 consumers
  must treat any status other than `open` as settled rather than
  assuming not-answered means open (SPEC §17 note).

### Fixed

All from the pre-merge adversarial review (8 confirmed / 0 refuted):

- `flip commission status` refused non-commission pages — a typo'd id
  (H1, C1) was handed whatever page resolved and mutated it. K#-shaped
  ids required at the CLI; type checked at the module.
- `answer` refuses closed questions (reopen first — the mirror of close
  refusing answered), drops a dormant page's stale `review_by`, and logs
  a `question-answer` event like every sibling transition.
- `dangling-derivation` fires only on the claim whose own `derives_from`
  carries the unknown id; doctor no longer asserts phantom edges on
  descendants with a suggested fix that fails.
- Doctor audits the new vocabularies: question status and closed_reason
  (`bad-enum`), `undated-dormant` for missing/unreadable review dates,
  commission status, commissions/ id integrity, absence scope
  (`bad-enum`) and `unscoped-absence` (beyond corpus, no surfaces).
- Views degrade loud: an unknown question status stays on the roster
  instead of vanishing from every surface; an unreadable `review_by`
  counts as due-now instead of lexicographically parking the question
  forever; the root index.md lists commissions/ so bundle consumers can
  reach the pages by link.
- `unsupported_reason` counts evidence via `evidence_ids` (dual-role
  citations collapse subject-wins, agreeing with corroboration);
  `--unit` without `--value` is refused before id allocation (no more
  permanently burned C#s); a kind contract may require commissions/;
  `dormant --until` validates real calendar dates; the `consumed`
  receipt rides only with the full source trail; commission render nodes
  carry `slug`.

## [0.17.1] — 2026-08-12

Both entries below came out of one research session that went wrong in the
ordinary way: an agent did eight fetches, read eight summaries, and wrote
claims off them before anything entered the notebook. The operator had to
notice and say so. Neither the rule nor the tooling was missing — the rule
reaches the agent only *after* it has decided to use flip, which is the
decision that already went wrong, and one capture lane silently refused every
identifier it was given.

### Fixed

- **`{id}` now strips every identifier scheme, not just `doi:`.** It stripped
  `doi:` and passed everything else through verbatim, so `arXiv:2606.15136`
  reached the resolver whole. A resolver handed an unrecognized string
  title-searches it, finds unrelated papers, downloads none, and exits 0 —
  which flip correctly reported as `EmptyCapture`, i.e. *as a finding about
  the document*. A clean exit with no bytes is the most expensive failure
  mode there is, because it reads as evidence: the notebook records "searched,
  gone" about a paper sitting at a public URL. `arxiv:`, `pmid:`, `pmcid:`,
  `hdl:`, `isbn:` and `urn:` now strip too, case-insensitively, and an unknown
  prefix is still left alone — `{id}` is also how a bare accession reaches a
  resolver. `{url}` continues to carry the target exactly as given, because
  the provenance row has to say what was asked for. New `integrations.bare_id()`.

### Added

- **A custody hook, shipped with the plugin** (`hooks/hooks.json`). flip's rule
  was already written well; it was written in the wrong place. The hook moves
  it to the moment of the act, and is a silent no-op outside a flip notebook:
  - `PreToolUse` on WebFetch — once per session, names the notebook and the
    three ways a fetched thing legitimately enters it (`add-source`,
    `add-source --record`, `pass`), and warns that a summary of a document is
    not the document.
  - `PostToolUse` on WebFetch — records the URL.
  - `Stop` — once per session, lists URLs read this session that appear in
    neither `sources/_provenance.jsonl` nor `references/`, and holds the turn
    open until each is captured, recorded, passed, or declared background.

  Deliberately **not** hooked: WebSearch. Discovery is capture-free by doctrine
  (SPEC §5) — a search returns leads, and a lead is not evidence. Matching is
  loose on purpose (arXiv id, DOI, then host+path), so the report under-reports
  rather than over-reports: a false "you didn't capture this" is what gets a
  hook switched off, and a hook that is off enforces nothing.

## [0.17.0] — 2026-08-10

Everything here came out of using flip for real research, and it is all one
theme: a notebook could say whether a claim was true yet, and almost nothing
else. It could not say a position was being *pursued* ahead of the evidence,
or that an audience holds something this desk rejects, or that a probe went
looking for a specific error and failed to find it. It could not say a claim
was *about* a document rather than supported by one. It kept the residue of a
conversation and threw away the conversation. And `sources/text/` — specified
since the first draft — had nothing that wrote it, so getting quotable text
out of a captured PDF happened outside flip, unlogged.

**No migration, and no on-disk change.** Every key added here is optional and
absent by default; a 0.16 notebook reads identically under 0.17, and each new
axis is silent in a notebook that does not use it.

**Three gates got stricter**, which will change outcomes for a notebook that
uses the new keys: `flip claim status <C#> superseded` is refused in favor of
`flip claim supersede --by --because` (letting go is comparative — name what
beat it); `verified` is refused when a severe test found the error
(`exposure: misattributed` or `refuted`) whatever the corroboration count says;
and a claim whose every citation is a `subject` reports no
`independent_corroboration` at all rather than `0`, so a consumer reading that
key must handle its absence.

### Added
- **Citation roles — what a citation is FOR** (SPEC §7). A claim's `sources`
  entries carry a `role`: `evidence` (the default) or `subject`. The role lives
  on the **citation**, not on the claim and not on the source page, because the
  same paper is what one claim is about and a witness for the next one.
  - **The problem, from real notebooks.** `corroboration_count` counts cited
    sources whose page is judged and `independent`. That bar is sound for a
    claim about the world — agreement between causally *independent paths* to
    one fact is evidence — and unsound for a claim about a document. A claim
    that "the rebuttal answers Ballarini & Sloman (2017) and never mentions
    Persson" cites the rebuttal, and the rebuttal is not evidence *for* the
    claim: it is what makes it true or false. A second source could only be a
    second *reading* of the same document — an independent reader, not an
    independent path — which addresses reader error where corroboration checks
    source error. Same shape wherever a claim rests on a transcript excerpt for
    what was said in the conversation: there is no second witness and there
    never can be.
  - **The count goes ABSENT, not to zero.** A claim citing something, all of it
    `subject`, carries no `independent_corroboration` key at all. `0` there is
    the wrong number the `uncountable_sources` doctrine already names — it
    reads as *the evidence is thin* when the truth is *this axis does not apply
    here*, and a wrong number is worse than a missing one because only the
    missing one prompts a look. A claim citing **nothing** keeps its `0`: the
    question applies there and nobody has answered it. Absent means
    inapplicable, never unmet. `flip claim add|status|source add|rm` and
    `flip show --claims` print `corroboration: n/a (subject)`, `flip ws show`
    the same, and the JSON projections omit the key (render/2 adds
    `subjects: [ids]`, so a renderer can say why it is missing).
  - **The audit that replaces it is an `attribution` test** (§7.1), which is
    exactly the check anyone can re-run against the same custody — the right
    ask where a second source is impossible in principle rather than merely
    absent. A severe, surviving one against every cited subject clears the
    `verified` gate in place of the count. Nothing else is loosened: a claim
    with any `evidence` citation faces the ordinary bar, A2's
    adversarial/recomputation path is untouched, and a severe attribution
    *failure* still refuses `verified` through the exposure gate first.
  - **`--about`, one spelling.** `flip claim add --about <ID>` and
    `flip claim source add <C#> --about <ID>` cite the source a claim is about;
    bare `--source`/positional ids stay evidence. `ID:subject` was the
    alternative and lost on a collision: `handle:ID` already means a
    workspace-qualified alias in flip. `--about` on a source the claim already
    cites **re-roles** it, which is the one-command fix for an existing page.
  - **doctor.** `unaudited-claim` on a load-bearing claim with a subject
    citation and no attribution test on record — the audit that IS available,
    not taken — worded so a second source is never the ask; `under-verified`
    and the workspace roster stop demanding corroboration of a claim that can
    never have it; `corroboration-drift` names a stored count on a subject-only
    claim as a key to drop rather than a number to refresh; `bad-enum` on an
    unreadable role, which still reads as `evidence` so a typo can never
    quietly excuse a claim from the bar; and `misattributed-citation` inverts
    its advice on a subject — do **not** unlink the document the claim is
    about, because a claim without it has nothing left to be true of.
  - **No migration.** `evidence` is the default and the meaning of the key's
    absence, so every citation ever written already has the right role and
    every existing page round-trips byte-identical.
  - **The honest limit**, stated in SPEC rather than buried: a role is
    authored, so `subject` can be used to duck a bar. flip checks the
    attribution test is *present*, never that it is true — the same limit the
    stance layer already declares. What it can do is make the role legible on
    the page and in every export, and name the untaken audit.

- **Text derivatives — `sources/text/` finally has tooling** (SPEC §5.5).
  `sources/text/` ("readable derivatives of raw/, 1:1 by source id") has been in
  §3 since the first version of the spec and nothing ever wrote it;
  `derived/_derivations.jsonl` ("inputs → tool/cmd/params → outputs with hashes,
  a deliberately small PROV profile") was specified and unused. Getting text out
  of a captured PDF was a manual scramble outside flip — a 94-page scanned
  chapter with no text layer took a hand-rolled render-and-recognize shell loop
  that silently produced zero output on the first attempt, with nothing on disk
  or in any ledger to say so.
  - **A fourth integration role, `[extractors]`, verb `extract`**, keyed by
    **media family** (`pdf`, `html`, `docx`, `audio`) rather than by source
    kind: the input format is what picks the tool, and a PDF is a PDF whether it
    was captured as a paper, a file, or a dataset. Placeholders `{src}` (the raw
    artifact), `{out}` (the destination) and `{id}`, with the same rule
    `{dest}` has on a fetcher — **a command that omits `{out}` has its stdout
    preserved**. Same config forms as `[fetchers]`: bare string, inline table,
    named variants reachable with `--via`.
  - **`flip extract <ID>`** derives `sources/text/<ID>.txt` and appends exactly
    one row to `derived/_derivations.jsonl`. `flip add-source --extract` does
    both inline; a capture that lands a document with a lane configured for it
    gets one nudge line and nothing more.
  - **An extraction method is recorded, from a fixed vocabulary** —
    `text-layer` · `layout-text` · `ocr` · `markup-strip` · `structured` ·
    `transcript`. This is the point of the feature. §5.1's discipline applied
    one layer down: **a quotation recovered by OCR is not the same evidence as
    one lifted from the publisher's own text layer**, and a notebook had no way
    to say which. The row already records the actor (`tool`, `tool_version`,
    `cmd`), so `method` is where the method belongs — methods travel between
    deployments, tool names are local trivia. flip never guesses one: a lane
    *named* after a method supplies it, and otherwise no method is recorded and
    doctor asks.
  - **`derivative_fidelity` is derived from the log row, never authored** — the
    same discipline as `capture_fidelity` and `derive_grade`. `text-only` ·
    `thin` (under **25 words/page**) · `empty` · `unknown`. The threshold is
    calibrated rather than guessed: on a measured corpus real extractions ran
    391–994 words/page and silent failures 0–10.8, with nothing in between.
  - **Near-nothing is two distinct events**, mirroring `not-captured` and
    `failed` in the capture log. Zero words raises `EmptyExtraction`, writes a
    `status: not-extracted` row, leaves **no file on disk**, and exits 1 — an
    extractor exiting 0 with no text is reporting a finding about the *document*
    (no text layer here), not a defect in the config, and saying otherwise sends
    the reader to debug a lane that is fine. Under 25 words/page the file *is*
    written, logged `fidelity: thin`, and warned about loudly at extraction
    time, because unlike the empty case it leaves a plausible-looking `.txt`
    behind. Both refusals read the operator's own configured lanes back to them
    (§16) — that is how "go hunt around for an OCR tool" stops being something
    done from memory.
  - **`sources/raw/` is never touched, and a derivative may be overwritten.**
    What makes that safe is the append-only log: every run records inputs (path,
    sha256, bytes), tool + version + the **verbatim command template** + lane +
    method, outputs (path, sha256, bytes, words), pages, words/page, the derived
    fidelity, and `supersedes` — the sha256 of the output it replaces. It is
    also how flip tells its own last output from someone else's work: **a file
    that hashes to no row was written by a person**, and `flip extract` refuses
    it without `--force`.
  - **`flip doctor`**: `thin-derivative`, `unlogged-derivative`,
    `unvocabularied-extraction`, and `missing-derivative` (a captured document
    with no derivative — an expected-until-use notice). The last does not
    consult machine config: doctor reads the notebook, and a check gated on an
    installed lane would go quiet for the reader least able to notice. `derived/_derivations.jsonl` was already in
    `LEDGERS`, so `bad-jsonl` came free.
  - **Nothing is bundled and there is no default lane.** `flip-fetch` can ship
    because it is stdlib-only; a PDF/OCR toolchain cannot, and flip must not
    acquire an opinion about PDF libraries in its package (§16). `flip config
    init` writes a fully commented `[extractors]` stanza — including the field
    notes about pinning an OCR model path, and about checking whether a chosen
    extractor has an opt-in mode that POSTs page images to a remote endpoint —
    and every refusal names the operator's own config file.
- **Stance and exposure — the attitude, separated from the truth-status**
  (SPEC §7.1). `status` is truth-tracking and right for facts, and it fuses two
  things a notebook has to keep apart: what a claim's evidential situation is,
  and what position the notebook takes toward it. The cost of the fusion is
  concrete — a claim whose cited paper turns out not to contain it and a claim
  nobody has ever tested both sit outside `verified` and render identically,
  so a citation failure reads as a hypothesis failure. Three new axes, all
  optional and all silent in a notebook that does not use them. Every framework
  sentence below was read against a captured primary and carries its page;
  where flip departs from a source, SPEC §7.1 says so in flip's own voice
  rather than borrowing the name.
  - **`flip claim test <C#>`** records a test that was run against a claim,
    *including one that found the error* — which `flip claim verify` structurally
    cannot, because `verified:` is OKF v0.2 §5.2's key and its entries are
    confirmations. Each record names the `--probe` (`attribution` · `substance`
    · `scope` — three, because each has a different repair; failing one says
    nothing about the others), the `--error` it looked for, how it
    `--would-detect` it, what it would have shown `--if-absent`, what it ran
    `--against`, and the `--result` (`survived` · `failed` · `inconclusive` ·
    `untestable`). Append-only.
  - **A test is `severe` only when it could have come out the other way.** Four
    authored fields, and each is one sentence of Mayo's: `error`, because a
    severe test is one the claim "probably would have failed, if false *in a
    specified manner*" (SIST p.65); `would_detect` and `if_absent`, the two
    halves of "a very high capability of signaling the error, *if and only if*
    it is present" (SIST p.16); and `against`, so the thing that did the
    testing is locatable. A probe that fires whether or not the error is there
    discriminates nothing, and `--if-absent` is the field that says so.
  - **`exposure` is derived from that record and never stored**, the same
    discipline as `derive_grade` and `capture_fidelity`: `bent` ·
    `severely-tested` · `misattributed` · `refuted` · `untestable`. **`flip
    claim exposure <C#>`** prints the whole derivation, the twin of `flip grade
    --explain`, and on a `bent` claim it prints *which* of the three roads into
    bent was taken — because SIST p.201 asks for "low, along with an
    explanation as to why", and the explanation is the half that gets dropped.
  - **`flip claim stance <C#> pursuing|holding|abstaining|rejecting`** records
    what is *done* with the claim, and by whom. `--because` is always required
    (a stance word alone is an enum without evidence); `pursuing` and
    `rejecting` are refused without a **`--falsifier`** — Peirce's verifiability
    condition, CP 5.197, asking for the prediction that would be "otherwise
    least likely to be true" (CP 2.89). flip cannot audit whether a falsifier is
    any good and does not pretend to; it refuses the stance until one is written
    and asks for the right thing while refusing. The falsifier is the promise,
    `flip claim test` is the receipt.
  - **`--holder` defaults to the reserved value `notebook`.** Naming anyone
    else records a belief the notebook does not share — the notebook's
    `rejecting` and a population's `holding` on the same page, without either
    overwriting the other. A widely-held false belief is a causal force whose
    structure points at interventions, and it belongs in the corpus as data.
  - **`flip claim rival <C#> <C#> --because …` and `flip claim supersede <C#>
    --by <C#>`** — the unit of comparison, and the only route to `status:
    superseded`. Lakatos, p.69: "a degenerating problemshift is no more a
    sufficient reason to eliminate a research programme than some old-fashioned
    'refutation' or a Kuhnian 'crisis'… such an objective reason is provided by
    a rival research programme which explains the previous success of its rival
    and supersedes it by a further display of heuristic power." Nothing here
    fires on a timer; a claim is let go of by naming what beat it. `flip claim
    status <C#> superseded` is now refused, because a bare status change records
    only that the notebook got tired of a claim.
  - `flip claim status <C#> verified` is now **refused when the exposure is
    `misattributed` or `refuted`**: a severe test that went looking for the
    error and found it outranks any count of sources agreeing, and a plausible
    citation is exactly what makes a source countable. Tests can only close
    that gate, never open it — a described test must not be able to verify a
    notebook against itself.
  - `flip claim list` gains `--stance` and `--exposure` filters and shows
    `exposure/stance` on claims that carry the keys; `flip show --claims`, the
    JSON list and the render-2 export carry them too.
  - Seven doctor checks, every one silent on a claim carrying none of the three
    keys: `stored-exposure`, `unpriced-stance`, `misattributed-citation` (a
    claim still citing the source a severe attribution test found it wrong
    about — WARN while active, ERROR once done/published), `unexamined-position`
    (the notebook `holding` **or `pursuing`** a load-bearing claim that reads
    `bent`), `losing-to-a-rival`, `no-declared-rival`, `unsourced-holder`.
  - **No credence lives on a claim**, and the changelog entry says so on
    purpose: the two-object rule stands, and the honest way to price a belief
    is to open the forecast that would settle it (`bears_on: claim:C#`), which
    costs a resolution date and an annulment clause.
- **The §7.1 vocabulary, corrected against its own citations.** The design was
  built on framework summaries nobody had read against a primary, and an audit
  of all five summaries used across this project found an error in every one,
  every error leaning the same way — toward making the framework more
  permissive than its source. Four corrections landed here, and each **removes**
  something rather than adding to it; exposure went from seven terms to five and
  the probe enum from four to three.
  - `untested` and `weakly-tested` were two rungs of a gradient attributed to
    Mayo. She has no gradient. SIST p.5 puts "nothing has been done to rule out
    ways the claim may be false" and a method that "had little or no capability
    of finding flaws with C even if they exist" into **one** verdict: bad
    evidence, no test. Both are `bent` now, which is her acronym, and a test's
    severity is `severe`/`bent` where it was `severe`/`weak` — `weak` read as a
    rung below severe and invited exactly the ladder she refuses.
  - **An unrecorded severity rendered as the neutral-sounding `untested`.**
    SIST p.201: "if it cannot be computed, it's also awful, since the onus on
    the researcher is to satisfy the minimal requirement for evidence… I'll say
    it's low, along with an explanation as to why." A claim nobody has tested
    now reads as the worst state on the axis, with its reason attached wherever
    the verdict appears — in `flip claim exposure`, in the note printed when a
    stance is taken on a bent claim, and in the doctor finding.
  - `contested` is gone. Two severe tests of one probe disagreeing is not a
    stable middle an operator can sit in; at least one of them is not the test
    it claims to be, and Mayo is explicit that the readings assume a test "has
    passed (or would pass) an audit, else these computations go out the window"
    (SIST p.201). A failed audit is the absence of a reading, so it reads
    `bent` with that as its stated reason. A failure recorded by a blunt
    instrument reads `bent` too, for the symmetric half of the same sentence.
  - **The falsifier gate was justified by the wrong Peirce.** It was charged as
    "the economy of research", which cannot gate anything: CP 1.136, immediately
    after "Do not block the way of inquiry", says "there is no positive sin
    against logic in trying any theory which may come into our heads", and CP
    7.220 makes cheapness a reason to give a hypothesis *precedence* "even if it
    be barely admissible for other reasons". Economy is a sort key. The gate is
    CP 5.197's verifiability condition, and it asks for something sharper than
    "what would move you" — which is where it meets Mayo's second severity
    condition coming the other way, and that convergence is the only joint
    result §7.1 claims.
- **Fixed a perverse incentive the design's own test suite certified.**
  `unexamined-position` fired on `holding` and not on `pursuing`, so switching
  the stance word to `pursuing` was the documented way to silence the
  notebook's only warning about untested belief — and `pursuing` was terminal,
  with nothing pointing out of it and no tests required to stay in it. A
  gradient ran downhill toward the design's blind spot. The finding is now
  about the claim's exposure rather than the stance word: both positions fire
  it, the stance changes the advice and nothing else, and the only exit is to
  record a test that could have come out the other way. `superseded_by` and
  `rivals:` make `pursuing` non-terminal in the other direction, by giving a
  pursued claim somewhere to lose to.
- **`flip add-source --record` — the ladder's terminus, written down** (SPEC
  §5.1). A source that cannot be captured may still have to be *citable*. A
  record capture takes no bytes of the document, because none were reachable;
  what enters custody is flip's own record of the source and of the attempt,
  under the new capture method **`record-only`**. It requires `--note` saying
  what was tried and what each rung returned — an assertion that something was
  unreachable is worthless without its receipt — always derives `thin`
  fidelity whatever the record weighs, opens at grade `?` so it corroborates
  nothing, writes `status: recorded` rather than `captured`, and says above the
  fold that the document is not in custody. `flip doctor` names it as a
  `thin-capture` in its own words, labeled expected-until-use rather than as
  breakage. `flip pass` remains the move for a source ruled *out*; a record is
  for one that is real, wanted, and out of reach.
- **Thin captures are loud at capture time, not only at doctor time** (SPEC
  §5.1). A JavaScript shell captured as 200 is the failure that reads as a
  success — same sha256, same ledger row, same page at grade `?`. doctor has
  always named it, but doctor runs later, and by then the thin bytes have been
  cited. `flip add-source` now prints `warning: thin capture` the moment it
  lands, with the file to open, the rungs still *above* the method that ran
  (not the whole ladder recited back), the lanes configured here, and the
  `--record` alternative.
- **`flip config show`** — the lanes configured on this machine and the command
  behind each, `--json` for agents. "What tooling do I actually have here?" had
  no answer short of reading `config.toml` by hand, which is a large part of why
  a stuck agent improvises instead of reaching for a lane sitting right there.
  flip still never names a deployment's tools (SPEC §16); it reads the
  operator's own configuration back to them, and says plainly that each lane is
  one verb of whatever fills it.
- The `notebook-source` skill teaches all of the above — the empty-handed case,
  the four moves, and that internal tools have more surface than the one verb
  flip wires. `notebook-audit` gains the rule that nothing load-bearing may rest
  on a thin capture, in either flavor.

- **Transcripts: the conversation kept, and citable by the passage** (SPEC §8,
  §9). SPEC §8 has always said a session page carries a "pointer to the raw
  transcript when kept" — nothing implemented it, and the gap was not a
  missing file field. Claims and graded sources are the *residue* of thinking,
  not the thinking: a conversation is where a position actually gets built,
  and a notebook that keeps only the conclusions cannot later show anyone —
  including its own author — why the conclusion has the shape it does.
  - `flip session transcript <session> --file <path>` captures the
    conversation under ordinary custody (immutable bytes, sha256, one capture
    row) and gives it a `T#` id, so it is cited like any other evidence. The
    method recorded is **`human-in-loop`**: a person was in the conversation
    and handed flip the file, which `copy` alone would understate. The page
    carries `medium: conversation`, plus `participants`/`model` when given;
    the session page gains `transcript: {id, local}` and a filled
    `## Transcript` section.
  - `flip transcript excerpt T1 --lines 88-104 --label relevance-null` pins a
    named passage. A claim then cites **`T1§relevance-null`** and travels with
    the words it came from. The quote is read out of the immutable capture and
    hashed — never taken from the caller — so a pinned passage is always the
    words it says it is; the label doubles as the page anchor, so a claim's
    `resource` deep-links to it. `flip transcript list` and
    `flip transcript unpin` round out the surface.
  - Excerpt refs **collapse to their base id wherever evidence is counted**: a
    claim resting on two passages of one conversation has two citations and
    one source, and only the second number reaches corroboration. `source_ids`
    keeps its existing contract for every downstream consumer; the new
    `source_refs` is what answers "which words".
  - Labels are stable because claims cite them: re-pinning a label is refused,
    and unpinning is refused while a claim still cites it. `flip doctor` gains
    `unbacked-excerpt` (custody gone), `excerpt-drift` (the stored quote no
    longer hashes — on an immutable capture that means a hand edit), and
    `dangling-excerpt` (a claim cites a label nothing pins, so the citation
    quietly widens from one exchange to the whole conversation).

- **Notebooks show their drafts.** flip-render/2 gains a `drafts` array
  (SPEC §11 and §17), so an internal renderer — an agent site, a review
  surface — can present in-progress prose next to the sources and claims that
  back it. Previously drafts were invisible to every renderer: `work` carried
  notebook.md, root prose and `analysis/`, but nothing reached into
  `drafts/`, so the actual deliverable of a research notebook was the one
  thing a reader could not open. Both shapes ship — the flat files that
  `flip new --kind pursuit` scaffolds, and SPEC §11's versioned
  `drafts/v0/`, `drafts/v1/` — with flat files first, then versions in name
  order, and a `current` symlink skipped so its target is not emitted twice.
  Each entry carries `slug`, `path`, `title` and `body`; a draft with no
  frontmatter is titled from its filename rather than dropped.
  **Private lane only:** `drafts` is populated under `--include-private` and
  empty otherwise. `export okf` already excludes `drafts/` from every
  outside-facing bundle, and a notebook going public should not publish its
  unfinished work as a side effect. flip-render/1 never grows the key.
- **Two more ladder rungs, bundled and needing no external tool** (SPEC §5.1).
  `flip-fetch --method` now selects the capture method, using the same
  vocabulary the ledger records:
  - **`archive-replay`** — a web archive's copy when the live host won't
    serve. Fetches the **raw** snapshot (`…/<timestamp>id_/…`) so custody
    holds the document rather than a rendering of it inside the archive's
    viewer, and records **`archived_at`**: the evidence is from the snapshot's
    date, not today, which is a grading fact. The lookup API rate-limits
    shared addresses hard — observed live while building this — so it falls
    through to the replay path rather than retrying the same endpoint harder,
    and a 404 from the archive is reported as "no archived snapshot" rather
    than a status line.
  - **`publisher-api`** — Crossref for metadata, then Unpaywall for a legal
    open-access full text, then arXiv for arXiv ids. All free, no signup;
    Unpaywall needs `--email` (it refuses without a real address, and the same
    address opts into Crossref's polite pool). When only a registry record is
    reachable it is captured and marked **`status: metadata-only`** — worth
    keeping, not the paper, and derived as `thin` fidelity so doctor says so
    rather than letting it pass as the article.

  `flip config init` ships both as ready lanes. flip had **no** default
  `paper` fetcher before this.

- **The documentation caught up with the code, in the places that had gone
  quiet.** README, AGENTS.md, `docs/quickstart.md`, `docs/internals.md` and
  `llms.txt` had nothing at all about stances, tests or transcripts — the
  module map did not list `stance.py` or `transcripts.py`, and AGENTS.md's
  contract, which is the thing an agent actually reads, said nothing about
  either. AGENTS.md gains a ninth lineage rule (*what you DO with a claim is
  not its status*) and two recipes; quickstart gains the two sections, with
  output copied from real runs.
- **The documentation site was refreshed against 0.17** (`website/`). Three
  new flipbook frames — a severe test, the exposure it derives, and a kept
  conversation with a pinned passage — generated by running the real CLI, so
  the narrative is 19 exchanges and 21 commands rather than 16 and 17. The
  home page states a fifth enforced rule; the spec map gains cards for the
  tests/stance/exposure axis and for citation roles, a sixth lifecycle stage,
  and `sources/text/` credited to `flip extract`; the whole-notebook view
  gains an `exposure` column and renders an absent corroboration count as
  `n/a (subject)` rather than as blank. Stale authored literals that no test
  covers were corrected along the way — the page had claimed OKF v0.1 since
  0.11, and a spec version three releases behind. The site's own notebook
  records the new gate as C7, with the current spec captured under custody as
  F3 and a severe attribution test run against those bytes: the copy it
  already held was the v0.10 snapshot, which could not support the claim.

### Changed
- **`http-alt-representation` stays in the vocabulary but ships no generic
  implementation.** Tested against the hosts that resist rungs 1–2: AMP paths,
  `?amp=1`, print params and `www` stripping all return the *identical*
  failure, because the block is at the edge on the whole host rather than
  per-representation. A purpose-built site-specific lane may legitimately use
  the method; shipping generic folklore that looks like it works would not.

### Fixed
- **Four defects found by using the thing.** All four came out of one
  afternoon's real research in a sibling notebook, and each was a check that
  misdescribed the situation rather than one that failed to fire.
  - `unsourced-holder` **could never be cleared**. Stances are append-only, so
    a foreign stance first written without a receipt and later rewritten with
    one leaves both records on the page — and the check read every record. It
    fired *after* the evidence had been cited, naming a defect that was already
    fixed and recommending the exact command that had just fixed it. Only the
    last record per holder is that holder's current position now; the
    unsourced one still stands on the page, which is what append-only is for.
  - `unaudited-claim` **could not see the tests axis**. It read corroboration
    and `verified` only, so it fired on a claim carrying a *severe attribution
    test* and told the author to "record a check" — which they had, with
    `flip claim test`, a command the message did not mention. A severe test is
    an audit; what it FOUND is `flip claim exposure`'s business, not this
    check's. Silence here is the absence of the thing the check is about, never
    approval. A bent test still buys nothing, per SIST p.5.
  - `missing-derivative` **was silenced by a broken lane**. Any derivation row
    counted as an attempt, including `status: failed`. A misconfigured html
    lane failed twice and doctor then reported nothing missing while nothing
    had been extracted. Only outputs, or a clean `not-extracted` run, settle
    it: the first means there is a derivative, the second is a finding about
    the document. A `failed` row settles nothing, and that distinction was
    already in the format — the check just wasn't using it.
  - **A non-file at the output path is a refusal, not a stack trace.** A lane
    that passes `{out}` to a flag meaning output *directory* creates one, and
    the next run died inside the tool on `IsADirectoryError`, blaming the retry
    for what the first run left behind. `flip extract` now checks the path
    first and names the lane, since that is where the fault is. Neither
    `--force` nor the hand-edit guard covered this: the question is not whose
    bytes those are, there are none.
- `flip claim list` printed each claim's OKF `sources` entries as raw YAML maps
  (`{'id': 'P1', 'resource': …, 'title': …}`) instead of source ids, which made
  the one view built for scanning unscannable at more than one source per
  claim. It prints ids now, like every other surface.
- **A fetcher that comes back empty-handed is reporting, not malfunctioning**
  (SPEC §5.1, §5.2). A configured command that exited 0 having written nothing
  was answered with `fetcher for 'paper' wrote nothing to <dest> and emitted no
  stdout — make sure its command in ~/.flip/config.toml uses the {dest}
  placeholder or emits the captured artifact on stdout`. That is a
  misdiagnosis: the config was fine, the paper was paywalled, and the tool had
  correctly found nothing downloadable. Sent to debug a non-problem, an agent
  in a real session abandoned the configured tooling and improvised — raw HTTP
  calls, a hand-written REST query, and finally two JavaScript shells captured
  as if they were papers. Nothing in the message named a next rung, the record
  option, or `flip pass`, so none of them happened.
  - `integrations.run_capture` now raises `EmptyCapture` (a `SystemExit`
    subclass, so every existing caller is unchanged) for the clean-but-empty
    case, distinct from the failure raised when a command cannot run or exits
    nonzero. Only one of those is anyone's fault.
  - `flip add-source` answers it with the four sanctioned moves: **climb** (the
    rungs above, plus the lanes and kinds this machine actually has
    configured), **ask the tool for more** (flip wires exactly one verb of
    whatever fills a lane — the binary's own `--help` often has search,
    resolution or alternate-source verbs flip never calls), **record it**, and
    **close it** with `flip pass`. The `{dest}`/stdout note survives as a
    parenthetical, where it belongs.
  - The capture log distinguishes the two: `status: not-captured` (ran clean,
    found nothing — a fact about the document) alongside `status: failed` (a
    broken toolchain). Both are rows without bytes and without a page, by
    design; doctor reads neither as corruption.

- **A short handed-over file is no longer reported as a thin capture**
  (SPEC §5.1). `capture_fidelity` inferred "markup" from a missing mime for
  every method except `copy`, so any brief transcript tripped the
  consent-wall/JS-shell heuristic and doctor called a complete capture thin.
  The size test only means something for bytes a *fetch* brought back;
  `human-in-loop` now sits alongside `copy` as handed-over. A declared markup
  mime is still tested whatever the method.

## [0.16.2] — 2026-07-31

### Changed
- **The Claude Code plugin is now named `flip`, not `flip-notebook`.** Install
  it with `/plugin install flip@lyra-forge`. Anyone who installed under the old
  name should remove it and reinstall — Claude Code keys installed plugins by
  name, so the rename reads as a different plugin. Unchanged: the PyPI package
  is still `flip-notebook` (`uv tool install flip-notebook`), and the Obsidian
  plugin id is still `flip-notebook` (`.obsidian/plugins/flip-notebook/`).
- **A stated stance on acquisition conduct** (SPEC §5.1), and `flip-fetch` now
  presents a browser User-Agent. flip's use case is *closely directed* capture
  — a named document a person is about to read, judge and cite — which is an
  extension of manual effort rather than crawling. A UA string is a
  compatibility hint, not an access control; blanket UA blocking is a blunt
  default aimed at bulk scrapers, and directed single-document capture is
  bycatch in that fight. Measured: the old self-identifying string earned a
  `403` from x.com and a timeout from nasdaq.com that a browser UA answers
  with 165KB and 248KB of the documents the user asked for.

  The default fetches **one named document, follows no links, and paces per
  host** across invocations, so an agent looping `add-source` still reads like
  a person rather than a crawler.

  **It is a default, not a constraint.** `flip-fetch --user-agent STRING`
  (the word `identify` selects flip's own name), `--min-interval SECS`,
  `--timeout`, and the `FLIP_FETCH_UA` / `FLIP_FETCH_MIN_INTERVAL`
  equivalents; `flip config init` shows worked alternatives. A deployment that
  needs to announce itself to a partner API, pace far slower for a fragile
  host, or move faster against its own infrastructure sets a policy and owns
  the result. flip enforces no conduct policy over the operator's, and
  authenticated capture of material you legitimately have access to is a
  first-class method (`browser-session`), not a transgression.

  **What does not vary is the record.** `user_agent`, `strategy` and
  `attempts` are written to the capture row as actually used, whatever the
  policy — not a restriction on conduct but the point of the format: a
  notebook that misreported how it got its bytes is worthless to whoever later
  has to trust it, usually its own author. Custody remains distinct from
  republication (§17).

### Fixed
- **The envelope whitelist silently dropped the conduct record.**
  `_harvest_envelope` returns only `ENVELOPE_KEYS`, so `user_agent` and
  `attempts` were written by the fetcher and lost before provenance — the
  capture row read `user_agent: None` while the real string sat in the
  sidecar. Caught by running a live capture end to end, not by the unit tests,
  which were green throughout.

### Added
- **Capture methods: the ladder** (SPEC §5.1). `strategy` in the capture log
  now records **how** the bytes were obtained, from a fixed vocabulary —
  `copy` · `http-get` · `http-alt-representation` · `archive-replay` ·
  `publisher-api` · `media-extract` · `browser-render` · `browser-session` ·
  `self-contained-archive` · `human-in-loop` — rather than which tool ran.
  `tool`/`tool_version` already record the actor. Methods make two notebooks
  comparable when they were built on different deployments; a tool name is
  local trivia, and an unpublishable one if the tool is private.
- **`flip-fetch` climbs rungs 1–2.** Backoff-retry on 429/502/503/504 and
  timeouts, honoring `Retry-After` (capped). A 403/404 is *not* retried — that
  is a decision, and repeating an unchanged refused request is noise; the
  error now points up the ladder instead. Neither is a refused connection or
  an unresolvable name: persistence aimed at the wrong failure is just a
  slower way to give up. `attempts` lands in the ledger when a retry was
  needed, so a flaky source is distinguishable from a clean one.
- **Capture fidelity, derived** — like the source grade, never stored.
  `faithful` · `text-only` · `thin` · `unknown`, from the method plus the
  recorded size and mime. New doctor checks: **`thin-capture`** (a capture
  that succeeded and brought back 800 bytes of consent wall produces the same
  hash, ledger row and grade `?` as the real document — the same
  looks-trustworthy-carries-nothing shape as a stored grade outliving its
  support tuple) and **`unvocabularied-method`** (a `strategy` that reads like
  a tool name). `lineage@1.3` claims both.
- **The ladder as a regimen** in the source skill and `flip config init`:
  named `--via` lanes for the higher rungs, and the rule that a refusal is
  where acquisition work starts rather than where it stops. When the ladder is
  genuinely exhausted, `flip pass` records what was tried — "searched, gone"
  stays distinguishable from "did not look".

## [0.16.1] — 2026-07-31

### Added
- **YouTube video URLs infer the `talk` kind.** `flip add-source
  https://www.youtube.com/watch?v=…` (also `youtu.be`, `/shorts/`, `/live/`)
  now classifies as `talk` without `--kind`, routing to the `[fetchers.talk]`
  lane. Channels, playlists, and every other YouTube surface still classify
  as `web` — they aren't one capturable spoken record. Born from the first
  real talk-lane deployment (an 8-video capture run where every command
  needed the explicit flag).
- **A docs-consistency release gate** (`tests/test_docs_current.py`, now five
  checks). Beyond retired vocabulary it asserts prose against the code: OKF
  version claims match `manifest.OKF_VERSION` (a new named constant, so prose
  and code share one source of truth), manifest examples match
  `FLIP_PROFILE_VERSION`, the version SPEC.md and README announce matches
  `flip.__version__`, and every version declaration agrees — the lockstep bump
  RELEASING.md used to ask a human to verify by eye.
  **Prose files are now discovered rather than listed**, which is the real
  fix: `AGENTS.md` rotted three releases purely because nobody had added it to
  a hand-maintained list. RELEASING.md documents the gate as a release step.

### Fixed
- **Docs misstated the OKF version at rest.** `AGENTS.md` opened by calling a
  notebook "a conformant OKF v0.1 knowledge bundle" — flip has stamped
  `okf_version: 0.2` into every manifest since 0.11, and AGENTS.md ships in
  the sdist, so 0.16.0 published that error. The site's design brief carried
  the same stale claim, and SPEC.md's canonical manifest example still showed
  `flip: "0.7"` one profile after 0.8 shipped.

## [0.16.0] — 2026-07-30

**Breaking, by design:** the judgment fix below changes verification-bar
outcomes on existing on-disk notebooks. A claim resting on a source whose
`independence` predates 0.8 will demote, because that source was never
carrying a judgment flip could read.

Everything here comes from a field report written after one long research
day and checked line by line against the implementation: two notebooks, ~40
sources, 27 claims, and one agent-run spent clearing 4 errors and 272
warnings out of a notebook that turned out to have a single root cause.

### Fixed
- **A source could show grade A and count for nothing.** `judged()` treated
  *any* truthy `independence` as a recorded judgment, including values not in
  the enum. A notebook carried across the 0.8 vocabulary change therefore had
  sources that were "judged", displayed a confident stored letter, and
  contributed **zero** corroboration — three surfaces disagreeing in silence.
  Worse, `derive_grade`'s `support.seeded: legacy-grade` short-circuit
  returned the stored letter without ever inspecting `independence`, and the
  `seeded-grade` notice suppressed the `grade-drift` warning that would have
  caught it. `judged()` now requires 0.8 vocabulary; pre-0.8 values derive
  `?`. **This demotes claims that rested on such sources** — intentionally: a
  corroboration count drawn from a judgment flip could not read was never
  evidence of anything.
- **`flip migrate` was a no-op exactly when it was needed.** It refused on the
  manifest's `flip:` version alone, so a notebook declaring 0.8 while every
  source page inside carried pre-0.8 tuples was told "already at the current
  profile" — while doctor's own `pre-08-vocabulary` warning was telling its
  owner to run precisely that command. Migrate now scans pages too, and
  "nothing to migrate" requires the manifest *and* the pages.
- **`migrate` no longer maps `original` → `independent`.** That key changed
  *axis*, not spelling: pre-0.8 it recorded custody ("we hold the original
  bytes"), 0.8 records epistemics ("independent of its own subject"). The old
  map silently promoted every self-reported source to full corroboration
  weight. `republisher`/`self-interested` still map (same axis); `original` is
  *parked* — the authored letter moves to `support.pre_08_grade`, the digest
  resets to `?`, and a human re-reads the source.
- **A failed capture no longer reads as corruption.** A `status: failed`
  provenance row has no page by design — "searched, gone" stays
  distinguishable from "did not look" — but `orphan-provenance` nagged about
  it forever, with hand-editing JSONL as the only way to silence it.
- **A local path never routes through a fetcher.** `--kind dataset ./local.psv`
  demanded a `[fetchers]` command for a file already on disk while `--kind
  file` copied the same path fine. Capture now routes on the target.
- **Binary payloads no longer become page titles.** A fetcher handing back a
  decoded payload's first bytes produced pages named `%PDF-1.7 1 0 obj` and
  `PK…[Content_Types].xml`. flip is the trust boundary for a fetcher envelope:
  implausible titles are rejected in favour of the target-derived name.

### Added
- **`flip grade <id> --explain`.** Writes nothing; prints why the source
  derives the letter it does. Only `independence`, `basis` and `base_defined`
  move it — plus `method`, which alone gates B — while `n`, `vintage` and
  `freshness` are documentation. That was discoverable only by reading
  `derive_grade`, and an agent regrading 134 sources had to reverse-engineer
  it.
- **doctor leads with the cause.** A new `vocabulary-drift` finding replaces a
  wall of repeats with one line naming the count *and* the claims it explains,
  and the text renderer collapses any code repeating past three (`--json`
  keeps every finding). 272 symptoms with one cause read as a deeply unsound
  notebook; the truth was that one field changed meaning.
- **Corroboration counts never travel alone.** `claims.uncountable_sources`
  names the cited sources flip could not count either way, and the `verified`
  refusal, doctor's `under-verified`, and `flip source list` all report it
  beside the number. A wrong number is worse than a missing one, because only
  the missing one prompts a look.
- **`flip source retitle <id> "<title>"`.** The write path that keeps a bad
  capture title out of a text editor — flip quotes the YAML, so a title
  containing a colon can't produce frontmatter that breaks every reader of the
  notebook at once. The slug stays `flip rename`'s job.
- **`unlocatable-recomputation`.** A `recomputation` clears the `verified` gate
  on its own, so it must be locatable: doctor now warns when one records no
  `against`. `--against` was always free-form — a session id, script path, or
  derivation record all belong there — but nothing said so and nothing checked.
- **`flip source list` shows the DERIVED letter**, naming the stored one where
  they disagree. A stored letter outliving its support tuple is how a source
  comes to display a confident A while corroborating nothing.

## [0.15.0] — 2026-07-28

### Added
- **The refresh receipt: `flip source recheck <id>`.** A page timestamp
  says the page changed; `last_checked` says the world was checked.
  Recheck re-fetches a URL-backed source's canonical coordinate into a
  temp area — custody is never overwritten — hash-compares against the
  capture ledger, and appends a recheck event (unchanged | changed |
  gone). Drift sets `drifted:` on the page; doctor warns on the source
  (`source-drift`) and on load-bearing claims resting on it
  (`drifted-evidence`); an unchanged recheck clears the flag.
  `lineage@1.1` claims the two new checks.

## [0.14.0] — 2026-07-26

### Added
- **Disciplines: declared standards with slot composition.** A discipline
  is what a notebook is *held to* — one TOML (built-in, $FLIP_HOME, or
  notebook-local) declaring the slots it owns, enforced vs attested
  gates, advisory checks (doctor check codes or simple field predicates —
  deliberately no expression language), namespaced vocabulary, graceful
  depends_on, and declared conflicts the manifest must resolve.
  Composition: gates partition by slot (the owner blocks); rubrics union
  (non-owners emit labeled advisory findings). Three batteries-included
  built-ins: `lineage@1.0` and `forecasting@1.0` (self-descriptions of
  enforcement flip already guarantees) and `systematic-screening@0.1`
  (the first authored regime, exercised by a real notebook). Versioning
  policy: 1.x = flip-guaranteed, 0.x = authored-and-earning-it; pins
  never move silently. Kinds may require slots
  (`requires = [{slot, default}]`); lit-review requires `screening`.
  Fully dormant: an undeclared manifest behaves byte-identically to
  0.13 — proven by test. `flip discipline list|show|new`; exports carry
  the declaration, so the identity of the *standard* travels with the
  bundle. Beats are untouched and stay what they are: a loose topic /
  multi-notebook grouping, not a standard.

## [0.13.1] — 2026-07-26

### Changed
- **The flipbook is a conversation now** — one scrolling page modeling the
  person↔agent exchange: human bubbles, agent replies, the command run
  shown by default, and the full under-the-hood detail (narrative, output,
  record, tree) behind a closed-by-default disclosure per exchange. No
  more stepper.
- **Notebooks show their work.** flip-render/2 gains a `work` array
  (notebook.md, root prose renders, analysis/ pages) — a notebook is the
  completed/in-progress work AND its dependent sources, and the site's
  notebook viewer now leads with "The work" accordingly. The demo
  notebook writes its own findings page during the build.

## [0.13.0] — 2026-07-26

### Added
- **The Forecast class.** A backward notebook fights staleness; a forward
  notebook accrues credibility through resolution. `forecasts/<slug>.md`
  pages (FC#) carry probability + confidence (two scalars, never merged),
  dated `resolves_by` with surfaces and a ranked resolver ladder, a
  string `base_rate` (outside view first), mandatory `annul_if`, typed
  `bears_on` refs, and an append-only `updates:` log. `flip forecast
  add|update|resolve|decline|due|list`; resolutions append RS-schema rows
  to `log/resolutions.jsonl`; the record scores as labeled sharpness +
  Brier (≥5 resolutions); the fold disposition records declines whose
  substance survives elsewhere. Clusters (CL#) hold unscored decision
  questions over proxy forecasts with Claim-typed inference links — class
  purity at file level. The **two-object rule is machine-enforced**:
  doctor errors on probabilities on claims and grades on forecasts.
  New built-in `forward-set` kind (aka "predictions", "what to watch"):
  three dated forecasts + a naive baseline declared before the first
  resolution. flip-render/2 gains a forecasts array; `flip show
  --forecasts` prints the board and the record.
- **"One notebook, whole"** — the docs site now renders a canonical
  browsable notebook (notebook.html) generated at build time from the
  demo notebook via flip-render/2: sources with support tuples and
  custody, claims with attribution and verification records, questions,
  decisions, sessions — every entity anchor-linkable, nothing
  hand-authored.

### Fixed
- flip-render/2 question projections now carry `resolves_via`; blank
  session Goal sections no longer leak the next heading into the goal.

## [0.12.1] — 2026-07-25

### Added
- **Kinds answer to what people actually say.** Every kind carries `aka`
  plain-language phrases; `flip new --kind "literature review"`,
  `flip kind adopt "due diligence"`, and `flip kind show "deep dive"` all
  resolve to the canonical kind (the manifest stores the canonical id).
  `flip kind list` shows the phrases; `--json` exposes them for agents.
- **notebook-kind-author skill** — interviews a domain expert in their own
  vocabulary and writes a valid kind file: outputs first, contract
  requirements each tied to the render that needs them, honest
  `prospective` flags, scaffold + doctor validation. The seventh packaged
  skill.

### Fixed
- Docs and site caught up with 0.12: the support tuple and derived grades
  in quickstart, internals, the OKF-profile draft, spec.html, start.html;
  kinds documented on the start page and README; stray sketch-path comment
  fragments removed from the built-in kind files.

## [0.12.0] — 2026-07-25

### Added
- **Outcome kinds.** `flip new --kind lit-review|decision-packet` starts a
  notebook that knows what its finished output must contain: kinds are
  single-TOML declarations (built-in, `$FLIP_HOME/kinds/`, or
  notebook-local) carrying a collection contract whose entries each name
  the render that needs them and whether they are prospective. `flip kind
  list|show|adopt|new`; late adoption prints an honest gap manifest
  (recoverable / reconstructible-with-loss / unrecoverable-by-construction)
  and records the crystallization; `flip doctor` reports `kind-gap`
  findings (WARN while active, ERROR at done/published). Profiles and
  outcome kinds share one registry and one manifest key; the open notebook
  stays the default and first-class.
- Questions carry `resolves_via` watching surfaces (`flip show` marks
  `unwatched`); pass records carry `absent_from` scoping (non-corpus
  absences must name surfaces); sources carry `pipeline` liveness with a
  mandatory evidence receipt and six provenance terminal states
  (PRIMARY-REACHED/GATED/LOST/NEVER-PUBLISHED/EXISTS-PRIVATE/OPEN, with a
  completion gate on OPEN); failed acquisitions are logged provenance
  events; claims carry `value`/`unit` as data; `flip export json
  --render-version 2` (flip-render/2, a superset — /1 unchanged);
  `flip doctor --workspace` checks cross-notebook claim-status drift.

### Changed
- **BREAKING (judgment model): the support tuple replaces authored
  grades.** `flip grade` records evidence *description* — independence
  (`independent|corroborated|self-reported|derivative`), basis, n (a
  string, so a sample size can't masquerade as the base), method, vintage,
  `base_defined` — and the letter grade is derived from it, never
  authored. The corroboration bar counts `independence: independent`;
  grade-A-suffices reads the derived digest. `flip migrate` (profile 0.8)
  maps the old vocabulary and seeds pre-0.8 letters so every existing bar
  outcome is preserved until sources are re-graded (doctor lists seeds as
  expected-until-touched). Capture no longer writes decorative
  independence/freshness defaults.

## [0.11.1] — 2026-07-25

### Added
- **Claude Code plugin.** The repository now doubles as a Claude Code
  plugin (`.claude-plugin/plugin.json`, name `flip-notebook`) exposing the
  six packaged notebook skills from a top-level `skills/` directory —
  a byte-for-byte synced copy of `src/flip/skills`, enforced by
  `tests/test_plugin_skills.py`. Listed in the `lyra-forge` marketplace.
- `notebook-create` gains a preflight note for agents on machines without
  the CLI (`uv tool install flip-notebook`).

## [0.11.0] — 2026-07-25

### Changed
- **BREAKING (on-disk format): OKF v0.2 adoption (flip profile 0.7).** A notebook is now a conformant
  OKF v0.2 bundle at rest (clean break — no v0.1 emission mode). Entity
  pages record `generated: {by, at}` in place of flat `timestamp`/`actor`;
  claims carry OKF `sources` entries (`{id, resource, title}`) with
  footnote-marker attribution and generated definition links in place of
  `supports` + the `# Citations` block; verification records move from
  `verifications` ({method, by, against, date, note}) to OKF `verified`
  events ({by, at, method, against?, note?}) — trust-tier consumers now read
  flip claims for free. Manifests declare `okf_version: "0.2"` / `flip:
  "0.7"`. The corroboration bar, gate semantics, and the `flip-render/1`
  JSON contract are unchanged.
- `flip migrate` upgrades 0.4–0.6 notebooks in place (idempotent; summary
  gains `pages_okf02`); the v0.3 ledger path now writes the new layout
  directly. `flip doctor` warns (`pre-okf02-layout`) on claims still carrying
  the old keys.
- `flip rename` rewrites `sources[].resource` paths (with `.md`) and
  footnote-definition links; extensionless pre-0.7 `supports` paths are
  still rewritten.

## [0.10.1] — 2026-07-25

### Fixed
- `flip resolve` / `flip open` crashed (`ws_root` None) when invoked with the
  `--notebook`/`FLIP_NOTEBOOK` pin from outside the notebook; resolution now
  anchors on the pinned root like every other command (SPEC §15).

### Changed
- `flip claim add` still accepts dangling citations (SPEC §6.1 — legal, and
  `flip doctor` counts them) but now notes uncaptured source ids at assert
  time, so a typo'd id no longer rides silently to the next doctor run.

## [0.10.0] — 2026-07-24

Question pursuit made expressible, navigable, and renderable — with zero new
stores and zero new services (the state machine stays in the agent; flip
stores artifacts and surfaces state).

### Added
- **Verification methods** (SPEC §7): claims may carry an append-only
  `verifications:` list of `{method, by, against?, date, note?}` records.
  `flip claim verify <C#> --method adversarial|independent-sources|
  recomputation` writes them. A claim passes the `verified` gate when the
  corroboration bar is met **or** an `adversarial`/`recomputation` record
  exists; `independent-sources` documents the reasoning but never satisfies
  the gate alone. The corroboration bar itself is unchanged — the vocabulary
  widens the honest paths, it never softens the gate. Doctor's
  `unaudited-claim` now fires only when a load-bearing claim has neither
  corroboration nor any verification record.
- **Post-hoc claim↔source links** (SPEC §7): `flip claim source add|rm <C#>
  <src-id…>` links or unlinks backing sources after the fact, regenerating the
  `# Citations` block and recomputing corroboration; unknown ids are refused,
  ungraded links warned.
- **Append-only question re-pose** (SPEC §7): `flip question repose <Q#>
  "<new formulation>"` keeps the id/slug/status, makes the new formulation
  current, and preserves the superseded text in a `formulations:` history and
  a dated **Re-posed** body section (plus a `question-repose` log event) — so
  `flip open Q#` always shows the full journey.
- **`pursuit` profile** (SPEC §13): one notebook per question under pursuit —
  scaffolds the primary question as Q1 and `drafts/question-plan.md` (answer
  shapes before retrieval · prior · holdings · routes + stop rule · dated plan
  revisions); notebook.md bands the answer (direct / adjacent / unresolved,
  an honest null being legal) and keeps confidence ≠ coverage ≠ usefulness.
- **`flip ws show [--open|--claims|--json]`** (SPEC §18): a merged roster
  across bound notebooks — open questions with re-pose counts, load-bearing
  claims still below the bar with no gating verification, and each notebook's
  kind/status/updated-age. A computed view over existing data; `flip ws list`
  stays the plain binding table.
- **`flip cli [--json]`**: a compact one-shot map of every command (group
  path, one-line purpose, key flags), generated from the live Click tree so
  it can't drift — the discoverability shortcut that replaces per-group
  `--help` reads.
- **`flip export json [--out <path>|-]`** (SPEC §17): the **`flip-render/1`**
  JSON projection — notebook identity, sources, claims (incl. verifications),
  questions (incl. formulations), decisions, session summaries, and a log
  tail — for renderers and site generators. Policy-filtered exactly like
  `export okf`: refuses unless `visibility: public` or `--include-private`,
  and strips source-trail custody (titles, URLs, capture times, sha256, the
  work log) to judgment stubs when `source_trail_public` is false. Stable key
  order and id-sorted entities for diffability.
- **Global `--notebook <path>` / `FLIP_NOTEBOOK`** pins the notebook root
  (refusing when the pin disagrees with the working directory), and global
  **`--actor <who>`** overrides `FLIP_ACTOR` (precedence `--actor` >
  `FLIP_ACTOR` > detected default). Read-only commands (`doctor`, `profiles`,
  `obsidian`, `migrate`) now honor the pin too.
- **Auto-bind on `flip new`** under a workspace root: the fresh notebook binds
  into the table (slug-derived handle, `-2` on collision) and says so.
- **Staleness honesty** (SPEC §18): `flip show` and `flip ws show` surface
  the notebook's updated-age (`active · idle 41d`) — visibility only, no
  doctor WARN and no auto-transition (status stays a human/agent judgment).

### Changed
- **flip profile 0.6** (additive over 0.5): claims may carry `verifications`,
  questions may carry `formulations`, and the `pursuit` kind arrives. Readers
  accept 0.5 notebooks untouched; `flip migrate` treats 0.5 → 0.6 as a
  version-only bump (no page moves), and still accepts un-migrated notebooks.
- **Root-anchored writes**: every mutating command writes relative to the
  resolved notebook root, never the current directory.
- **Doctor output separates expectations from findings** (E3): appears-with-
  use notices (profile minimums not yet due) render under a distinct
  "expected until use" section apart from real WARN/ERROR; `flip doctor
  --json` exposes the same distinction as an `expected: true|false` field.
- **Unknown-leaf suggestions**: a group invoked with an unknown subcommand or
  a bare argument (`flip question "text…"`, `flip claim C1 …`) now errors with
  a nearest-leaf suggestion (`did you mean \`flip question add "text…"\`?`) and
  the subcommand list — a suggestion, never auto-execution.
- **Skills + AGENTS.md**: every packaged `notebook-*` skill and AGENTS.md gain
  a copy-pasteable verb→leaf command map (consistent with `flip cli`), a loud
  "attribution is `--actor` / `FLIP_ACTOR`, there is no other actor flag"
  line, and a "doctor prints expected-until-use notes; don't re-run for
  reassurance" note. `notebook-create` documents `--kind pursuit`;
  `notebook-audit` documents the verification methods.

### Removed
- **`#` cross-notebook ref reads** (SPEC §9): the pre-0.5 `handle#id` form no
  longer resolves — it fails the ref grammar like any other malformed
  reference. Writers already emit only `:`; `flip migrate` still rewrites
  stored `#` refs (e.g. `links.beat`) and doctor still flags them.

## [0.9.0] — 2026-07-16

### Added
- **Workspaces** (SPEC §18): many notebooks sharing one vault or repo. The
  shared root carries `.flip/workspace.toml` — a local table binding short,
  importer-owned handles (the git-remote-name model) to notebook paths.
  `flip ws init` scans and binds what's below; `flip ws add / rename / rm /
  list [--json]` maintain the table. Binding keeps entity-page `aliases`
  honest (bare id, then `handle:id`); `flip ws rename` rewrites qualified
  refs workspace-wide (prose, wikilinks, labels, frontmatter — never
  captured bytes, export copies, fenced code blocks, or `links.beat`;
  inline code spans are an accepted limitation). Handles never ship with a
  bundle.
- **Notebook uid** (SPEC §4): stable machine identity in the manifest
  (`uid: nb-7k3m9p2x`), minted by `flip new`, backfilled by `flip migrate`
  and `flip doctor --workspace --fix`, carried by every export and import —
  so two copies of one notebook are recognizable as one lineage. Plus
  `origin:`, the provenance of an imported copy.
- **`flip import <src>`**: bring a shared notebook — a directory, an OKF
  export, or a BagIt bag — into the enclosing workspace under a handle you
  own (`--as`, `--into`). Entity ids are never rekeyed, so citations inside
  the bundle stay valid; `origin` is stamped and a uid minted only when the
  source predates uids. `--update <handle>` is replace-if-uid-matches: the
  same lineage refreshes in place (local `.flip/` id reservations survive);
  a uid mismatch refuses. Merging diverged copies is out of scope.
- **`flip resolve <ref> [--json]`** and cross-notebook refs (SPEC §9):
  `handle:id` (`recipes:A3`) resolves through the nearest workspace table;
  `flip open` now takes the same refs. Bare ids resolve in the containing
  notebook exactly as before; under a workspace root (outside any notebook)
  a bare id resolves iff exactly one bound notebook carries it — ambiguity
  lists the qualified forms. Unknown handles and ids are errors, never
  guesses.
- **`flip doctor --workspace [--fix]`**: lints the shared space —
  `bad-workspace-file`, `handle-syntax`, `dangling-workspace-entry`
  (ERRORs); `missing-uid`, `duplicate-uid`, `unregistered-notebook`,
  `stale-alias`, and the aggregated `ambiguous-id` / `slug-collision`
  (WARNs). `--fix` binds unregistered notebooks, backfills uids, and
  regenerates qualified aliases. Notebook-mode doctor gains `missing-uid`
  (gated to manifests declaring flip 0.5+) and `deprecated-ref-separator`.
- **Obsidian workspace vaults**: `flip obsidian` now also prepares a
  workspace root; the companion plugin detects `.flip/workspace.toml`,
  runs `flip doctor --workspace --json` for the panel and status bar, and
  open-by-id suggests every bound notebook's entities in qualified form
  (`recipes:A3`).

### Changed
- **flip profile 0.5** (SPEC §4): the manifest gains `uid` and `origin`;
  the normative cross-notebook ref separator is `:`. `flip migrate` brings
  a 0.4 notebook forward (mints the uid, rewrites `links.beat` `#` → `:`);
  the v0.3 path now ends at 0.5.
- `flip beat graduate` writes the back-link as
  `links.beat: "<beat-slug>:<TH#>"` (was `#`).
- Doctor's `missing-alias` message now says what aliases honestly buy:
  they feed Obsidian's `[[` autocomplete; they do not make a raw `[[A3]]`
  resolve.
- `flip index` rows gain `uid`; a directory carrying `.flip/workspace.toml`
  adds a workspace row (`{"path", "workspace": true, "notebooks": …}`) —
  new row type, consumers that assume every row is a notebook should key on
  `"workspace"`.

### Deprecated
- `#` as the cross-notebook / beat-link separator (`recipes#A3`,
  `links.beat: "<beat>#TH3"`). Readers accept it with a warning
  (`flip resolve`/`flip open` note it; doctor WARNs
  `deprecated-ref-separator`); writers emit only `:`; `flip migrate`
  rewrites stored refs. **`#` reads are removed in flip 0.10.**

### Fixed
- `flip.__version__` had drifted (stuck at 0.6.0 since the 0.7.0 release);
  now 0.9.0 and back in lockstep with `pyproject.toml`.

## [0.8.0] — 2026-07-14

### Added
- **`flip-fetch`** — a bundled, zero-dependency web fetcher (stdlib only,
  shipped as its own console script). Point a `[fetchers]` lane at it —
  `web = "flip-fetch {url} {dest}"` — for out-of-the-box URL capture with no
  external tool. It does a plain GET, extracts the page title, and records the
  canonical URL/mime in a return envelope. The core library stays network-free
  (SPEC §15): `flip-fetch` is a separate process, like any other fetcher.
- **`flip config init`** — writes a starter `$FLIP_HOME/config.toml` whose `web`
  lane defaults to `flip-fetch` (so `flip add-source <url>` works right away),
  with commented curl/wget/yt-dlp and research/knowledge stubs. Refuses to
  overwrite an existing config without `--force`. The "no fetcher configured"
  error now points at it.

### Added
- **Integration roles** (SPEC §15–16): the single `[fetchers]` seam generalizes
  into three deployment-neutral roles sharing one runner (`integrations.py`),
  each a config namespace + command protocol + landing contract.
  - **capture** (`[fetchers]`, hardened): config now accepts an inline table
    (`{ cmd = "…", needs = […] }`) and named variants selectable with
    `flip add-source --via <name>`, alongside the 0.6 bare-string form.
  - **research** (`[research]`): `flip find "<q>"` lists candidate leads (nothing
    is captured until you pick one, `--capture <n>`); `flip ask "<q>"` returns
    cited synthesis — a grade-C **lead**, its raw output preserved under
    `sessions/raw/` and logged, never opened as a source.
  - **knowledge** (`[knowledge]`): `flip recall "<q>"` reads what the deployment
    already holds locally (read-only; lands nothing unless `--record`).
- **Return envelope** (optional, capture): a fetcher may emit a `flip.json`
  sidecar — or a JSON stdout capture — carrying a top-level `flip` object.
  flip harvests its neutral, all-optional keys (`title`, `canonical_url`,
  `strategy`, `retrieved_at`, `status`, `mime`, `from_cache`, `backend_ref`, and
  independence/freshness *hints*) onto the page and provenance. Hints are
  recorded as a page note, never the grade — judgment stays explicit. Absent
  envelope = 0.6 behavior unchanged. `from_cache` + `backend_ref` let a shared
  cache/archive store serve bytes without a re-fetch, the store id recorded
  alongside the mandatory local copy.

### Changed
- `flip add-source --kind lookup` is deprecated: cited synthesis is a lead, so it
  now reroutes to `flip ask` (landing in `sessions/`, not `references/`) with a
  one-line notice. Move `[fetchers].lookup` config to `[research].ask`.

### Fixed
- Removed site-specific fetcher names and assumptions from the public source,
  docs, agent guide, and packaged skills. Missing-config guidance now describes
  only the portable fetcher protocol; implementations remain private operator
  configuration.

## [0.6.0] — 2026-07-10

### Added
- **Obsidian integration** (SPEC §12): `flip obsidian` prepares a notebook
  (or beat) as a vault — merge-writes `.obsidian/app.json` so Obsidian
  authors the same relative markdown links flip does, and installs the
  packaged companion plugin (plain CommonJS, no build step) into
  `.obsidian/plugins/flip-notebook/`. The plugin surfaces doctor findings
  and the hot view in a sidebar panel, a status bar summary, and open-by-id
  navigation, all read-only over `flip … --json`. Walkthrough:
  [docs/obsidian.md](docs/obsidian.md).
- **Spindle distribution** (`spindle/`): `flip-core` bundles the six
  notebook skills with a flip-flavored doctrine (capture before cite; never
  verify below the bar; preserve keys you don't own) so any surface can
  `spindle dist install` + `bind` them.
- `src/flip/spindle-package.toml`: the `[tool.spindle.package]` table as
  package data, so wheel installs (PyPI) stay discoverable by spindle
  (wheels don't carry pyproject.toml); a test keeps it in sync.

## [0.5.0] — 2026-07-10

### Added
- **Beats** (SPEC §14): the grouping layer above notebooks. A beat is itself
  an OKF bundle — `flip_beat:` manifest in its root `index.md`, a `beat.md`
  mission page, and one **thread** page per line of attention (`TH#`, kind
  `arc`/`vein`, weighted triage scores). `flip beat new / thread add|update|
  drop / graduate / show / log`. Graduation scaffolds a child notebook under
  `notebooks/`, back-links both ways (`links.beat: <beat>#<thread>`), and
  records coverage; drops record the reason as negative coverage. Beat and
  notebook commands resolve correctly from inside each other.
- Notebook doctor WARNs `broken-beat-link` when a manifest's `links.beat` no
  longer resolves.
- Trusted-publishing workflow (`publish.yml`): GitHub releases publish
  `flip-notebook` to PyPI via OIDC.
- [docs/okf-provenance-profile.md](docs/okf-provenance-profile.md): flip's
  extension vocabulary written up as a draft OKF provenance profile.

### Fixed
- File captures slug from the stem: `districts.csv` →
  `references/districts.md` (was `districts-csv.md`; found dogfooding).

## [0.4.0] — 2026-07-10

**A flip notebook is now natively an
[OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
knowledge bundle** — flip becomes an extension profile of OKF (lineage rules
for LLM-built wikis, SPEC §6) rather than an exporter to it. Breaking
release; `flip migrate` converts v0.3 notebooks.

### Changed (breaking)
- **Entities are pages.** Sources, claims, decisions, questions, and sessions
  are one markdown file each with YAML frontmatter — the canonical record —
  in `references/`, `claims/`, `decisions/`, `questions/`, `sessions/`.
  The JSONL entity ledgers (`sources/ledger.jsonl`, `analysis/claims.jsonl`,
  `log/decisions.jsonl`, `log/questions.jsonl`) are gone; event logs
  (`log/log.jsonl`, `log/passed.jsonl`, `_provenance.jsonl`,
  `_derivations.jsonl`) remain append-only JSONL sidecars.
- **Filenames are human slugs** (`references/lecun-jepa-keynote.md`); the
  immutable compact id lives in frontmatter with `aliases: [<id>]`, so id
  wikilinks resolve in Obsidian-style editors. `flip rename` moves a page and
  rewrites links; `flip open <id>` resolves ids.
- **The manifest moved into the root `index.md` frontmatter** (OKF's
  sanctioned identity slot); `notebook.toml` is retired. Policy keys are
  flat (`visibility`, `source_trail_public`, …) and edit cleanly as
  Obsidian properties.
- **`index.md` bodies and `log.md` are generated views**, regenerated on
  every mutating command.
- **`flip export okf` is now a policy filter** (visibility gate + source-
  trail stripping) over an already-conformant bundle, not a format transform.
- PyYAML joins click as a core dependency (faithful reading of human/editor-
  authored frontmatter); flip writes a deterministic strict subset.

### Security
- Stripped exports (`source_trail_public: false`) withhold **derived views of
  withheld data**, not just the data: `log.md` (a rendering of the withheld
  work log), reference titles/descriptions (capture notes, private file
  basenames), and any prior export or bag nested inside the notebook are all
  excluded; the references listing is regenerated from the stripped pages.
  Known residual: a claim's `# Citations` label text is frozen at claim-add
  time and ships as written.

### Added
- **The flip profile for OKF** (SPEC §6): eight lineage rules — capture
  before cite, explicit judgment, status-carrying claims, logged generation,
  append-only events, key preservation, attribution, render discipline —
  plus the extension frontmatter vocabulary.
- **Round-trip guarantee**: flip preserves frontmatter keys and bodies it
  doesn't own, so humans (Obsidian) and other agents can edit the same
  files (SPEC §12).
- `flip open`, `flip rename`, `flip migrate`; doctor checks for OKF
  conformance, id/alias integrity, dangling citations, corroboration drift.

## [0.3.0] — 2026-07-10

### Added
- **Reference implementation**: the `flip` CLI (`new`, `add-source`, `grade`,
  `log`, `decide`, `pass`, `question`, `claim`, `session`, `show`, `doctor`,
  `index`, `export`, `profiles`, `source list`, `question list`) as a Python
  package (`flip-notebook`, stdlib + click, no network in the core), with a
  full test suite and CI.
- **OKF export** (`flip export okf`): project a notebook as an
  [Open Knowledge Format v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
  knowledge bundle — sources as `references/` concepts with custody
  frontmatter, claims with `# Citations`, decisions, `log.md`, policy-gated
  source trail, and `--announce` marker blocks for AGENTS.md. Design:
  [docs/wiki-alignment.md](docs/wiki-alignment.md).
- **Agent-learnability layer**: `AGENTS.md`, `llms.txt`,
  [docs/quickstart.md](docs/quickstart.md), and six procedural skills under
  `src/flip/skills/` (also declared as a spindle package in `pyproject.toml`).
- BagIt export (`flip export bag`), CSL JSON export (`flip export csl`),
  per-user notebook registry (`flip index`).

### Changed
- **Breaking (spec §3/§9):** file/dataset source ids now use the `F#` prefix;
  `D#` is reserved for decisions (the two collided in prose cites).
- **Spec §7.2 hardened:** ungraded (`?`) sources never count toward claim
  corroboration — capture is custody, not judgment.
- **Spec §12:** profile minimums are completion requirements — missing
  required files WARN while a notebook is `active`/`dormant` and ERROR once
  it is `done`/`published`/`archived`.

### Fixed
- Ten findings from an adversarial review of the initial implementation,
  including manifest round-trip data loss, TOML escaping that could brick a
  notebook, session-slug suffix collisions, corroboration dedupe, and BagIt
  symlink handling.

## [0.2.0] — 2026-07-09

### Added
- **Beats** (§13): a grouping layer above notebooks — a standing mission with
  a thread ledger that spawns notebooks as threads get real.
- **Detached notebooks** (§3): convention for notebooks whose visibility
  exceeds their host repo's (private notebook, public repo).
- **Pluggable fetchers** (§14): `flip add-source` routes through commands
  registered in `~/.flip/config.toml`; only `builtin:copy` is built in.
- **Dependency-free registry** (§14): `flip index` writes a plain per-user
  `~/.flip/index.jsonl` by scanning; no services.

### Changed
- Removed the `agent-beat` profile; that territory belongs to the beat layer.
- Hardened the no-proprietary-dependencies commitment throughout (§15).

## [0.1.0] — 2026-07-09

### Added
- Initial spec draft: principles, directory layout, manifest, source custody +
  capture provenance, source-quality model (reliability/credibility split),
  derivations log, claim ledger, work/decision/negative-evidence/session logs,
  IDs, hot/cold views, drafts and renders, profiles, CLI sketch, skills layer,
  git conventions, interop exports.
