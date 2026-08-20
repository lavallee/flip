# Information architecture — the flip site

Private working document. Not deployed.

Built from the DES primitives: audience/task classification and the surface
router (`modes/README.md`), the decision stack and design plan (`PRACTICE.md`
§1 and §3), and structural fingerprints rather than page templates.

## 1. The customers, and the job each one arrives with

Three real reader populations. Only the first sets the IA; the other two are
served without being allowed to dilute the front door.

| Reader | Arrives from | The job in their words | What convinces them | What loses them |
|---|---|---|---|---|
| **Agent workflow owner** (primary) | A repo link, an agent recommendation, a search for durable research or provenance | "How do I give the research my agent already does a record we can trust and continue?" | A direct agent handoff, real use cases, harness install, and evidence that the record survives the tool. | Being asked to learn a CLI or pass an adoption test first; a tool that claims to replace current owners; unsupported efficacy claims. |
| **Human researcher** (secondary) | Obsidian community, PKM circles, journalism-tools chatter | "Can I actually work in this, or is it an agent thing I'd be babysitting?" | That it is already a valid Obsidian vault, and that re-grading from the properties panel is a legitimate operation. | Being shown only a CLI. Implying the human is a spectator to the agent. |
| **Format evaluator** (tertiary) | OKF, OpenWiki, archival/provenance standards work | "Is this a credible extension profile, or a fork with opinions?" | Conformance stated precisely; the extension vocabulary listed; honest status on where the profile proposal stands. | Overclaiming standardization. Vagueness about what OKF supplies vs what flip adds. |

**Where the three converge:** all three are deciding about a durable artifact at
rest. The primary reader reaches that decision through an agent already inside
the workflow, so the site must support both the human scan and a direct
orientation handoff to that agent.

**Where they diverge:** the builder wants to know what is enforced; the
researcher wants to know what it feels like to live in; the evaluator wants
to know exactly which claims are being made about conformance. Three
questions, three routes, one spine.

## 2. The decision stack, marked

Per `PRACTICE.md` §1, bottom-up, before touching a surface:

| Layer | State | Note |
|---|---|---|
| Observed user behavior and constraints | **partial** | Public notebooks and a long-running case study now show concrete use, correction, and continuation patterns. There are still no analytics, interviews, adoption counts, or controlled comparisons. |
| Domain facts and rules | **strong** | SPEC.md is draft v0.21; its current size, command map, profiles, and package version are mechanically checked at build time. |
| User need and authority | **partial** | The need is inferred from the author's own multi-project practice, not measured. Stated as a bet on the site, not as a finding. |
| Product strategy and scope | **strong** | VISION.md names the north star, three strategy bets, and four explicit non-goals. |
| Concept model and vocabulary | **strong** | Source / claim / decision / question / session, plus beats and workspaces. Stable across four releases. |
| Interaction flow | **partial** | The CLI flow is proven by tests; the *site's* flow is new work. |
| Rendered surface | **absent** | No site exists yet. |

**Lowest weak layer is the bottom one, and it cannot be repaired by this
project** — no amount of design produces user evidence. The correct response
is not to fake it but to build a site that argues from the format itself and
labels the absence of adoption evidence explicitly. That decision propagates
into every route: the proof on this site is *mechanical* (real commands, real
output, real conformance) because the *empirical* proof does not exist yet.

## 3. Routes

Five routes, flat files so the site renders from `file://` (an artoo
requirement, and the reason there are no directory-index URLs). Four are in
the nav; `notebook.html` is reached from the pages that earn it, below.

### `index.html` — show, name, prove

- **Mode:** marketing, with editorial passages for the argument body.
- **Dials:** variance high, density relaxed, motion functional, type register
  branded, imagery role evidence-only.
- **Task anatomy:** concrete before/after → plain-language research jobs → a
  three-moment generated proof → category evidence → real uses → enforcement →
  format and coexistence → honest limits → status and lineage.
- **Structural fingerprint:** *show, then name, then prove.* The first viewport
  shows what changes. The next section lets readers recognize their own job. The
  generated proof then connects one human assignment, a real refusal, and the
  durable notebook before the page introduces the deeper vocabulary.
- **Deliberately absent:** feature cards, logo strip, testimonials, metrics
  the project does not have, animated terminal.

### `flipbook.html` — how a notebook comes together

- **Mode:** public-data.
- **Dials:** variance medium, density balanced, motion explanatory, type
  register editorial-data, imagery role evidence-and-explanation.
- **Task anatomy:** one scrolling reporting conversation. Nothing auto-plays;
  each agent update has a closed receipt that expands to commands, changed
  files, output, and the resulting page or ledger row.
- **Structural fingerprint:** *assignment → finding → receipt.* The visible
  surface stays at the altitude of an ordinary agent conversation. Repeated
  under-the-hood panels make the implementation auditable without implying
  that the person directed each CLI operation.
- **Why a conversation and not a stepper:** the unit a person recognizes is a
  reporting turn, not a command. Ordinary document scroll preserves that
  reading model and works without animation, keyboard state, or reduced-motion
  exceptions.
- **State:** each exchange has a URL anchor so a finding remains linkable and
  the back button works. Native summary/details controls keep the receipts
  keyboard-operable without a custom interaction model.
- **Deliberately absent:** autoplay, typing animation, fake latency.

### `spec.html` — the format tour

- **Mode:** public-data.
- **Dials:** variance medium, density compact, motion functional, type
  register editorial-data, imagery role evidence-only.
- **Task anatomy:** a map with drill-down. Not a diagram to admire — a
  navigation surface into SPEC.md.
- **Structural fingerprint:** *the bundle, opened.* The directory layout as
  the organizing spine (because that is how a reader meets a notebook on
  disk), with each region expandable into the entity type it holds, its
  frontmatter keys, and a link to the governing spec section.
- **Second view on the same page:** the source lifecycle — captured → graded
  → cited → gating a claim → verified — because the single most important
  thing to understand about flip is that these are *separate acts*, and a
  static layout diagram cannot show sequence.
- **Deliberately absent:** a force-directed node graph. It would be
  unreadable at 390px, unnavigable by keyboard, and would imply a topology
  the format does not have.

### `start.html` — agent handoff and harness installation

- **Mode:** operator.
- **Dials:** variance low, density compact, motion none, type register
  interface, imagery role none.
- **Task anatomy:** agent handoff followed by a linear install. Orientation →
  harness plugin → skill-guided CLI setup → conversational direction. The exact
  CLI lifecycle remains below as inspectable
  under-the-hood output.
- **Structural fingerprint:** *orientation → installation → operation.* The page
  gives the agent the map, gives it responsibility for setup, then shows what it
  does for the human.
- **Deliberately absent:** a prerequisite fit assessment, an assumption that the
  human will operate the CLI, or a repository-wide migration ceremony.

### `notebook.html` — the finished notebook, whole

- **Mode:** public-data.
- **Dials:** variance low, density dense, motion none, type register
  interface, imagery role none.
- **Task anatomy:** a reference read, entered with a question already formed
  ("what does one of these actually look like when it's done?"). Nothing is
  authored on it: every section renders the `flip-render/2` projection of the
  same demo notebook the flipbook builds, so the two can never disagree.
- **Structural fingerprint:** *the ledger, in full, with nothing summarised.*
  Sources with their support tuples, claims with corroboration, exposure and
  verifications, questions, decisions, sessions, forecasts, the log tail.
- **Navigation:** the ordinary site nav remains available, while the page is
  still reached most prominently as the payoff of the flipbook and home proof.

## 4. Navigation model

A persistent five-item nav: `flip` (home), Flipbook, Format, Start, GitHub.
Flat, no dropdowns, no mega-menu — four top-level destinations do not need hierarchy, and
inventing some would misrepresent the site's size. `notebook.html` is
deliberately out of the nav: it is the payoff of a specific promise ("browse
the finished notebook"), linked from the home hero and the flipbook's end,
and a reader who has not made the trip has no use for it. It is listed on the
404 page and in the sitemap, because it is a real address.

Ordering is the reader's likely path, not alphabetical: understand → see it
happen → tour the format → install.

Cross-route links are one-directional and specific:

- Home → flipbook at the moment custody is claimed ("watch this happen").
- Home → the whole notebook and format tour once the generated proof is shown.
- Flipbook → the whole notebook, plus a SPEC.md section per step.
- Format tour → SPEC.md anchors, always; the visual never becomes the source of
  truth.
- Everything → start, once.

## 5. Content inventory and its provenance

| Surface content | Source | Fails how |
|---|---|---|
| Version, test count, revision | `pyproject.toml`, a regex count of test functions (deliberately not `pytest --collect-only`), `git rev-parse` at build | Build error |
| CLI commands and flags | `flip cli --json` at build | Build error |
| Flipbook frames | Real CLI runs in a temp directory at build | Build error |
| Spec sections and anchors | Parsed from `SPEC.md` headings at build | Build error |
| Entity types, frontmatter keys, lifecycle | Hand-authored in the build script, checked against the generated demo notebook's real frontmatter | Build error on drift |
| Site's own claims and sources | `website/notebook/`, via `flip export json` | Provenance panel absent |
| Everything else (prose) | Written, and answerable to the design brief | Review |

The rule: if a fact can be derived, it is derived. Prose is for argument, not
for facts that will drift.

## 6. What this site does not have, on purpose

- No blog, no news, no changelog page — CHANGELOG.md is the record and the
  nav links to it rather than mirroring it.
- No docs tree. `docs/` in the repo is the reference; duplicating it here
  would create two sources of truth, which is the exact failure flip's own
  "canonical notebook, derived renders" principle warns about.
- No search. Four routes.
- No newsletter, no waitlist, no analytics, no third-party anything.
