# Changelog

All notable changes to the flip spec and tooling are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

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
