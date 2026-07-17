# Changelog

All notable changes to the flip spec and tooling are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
