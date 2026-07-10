# Changelog

All notable changes to the flip spec and tooling are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

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
