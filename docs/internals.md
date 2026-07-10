# flip internals — module map and contracts

How the reference implementation is organized. Read alongside
[SPEC.md](../SPEC.md); the spec defines the on-disk format, this file defines
the code that manipulates it. Normative for contributors: if code and this
document disagree, fix one of them in the same change.

## Ground rules

- **Stdlib + click + PyYAML only.** The library core makes no network calls,
  runs no LLMs, requires no services (SPEC §15). Fetchers are external
  commands the user configures; flip only ever `subprocess.run`s them.
- **Every disk convention goes through `util.py`** — timestamps (`utc_now`),
  hashing (`sha256_file`), JSONL io (`append_jsonl`/`read_jsonl`/`write_jsonl`),
  actor detection (`detect_actor`), id allocation (`next_id`), root discovery
  (`is_notebook_root`/`find_notebook_root`/`require_notebook_root` — an
  index.md whose frontmatter declares a `flip:` version). All YAML io goes
  through `pages.py`. The one exception: beat root discovery
  (`is_beat_root`/`find_beat_root`/`require_beat_root`) lives in `beat.py` —
  the same 4KB sniff keyed on `flip_beat:`, deliberately disjoint from
  `flip:` so the two root kinds never shadow each other (a notebook nested
  under a beat still resolves notebook commands to itself; `flip beat …`
  walks past it to the beat).
- **Entity pages are canonical; ledgers are append-only.** One markdown file
  per source/claim/decision/question/session; event history (`log/*.jsonl`,
  `sources/_provenance.jsonl`, `derived/_derivations.jsonl`) is written with
  `append_jsonl` exclusively and never rewritten. `index.md` bodies and
  `log.md` are generated projections owned by `views.regenerate`.
- **Round-trip rule (SPEC §6.6).** Editing an existing page means
  `pages.read_page`, changing only the keys the function owns, and writing
  fm+body back — unknown frontmatter keys and the prose body survive.
- **Mutation tail.** Every mutating library function validates the notebook
  root FIRST (`require_notebook_root` or `load_manifest`), writes, then runs
  `manifest.touch_updated(root)` and `views.regenerate(root)` — exactly once
  per command; the CLI never regenerates on its own.
- **Ids are never reused.** All allocation goes through
  `pages.allocate_id(root, prefix)`: it runs `util.next_id` over
  `pages.all_ids(root)` — current pages (entity dirs + analysis/), every id
  that ever hit the provenance ledger, and every id in the notebook-local
  append-only reservation file `.flip/ids` — then records the grant there.
  Deleting a page never frees its id.
- **Human-readable errors.** CLI failures raise `SystemExit` with a one-line,
  actionable message. Agents read these too — say what to do, not just what
  broke.
- **Tests:** pytest, `tmp_path`-based, no network, no global state. Each
  module has `tests/test_<module>.py`. Ruff clean at the repo's settings.

## Module map

| module | owns | public surface |
|---|---|---|
| `util.py` | shared primitives | see ground rules; plus `ROOT_FILE` ("index.md"), `age_months`, `stamp_slug`, `today` |
| `pages.py` | entity-page layer (all YAML io) | `Page` (path/fm/body, `.id`, `.slug`), `parse`, `read_page`, `write_page`, `dump_frontmatter`, `slugify`, `unique_slug`, `iter_pages`, `iter_pages_tolerant`, `find_by_id`, `all_ids`, `allocate_id`/`reserve_id`/`reserved_ids` (`.flip/ids`), `as_list` (None→[], scalar→[x] — every consumer of a list-typed field uses it), `ENTITY_DIRS`, `SCAN_DIRS` (entity dirs + analysis/, where H# ids resolve, + threads/, where a beat's TH# ids resolve), `PREFIX_DIR` (multi-char prefixes work: `find_by_id` strips trailing digits, so TH3 routes to threads/ while T3 still routes to references/), `RESERVED` ({index.md, log.md}). Strict producer, tolerant consumer: reading normalizes YAML dates to ISO strings (tz-aware datetimes convert to UTC before the Z label); `parse` strips the one-blank-line separator `write_page` emits, so the pair are inverses and rewrites are byte-stable; writing re-emits every key with insertion order preserved |
| `profiles.py` + `profiles/*.toml` | section menu, profile loading | `SECTIONS`, `SECTION_ORDER`, `load_profile`, `list_profiles`, `Profile` (requires paths are v0.4: entity dirs like `references`, `claims`, plus files like `log/passed.jsonl`) |
| `manifest.py` | root index.md frontmatter | `Manifest` dataclass (flat policy fields + `.policy` dict property), `load_manifest(root)`, `save_manifest(root, m, body=None)` (body preserved byte-for-byte unless views passes a new one), `manifest_frontmatter(m)`, `touch_updated(root)`, `require_valid_slug` (`^[a-z0-9][a-z0-9._-]*$`). Unknown frontmatter keys land in `Manifest.extras` and re-emit on save; a known key whose value fails its type check (`tools: "a string"`, `relations: {map}`) rides along in extras verbatim instead of being dropped |
| `scaffold.py` | `flip new` | `create_notebook(dest, slug, kind, title, visibility) -> Path`; writes exactly index.md (via `save_manifest`) + notebook.md (`type: Notebook` + section stubs); all validation before mkdir |
| `sources.py` | `flip add-source` / `flip grade` | `add_source(root, target, kind=None, note=None) -> Page`: fetcher routing/exec, `builtin:copy`, per-file provenance events, opens `references/<slug>.md` at grade `?`; kind→prefix per SPEC §9 (`paper`→P, `web`/`article`→A, `file`/`dataset`/`document`→F, `talk`/`transcript`→T, else S — D is reserved for decisions). `grade_source(...) -> Page` edits only the judgment keys; `list_sources(root) -> list[dict]` (fm + slug + root-relative path, id order); `source_pages(root)` read-only for claims/doctor/export |
| `ledgers.py` | `flip log/decide/pass/question` | Event ledgers: `log_event`, `add_passed` (append-only JSONL under log/). Entity pages: `add_decision` (D#, decisions/), `add_question` (Q#, questions/, `status: open`), `answer_question(root, qid, note=None)` (status→answered + answered/answered_by; note under `## Answer`), `list_questions(root, status=None)`, `open_questions(root)` |
| `claims.py` | `flip claim` | `add_claim(root, text, sources, load_bearing, notes) -> Page` (C#, claims/, generated `# Citations` block + `supports` bundle paths); `set_claim_status` (verification bar via the profile: `claim_min_independent` / `claim_grade_a_suffices`; recomputes corroboration, refreshes supports + citations); `list_claims`; `STATUSES`; `corroboration_count(source_fms, source_ids)` is the one shared bar: deduped source ids whose page is judged (grade A/B/C — `?` never counts) with `independence == "original"`; doctor uses it too |
| `sessions.py` | `flip session` | `start_session(root, slug, model=None, tools=None) -> Path` (top-level `sessions/<stamp>-<slug>.md`, `type: Work Session`), `end_session(root, path_or_slug, summary)` — path or exact slug (newest exact match wins); `ended` lands in frontmatter, summary under `## Summary` |
| `views.py` | `flip show` + generated projections | `hot_view/claims_view/stale_view(root, as_data=False)` computed from pages + ledgers (SPEC §10); `regenerate(root)` rewrites `log.md` (newest-first), each entity dir's `index.md` listing (deleted when the dir empties), and the root index.md *body* through `save_manifest` — deterministic, byte-stable, never touches canonical records. `write_log_md` and `is_generated_index` are shared with the beat layer so beat and notebook projections render identically |
| `beat.py` | `flip beat` — the grouping layer above notebooks (SPEC §14) | Root discovery: `is_beat_root`/`find_beat_root`/`require_beat_root` (index.md with `flip_beat:`; the walk climbs past child notebook roots). Manifest: `Beat` dataclass (slug, mission, status, created, updated, weights + extras — same extras-preservation discipline as `Manifest`), `load_beat`/`save_beat`/`beat_frontmatter`/`touch_updated`. `create_beat(dest, slug, mission="")` writes exactly index.md + beat.md (`type: Beat`, prompt stubs). Threads (threads/<slug>.md, `type: Thread`, ids TH# via `pages.allocate_id`): `add_thread` (kind arc\|vein, status open, `scores` holds only judged keys), `update_thread` (round-trip; notes append under a dated heading; scores merge key-by-key; `next_review` for dormancy; dropping is refused — it needs a reason), `drop_thread` (status dropped + `dropped_reason` + body note + coverage event). `graduate(root, id, slug, kind, title)` scaffolds notebooks/<slug>/ via `scaffold.create_notebook`, stamps the thread `status: active` + `notebook:`, writes `links: {beat: "<beat-slug>#<TH#>"}` into the child manifest, appends a coverage event; refuses unknown/dropped/done/already-graduated threads and taken slugs. Ranking is computed, never stored: `rank_threads` (open/active only, weighted sum, missing score = 0.5, `effective_weights` overlays manifest `weights:` — unknown key SystemExits, tiebreak on id), `thread_score`. Ledgers: `coverage_event` (coverage.jsonl, pure append), `log_event` (log/log.jsonl). `regenerate` rewrites log.md, threads/index.md, and the root index.md body through `save_beat`; every mutator ends with `touch_updated` + `regenerate`. `beat_show(root, as_data=False)`: mission, ranked triage, dormant threads past `next_review`, notebook roster (`child_notebooks`), recent log |
| `doctor.py` | `flip doctor` | `run_doctor(root) -> list[Finding]` (`Finding(level, code, message, path)`). ERRORs: bad-manifest/status/visibility, unknown-kind, missing-required (closed statuses), policy-mismatch, missing-notebook, bad-frontmatter, reserved-frontmatter, missing-id, bad-id, wrong-prefix, duplicate-id, orphan-custody, bad-enum, under-verified, bad-jsonl. WARNs: missing-required (active/dormant — SPEC §13), missing-section, missing-type, missing-alias, dangling-citation, corroboration-drift, unaudited-claim, unlogged-capture, orphan-provenance, unregistered-raw, stale-freshness, broken-beat-link (a manifest `links.beat` that no longer resolves: no beat root above the notebook, beat slug mismatch, or the thread id gone — moved notebooks keep working, but the beat's memory has lost them). Exit 1 on ERROR is the CLI's job |
| `rename.py` | `flip rename` | `rename_entity(root, entity_id, new_slug) -> (old, new, files_changed)`: the only sanctioned rename (SPEC §9) — moves the page (id/aliases unchanged), rewrites resolution-checked markdown links (optional quoted link titles preserved) and `/dir/<slug>` supports paths notebook-wide (sources/ and derived/ never edited), regenerates listings |
| `registry.py` | `flip index` | `build_index(roots) -> list[dict]` scanning for flip roots (`is_notebook_root`), writing `$FLIP_HOME/index.jsonl`; prunes directories holding a `bagit.txt` or `.last-export.json` (exports are copies, not second notebooks); `read_index()`, `flip_home()` |
| `export.py` | `flip export bag/csl` | `export_bag(root, dest)` (BagIt 1.0; symlinks materialized, dangling links skipped with a stderr warning, partial bags removed on failure), `export_csl(root) -> list[dict]` (CSL JSON from references/ pages; item id = compact id; type from page `kind` else id prefix; grade `?` contributes no note), `export_okf` forwards to okf.py |
| `okf.py` | `flip export okf` | `export_okf(root, dest, include_private=False, announce=None)`: a **policy filter**, not a format transform — the notebook already is an OKF bundle. `visibility` gates (public or `--include-private`); full trail (include_private or `source_trail_public`) ships sources/ + log/ + log.md wholesale and adds fixity keys to reference pages (sha256 from the provenance event matching the page's `local`; latest event as fallback); otherwise custody is withheld: sources/, log/, and log.md do not ship (the root listing loses its Update Log entry), reference pages strip custody keys **plus title/description** (capture note, captured basename) down to id-headed judgment stubs, and references/index.md is regenerated from the stubs (id label, "grade X"). Nested exports inside the notebook (dirs holding `bagit.txt`/`.last-export.json`, registry's `COPY_MARKERS`) are pruned from payloads. `.last-export.json` marks the render; `--announce` writes the `<!-- FLIP:START/END -->` block into an AGENTS.md |
| `migrate.py` | `flip migrate` | `migrate(root) -> dict` counts (incl. `already_migrated`): notebook.toml → index.md frontmatter (unknown keys/policy tunables preserved in extras), JSONL entity ledgers → pages (ids and unconsumed fields preserved, corroboration recomputed), question events folded (unconsumed ask/answer fields land in frontmatter, later events win per key), `log/sessions/*.md` moved to `sessions/`, notebook.md gains `type: Notebook`. Resumable: each ledger is deleted only after its pages are written, notebook.toml last, and rows whose id already has a page are skipped (counted as already migrated), never duplicated |
| `obsidian.py` + `obsidian_plugin/` | `flip obsidian` — vault prep for the reference human client (SPEC §12) | `prepare_vault(root, with_plugin=True) -> list[str]` (actions taken; [] when already prepared): accepts a notebook OR beat root (refuses anything else), merge-writes `.obsidian/app.json` (`useMarkdownLinks: true`, `newLinkFormat: "relative"` — Obsidian-authored links match flip's relative markdown links; every foreign key survives, a corrupt config is refused with the filename, never clobbered), copies the packaged plugin (`obsidian_plugin/`: manifest.json + plain-CommonJS main.js + styles.css — no build step, shipped as package data like `profiles/`) into `.obsidian/plugins/flip-notebook/`, and merges `"flip-notebook"` into `community-plugins.json` (no duplicates). The plugin is read-only over `flip doctor/show/… --json` run at the vault base path. `.obsidian/` is editor-local state: flip never reads it back, and dot-dir exclusion keeps it out of every export/bag payload |
| `cli.py` | wiring | click group `main`; one subcommand per module surface; `--json` on read commands. Every write echoes something citable — ids where pages allocate them (`F1`, `C3`, `D2`, `Q4`, `TH2`), paths for sessions/`open`, the recorded ts + reason for `flip pass`. `flip open <id>` resolves ids via `pages.find_by_id`; `flip migrate` finds a v0.3 root by walking up for notebook.toml (a v0.3 notebook has no index.md for `require_notebook_root` to find). `flip obsidian` resolves the nearest notebook root first, else the enclosing beat (inside a graduated notebook, the notebook's vault wins). The `flip beat` group (`new`, `thread add/update/drop`, `graduate`, `show`, `log`) resolves via `beat.require_beat_root`, so beat commands work from inside a child notebook too; `--score key=value` pairs parse via `beat.parse_score_pairs` |

## Config resolution

- `FLIP_HOME` (default `~/.flip`) holds `config.toml` and `index.jsonl`.
- `config.toml` `[fetchers]` maps kind → command template with `{url}`/`{id}`/
  `{dest}` placeholders (SPEC §15). Unknown kind or missing fetcher →
  actionable error naming the config file. `builtin:copy` needs no config.
- Notebook-local `.flip/profiles/*.toml` overrides shipped profiles.
- `FLIP_ACTOR` overrides actor detection (then agent-harness env vars, then
  git user.name, then the OS user).

## Data shapes (authoritative examples in SPEC §4–§8)

Entity pages (YAML frontmatter; unknown keys always survive rewrites):

- manifest (root index.md): `okf_version, flip, slug, title?, kind, status,
  created, updated, host?, visibility, renders_public, source_trail_public,
  citation_rule, links?, relations?, consumers?, tools?` + extras
- source (`references/<slug>.md`): `type: Source, id(P#|A#|F#|T#|S#),
  aliases[id], title, description, resource?, date?, authors?, publisher?,
  local, grade(A|B|C|?), independence(original|republisher|derivative|
  self-interested), freshness(fresh|dated), status, actor`
- claim (`claims/<slug>.md`): `type: Claim, id(C#), aliases, description,
  status(asserted|verified|needs-2nd|unconfirmed|false-positive|retracted|
  superseded), load_bearing, sources[ids], supports[/references/<slug>],
  independent_corroboration (recomputed, doctor flags drift), first_asserted,
  actor, notes?`; body = assertion + `# Citations` edge list
- decision (`decisions/<slug>.md`): `type: Decision, id(D#), aliases,
  description, question, alternatives_rejected?, timestamp, actor`
- question (`questions/<slug>.md`): `type: Question, id(Q#), aliases,
  description, status(open|answered), timestamp, actor, answered?,
  answered_by?`; answer notes under `## Answer`
- session (`sessions/<stamp>-<slug>.md`): `type: Work Session, actor, model?,
  tools?, started, ended?`

Beat pages (SPEC §14; a beat is an OKF bundle with the same grammar):

- beat manifest (root index.md): `okf_version, flip_beat, slug, mission?,
  status, created, updated, weights {payoff .30, access .25, urgency .20,
  connection .15, uniqueness .10}` + extras; beat.md is the prose working
  memory (`type: Beat`, mission / standing sources / what counts as covered)
- thread (`threads/<slug>.md`): `type: Thread, id(TH#), aliases, title,
  kind(arc|vein), status(open|active|dormant|done|dropped), scores? (only
  the judged keys, each 0–1; missing reads as 0.5 at rank time), timestamp,
  actor, notebook? (set at graduation), next_review? (dormancy),
  dropped_reason?`; body = the thread's running rationale, notes appended
  under dated headings
- a graduated child notebook's manifest carries
  `links: {beat: "<beat-slug>#<TH#>"}` back to its thread

Append-only JSONL events (one object per line, every line has `ts` + `actor`):

- provenance (`sources/_provenance.jsonl`): `ts, source_id, url?, url_used?,
  local_path, sha256, bytes, http_status?, tool, tool_version?, strategy?,
  actor, note?`
- log event (`log/log.jsonl`): `ts, text, actor` (notebooks and beats alike)
- passed (`log/passed.jsonl`): `ts, text, url?, reason, actor`
- coverage (beat `coverage.jsonl`): `ts, thread?, notebook?, note?, actor` —
  one event per notebook outcome or coverage-relevant act (graduations,
  drops; negative coverage prevents re-scouting dead angles)
- derivation (`derived/_derivations.jsonl`): inputs → tool/cmd/params →
  outputs with hashes (small PROV profile, SPEC §8)
