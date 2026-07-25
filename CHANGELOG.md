# Changelog

All notable changes to the flip spec and tooling are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
