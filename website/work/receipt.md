# Design receipt — the flip site

Private working document. Not deployed.

```yaml
task: "Decide whether flip is the at-rest format my agents write research into,
       and get a first notebook running."
surface: "flip documentation site — website/site, four routes"
baseline:
  revision: "ce74af1"
  route: "none — no site existed"
  state: "greenfield"
  screenshots: []
  rubric_verdict: "n/a"
variant:
  revision: "ce74af1 + website/"
  screenshots:
    - work/evidence/home-1440.png
    - work/evidence/spec-1440.png
  rubric_verdict: "candidate"
checks:
  functional:
    - "artoo build / status / doctor clean; render vintage fresh against notebook nb-qy38zvcn"
    - "artoo deploy --dry-run stages 29 files through the firewall; flip doctor gate passes"
    - "flipbook stepper: arrows, Home/End, bounds disable, hash sync, deep link (#verified -> step 12)"
    - "spec map: 16 selectable regions, 5 lifecycle stages, 4 ledgers, 6 profiles, 11 CLI groups, 19 sections"
    - "home: 4 rules, 8 coordinates, 8 provenance entries, 2 inline claim refs resolved to anchors"
    - "start: 5 real command outputs including the refusal"
    - "pytest 727 passed (6 new site guards); ruff clean"
  accessibility:
    - "no body overflow at 1440 / 768 / 390 on any route"
    - "wide content scrolls in its own container (.table-wrap, .compare-wrap, .tree, pre)"
    - "focus-visible outline on every interactive element"
    - "file tree is a real nested list; added/changed state carries a text label, not colour alone"
    - "reduced-motion honoured (kit tokens zero durations; site.css zeroes transitions)"
    - "keyboard hints hidden below 720px rather than crushed"
  console_errors: 0
  body_overflow: false
evaluation:
  profile_id: "flip-site-2026-07-24"
  surface_mode: "marketing (home) · public-data (flipbook, spec) · operator (start)"
  harness: "claude-code"
  model_tier: "frontier"
  capabilities: ["browser", "visual-input", "shell"]
  requested_model: "claude-opus-5[1m]"
  served_model: "claude-opus-5[1m] (self-declared; not provider-corroborated)"
  independent_judge: false
  promotion_authority: "none — awaiting human acceptance"
  material_delta: "New surface. No baseline to compare against."
feedback:
  status: "none"
  observations: []
  reopened_from_verdict: null
deferred:
  - "An independent seeing pass. Without one the maximum verdict is candidate, not ship."
  - "Real-device check. All rendering evidence is Chromium at three synthetic widths."
  - "The two first-party captures in the site notebook record an absolute file:// path
     from the build machine. Accurate, and the ledger is append-only so it was not
     rewritten — but a reader will see the author's directory layout."
  - "flip.json ships the full CLI map (~21KB). Fine today; worth trimming to the fields
     the page uses if the surface grows."
```

## What the lowest weak layer forced

The decision stack (see `ia.md` §2) bottoms out at **observed user behaviour: weak** —
there is no adoption to observe, and no amount of design produces it. Every
significant choice on this site follows from refusing to paper over that:

- The proof is **mechanical, not empirical**. Real CLI output, real conformance, real
  refusals — because that is the evidence that actually exists.
- The counter-reading ("this is ceremony") gets its own section on the home page rather
  than a defensive footnote, and the answer given is structural rather than
  promotional.
- The site's own notebook ships a claim that is `unconfirmed` and one downgraded by
  hand to `needs-2nd`. A wall of green verifications would have been achievable and
  would have been a lie about how much is settled.

## Where the design brief bound the outcome

Three anti-references in the brief did real work:

1. *No terminal-with-fake-typing hero.* The hero shows a static claim page from the
   generated notebook instead — a thing that exists rather than a thing that animates.
2. *No decorative node graph for the spec.* The bundle listing became the organising
   spine because that is how a reader meets a notebook on disk, and it stays readable
   and keyboard-navigable at 390px.
3. *No invented notebook content that could pass for a finding.* The demo subject is a
   fictional baking club, labelled as invented on the page itself.

The brief's rule "if a fact can be derived, it is derived" is what made the build
fail-loud. Four separate drifts were caught during construction by the build refusing
to run — including two places where my authored narrative was simply wrong about
flip's behaviour (see below).

## What the build caught that review would not have

- **The scout profile's bar is one source, not two.** The narrative I wrote claimed a
  single source would be refused. The build asserted the refusal, the command
  succeeded, and the build failed. Corrected by moving the demo to `research-review`,
  whose bar genuinely is two.
- **A grade-A primary clears the bar alone.** The reordered story still did not refuse,
  because the first source was graded A. Corrected by leading with a secondary source,
  which is also the more honest research narrative.
- **`export json` refuses on a non-public notebook.** Discovered because the build ran
  it. Now a teaching point in the frame rather than an omission.
- **Source pages carry no `resource` key for local-file captures.** The spec-map
  cross-check caught the advertised key not existing.

None of these would have been caught by reading the spec carefully, and all four would
have shipped as confident, wrong prose.

## Known limits of this receipt

The model and harness fields are a **self-declared attestation**. A screenshot proves a
render happened; it does not prove the surface works for a reader who is not me. The
verdict is `candidate` until someone else looks at it.

## 2026-08-20 — continuable-research and harness-first refresh

This pass changed the front door from an at-rest-format argument to a workflow
handoff: “Research that can keep going.” The home page now gives the active agent
a copyable, read-only fit check; distinguishes the CLI from the harness plugin;
puts real notebook use and recent deep-research evidence above the format
mechanics; and preserves the controlled-efficacy, token-efficiency, rights, and
draft-spec boundaries. `start.html` now assumes the human directs research while
the agent operates the CLI, with the exact commands retained as inspectable
under-the-hood output.

The follow-up pass removed the fit-check instructions from the reader's surface:
“Curious about how flip can work for you? Hand this to your agent” is now the
whole call to action, while the button copies the complete read-only brief. It
also made the plugin the only human-facing install; the notebook creation skill
now checks for and guides the separate CLI tool install when an approved pilot
actually needs it.

The next pass removed the duplicated, defensive “Ask your agent if it fits” hero
action. “See flip in action” now leads with proof; the adjacent “Hand this to your
agent” invitation is the sole fit-assessment path, and “Get flip” is the direct
installation path.

The headline now makes the behavioral change explicit: “Help your agent be a
reporter, not a stenographer.” The supporting copy names what that means—source
judgment, claim-to-evidence tracing, question refinement, and pursuing research
beyond the first plausible answer—then closes on the human-agent contract.

That supporting copy is now two paragraphs: CLI tools and skills describe what
the agent does; the spec describes the portable agentic reporter's notebook and
its fit with OKF and LLM- and wiki-friendly tools such as Obsidian.

Checks at the working-tree revision:

- `artoo build website`, `artoo status website`, and `artoo doctor website`: clean;
  render fresh against notebook `nb-qy38zvcn` updated 2026-08-20.
- `pytest -q tests/test_website.py`: 6 passed; `ruff check .`: clean;
  `git diff --check`: clean.
- Chromium at 1440, 768, and 390 px: no body overflow on home or start, no page or
  console errors, no broken images; copy controls materialized for all four home
  command/prompt blocks and all eleven start blocks.
- `uv run pytest -q`: 1355 passed and two unrelated failures: one date-sensitive
  dormant-view fixture landing exactly on 2026-08-20, and the public-name scrub
  correctly catching a name in the user's pre-existing untracked
  `docs/concurrent-writes.md`. Neither was changed by this surface pass.
