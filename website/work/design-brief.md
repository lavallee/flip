# Design brief — the flip site

Private working document. Artoo keeps this file outside `site/`; it is not deployed.

## Reader decision

A person already doing research through an agent harness should quickly grasp the
benefit, see the workflow operate on a real notebook, and either give the agent an
orientation guide or install the harness plugin and start source-backed research
without learning flip's command surface first.

The decision is not "is this a nice note-taking app." It is a substrate
choice with lock-in consequences: what my agents produce a year from now,
whether a downstream human or a different model can trust it, and what I owe
in dependencies to get that.

Secondary reader, explicitly served but never allowed to blur the front
door: the **human researcher** who will open the same notebook in Obsidian.
The site must make clear that these are the same files, because "humans and
agents edit the same artifact" is one of flip's three strategy bets, and a
site that showed only the CLI would misrepresent the format.

## Headline claim

**Deep research your next agent can pick up where this one left off.** flip's
CLI tools and skills help an agent work like a reporter rather than a
stenographer: judge the sources it builds on, trace claims to evidence,
formulate and refine research questions, and pursue them beyond the first
plausible answer. You steer the research; the agent maintains the record. The
spec defines a notebook format agent harnesses can operate—a conformant OKF
bundle that also opens as an Obsidian vault. Auditability is the mechanism:
custody, separate judgment, claim gates, question journeys, tests, actor
attribution, and logged generation in plain Markdown and append-only ledgers.

## Supported claims

Each of these resolves against the repository at the deployed revision; the
build fails the site rather than shipping a stale number.

- A flip notebook is a conformant OKF v0.2 knowledge bundle at rest, not an
  export target (SPEC §1 preamble, §3 conformance note).
- The core has two library dependencies, click and PyYAML, and makes no
  network calls and no LLM calls in the library (SPEC §15).
- Capture, text extraction, research, and knowledge integrations are four
  pluggable roles configured by the operator; the package ships only
  `builtin:copy` and the stdlib `flip-fetch` web lane, and no extractor at all
  (SPEC §15 integration roles, §16, §5.5).
- Source reliability and claim credibility are separate judgments, after
  Admiralty/NATO practice; ungraded sources corroborate nothing (SPEC §5.4).
- `verified` is mechanically gated: the profile's corroboration bar, or an
  `adversarial` / `recomputation` verification record. `independent-sources`
  documents reasoning and never satisfies the gate alone (SPEC §7).
- A severe test that found the error closes that gate again, whatever the
  corroboration count says; `exposure` is derived from the test record and
  never stored, and tests can only ever close the gate, never open it
  (SPEC §7.1 — the site's own notebook carries this as C7, asserted, with a
  severe attribution test against the captured spec).
- A claim can cite the document it is *about* rather than evidence for it;
  such a claim reports no corroboration number rather than zero, and owes an
  attribution test instead of a second witness that cannot exist (SPEC §7).
- A conversation can be a source: captured whole under ordinary custody, with
  a passage pinned and hashed out of the capture so a claim cites the exchange
  (SPEC §8–9).
- Six profiles ship as TOML data — ledger, scout, research-review,
  engagement, data-investigation, pursuit — and profile minimums are
  completion requirements, not creation requirements (SPEC §13).
- Version, test-function count, spec status, Python requirement, and CLI surface
  are derived at build time rather than copied into prose. The package is MIT
  licensed and installs as `flip-notebook`.
- Public example notebooks demonstrate recomputation, prospective review
  criteria, honest unresolved questions, forecasts, and a 43-session autonomous
  case study. They are observed uses, not controlled evidence of efficacy.
- LiveDRBench and DeepTRACE support the bounded category claim that polished
  deep-research reports can retain incomplete search coverage, one-sided framing,
  and uneven citation support; the latter's product snapshot is dated 2025.
- `flip export json` emits the versioned `flip-render/1` projection, which is
  what renders this site's own provenance panel; `--render-version 2` adds the
  support tuple, exposure and stances, and is what the whole-notebook page
  reads (SPEC §17).

## Unsupported claims and counter-reading

- **No population-level adoption evidence.** Public examples and one case study
  now exist, but there is no user count, adoption rate, testimonial corpus, or
  "trusted by" claim. Test count is implementation evidence, not field evidence.
- **No effectiveness measurement.** Nothing here demonstrates that
  notebook-backed agents produce better research than agents that don't keep
  notebooks. The north-star metric — reusable verified claims picked up in a
  later session — is a stated goal, not a reported result.
- **OKF profile standing is unresolved.** flip's provenance vocabulary is a
  *draft* proposal that has been submitted nowhere. The site must say
  "draft, not submitted," never imply endorsement by OKF or its maintainers.
- **Spec status is draft v0.21.** Not 1.0, not frozen. Migration exists
  (`flip migrate`) precisely because the format has moved and may move again.
- **Strongest counter-reading:** that this is ceremony — metadata discipline
  that raises the cost of every capture without changing what the agent
  actually concludes, and that in practice grades get assigned carelessly by
  the same model that wrote the claim, making the whole apparatus decorative.
  The site must meet this head-on rather than route around it. The honest
  answer is structural, not promotional: grading is a separate recorded act
  by a named actor, ungraded sources count toward nothing, and `flip doctor`
  makes the gap between "captured" and "judged" visible instead of letting it
  hide. That is a design that *surfaces* carelessness; it is not a claim to
  prevent it. Say so.

## Data vintages and denominators

- flip: package version, spec status, and repository revision are stamped at
  build; authored HTML carries only a fallback value.
- Test count: derived at the built revision. This counts test
  functions in the repository. It is not a coverage figure and not a quality
  measure.
- CLI surface: generated from `flip cli --json` at build time, so the site
  cannot describe commands that do not exist.
- Flipbook frames: generated by running the real CLI at build time; each
  frame's vintage is the build.
- Provenance panel: the site notebook's `uid` + `updated`, as recorded in
  `artifact.toml` at the last build. Staleness is reported by `artoo status`.

## Licit comparisons

**Valid axes** — what a builder is actually choosing between:

- What is canonical at rest (plain markdown pages / database rows / vector
  index / opaque service state).
- What the format *enforces* versus merely permits.
- What a downstream consumer can verify without the producing tool.
- Required services and dependencies.
- What happens to the artifact when the tool is abandoned.

Valid comparison set: OKF / OpenWiki (the LLM-wiki pattern flip extends),
plain markdown in a repo, PKM systems (Obsidian, Zotero), and RAG / vector
stores. These differ in *kind*, and the comparison must present them as
differing in kind.

**Invalid comparisons** — must not appear:

- Ranking these as better/worse on one axis, or any composite score. flip's
  own non-goals forbid replacing judgment with a composite trust score; the
  site must not commit that sin in its own comparison table.
- Implying flip replaces retrieval, a vector store, or an agent framework.
  It is the at-rest layer beneath them.
- Feature-count tables. Presence of a field is not capability.
- Any performance or accuracy benchmark. None has been run.

## Selected forms

- **The flipbook** (`flipbook.html`) — the load-bearing interactive. A
  step-through of one notebook being built by real commands, showing three
  synchronized panes: the command, the filesystem it changed, and the record
  that resulted. It exists to make custody *concrete* — the abstract promise
  "hashed bytes plus an append-only provenance line" becomes a thing the
  reader watches happen. Every frame is generated by running the real CLI at
  build time; nothing is authored by hand.
- **The spec map** (`spec.html`) — an entity-relationship view of the format:
  the five entity types, their frontmatter, the ledgers, and the lifecycle a
  source travels (captured → graded → cited → gating a claim). Backed by the
  same generated data, cross-linked into SPEC.md by section so the visual is
  a way *into* the spec, never a replacement that can drift from it.
- **The hero before/after** — one concrete research failure and the record flip
  leaves instead, drawn from the EV-charger example. It puts the artifact in the
  first viewport rather than asking the reader to accept an abstract claim.
- **The generated proof strip** — the assignment, a real non-zero verification
  refusal, and the final handoff, all taken from the same CLI replay as the
  flipbook.
- **The comparison strip** later on the home page — categorical, adjacent, no
  ranking, one row per valid axis above.
- **The orientation handoff** on `start.html` — one explicitly copyable prompt
  that gives the active agent enough context to put flip to work without making
  the person learn the format first.
- **The hero actions** are one proof path (the flipbook) and one install path.
  Examples, orientation, and exact harness commands appear only after the first
  concrete proof.
- **The harness install path** lives on `start.html`. The plugin is the
  human-facing install; its creation skill checks for and guides installation of
  the CLI when the first notebook needs it. Manual CLI use is explicitly under
  the hood.
- **The claim ledger** in the footer — the site's own provenance panel, from
  its own flip notebook, via `flip export json`.
- Rejected: a chart of any kind. There is no measured distribution here, and
  quantitative form would invent a rigor the evidence does not have. The one
  number worth showing (721 tests) is a stat, not a plot.
- Rejected: an architecture diagram of the CLI. It flatters the tool; the
  reader is choosing a *format*.

## Closest DES reference

- **Marketing** for the home page: a prospective adopter must understand
  distinction and credibility. Variance high, but the proof is real interface
  output, never decorative browser chrome.
- **Public-data** for the spec map and the flipbook: provenance, exact
  values, overview-to-detail movement, adjacent comparison.
- **Editorial** for the argument sections and the counter-reading.
- **Operator** for `start.html`: copyable agent prompts, exact harness install
  commands, clear authority boundaries, and real CLI output under the hood.

Design DNA held constant across all routes: the type roles and spacing
rhythm from artoo-kit tokens, a single accent, the monospace record voice for
anything that is literal file content, and the recurring structural motif of
**assignment → finding → receipt**. The CLI belongs inside the receipt, not in
the human's conversation.

## Anti-reference

- The generic developer-tool landing page: centered gradient hero, three
  feature cards, logo strip, "Trusted by," CTA. flip has no logos to strip.
- A terminal-with-fake-typing hero. Motion that pretends to be a demo while
  proving nothing.
- The spec map as a decorative node graph that cannot be read at 390px and
  does not link anywhere.
- An interactive that is a slideshow of screenshots — clickable but inert,
  with no real data behind it.
- A toy research subject that makes agent work look like a human-operated CLI
  tutorial. The flipbook must derive from a real investigation, show the
  conversation first, and link to the complete public notebook whenever its
  offline build uses compact source packets.
- Internal tooling names anywhere. This repository is public-ready and the
  name-leak rule is absolute: the fetchers, retrieval services, and knowledge
  corpora that fill flip's integration roles in the author's own deployment
  are never named in public defaults, docs, or this site.

## Proof required

- **Factual proof:** every command, flag, version, count, file path, and spec
  section reference on the site resolves against the repository at the
  deployed revision. Generated data comes from `flip cli --json`,
  `flip export json`, and real CLI runs — not from prose I typed.
- **Visual and editorial proof:** keyboard operation of the flipbook and the
  spec map (they are the only stateful surfaces), visible focus, reduced-
  motion behavior, contrast, responsive recomposition at 1440 / 768 / 390,
  and an independent seeing pass across all public pages.
- **Offline and firewall proof:** zero CDN and runtime dependencies; the site
  renders from a `file://` URL; `artoo build`, `artoo status`, and
  `artoo doctor` clean; the private-file firewall keeps `work/` and
  `_notebook/` out of the deployed tree; both name-leak greps pass over
  `website/` including every generated data file.
