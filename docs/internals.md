# flip internals — module map and contracts

How the reference implementation is organized. Read alongside
[SPEC.md](../SPEC.md); the spec defines the on-disk format, this file defines
the code that manipulates it. Normative for contributors: if code and this
document disagree, fix one of them in the same change.

## Ground rules

- **Stdlib + click only.** The library core makes no network calls, runs no
  LLMs, requires no services (SPEC §14). Fetchers are external commands the
  user configures; flip only ever `subprocess.run`s them.
- **Every disk convention goes through `util.py`** — timestamps (`utc_now`),
  hashing (`sha256_file`), JSONL io (`append_jsonl`/`read_jsonl`/`write_jsonl`),
  actor detection (`detect_actor`), id allocation (`next_id`), root discovery
  (`require_notebook_root`).
- **Append-only means append-only.** Log ledgers (`log/*.jsonl`,
  `sources/_provenance.jsonl`, `derived/_derivations.jsonl`) are written with
  `append_jsonl` exclusively. Only `sources/ledger.jsonl` and
  `analysis/claims.jsonl` are current-state (rewritten via `write_jsonl`).
- **Human-readable errors.** CLI failures raise `SystemExit` with a one-line,
  actionable message. Agents read these too — say what to do, not just what
  broke.
- **Tests:** pytest, `tmp_path`-based, no network, no global state. Each
  module has `tests/test_<module>.py`. Ruff clean at the repo's settings.

## Module map

| module | owns | public surface |
|---|---|---|
| `util.py` | shared primitives | see ground rules |
| `profiles.py` + `profiles/*.toml` | section menu, profile loading | `SECTIONS`, `SECTION_ORDER`, `load_profile`, `list_profiles`, `Profile` |
| `manifest.py` | notebook.toml read/write | `Manifest` dataclass, `load_manifest(root)`, `save_manifest(root, m)`, `touch_updated(root)`. Unknown top-level keys/tables are preserved in `Manifest.extras` and re-rendered on save; every rendered value goes through TOML basic-string escaping; slugs are validated (`^[a-z0-9][a-z0-9._-]*$`) at create/save |
| `scaffold.py` | `flip new` | `create_notebook(dest, slug, kind, title, visibility) -> Path`; renders notebook.toml + notebook.md section stubs from the profile; rejects invalid slugs before creating anything |
| `sources.py` | `flip add-source` | `add_source(root, target, kind=None, note=None) -> dict`; fetcher routing/exec, `builtin:copy`, hashing, provenance append, ledger entry (grade `?`); kind→prefix per SPEC §3 (`paper`→P, `web`/`article`→A, `file`/`dataset`/`document`→F, `talk`/`transcript`→T, else S — D is reserved for decisions); `flip grade` updates ledger judgments; `list_sources` backs `flip source list` |
| `ledgers.py` | `flip log/decide/pass/question` | `log_event`, `add_decision`, `add_passed`, `add_question`, `answer_question`, `list_questions`, `open_questions` — append + id allocation (D# over log/decisions.jsonl, Q# over log/questions.jsonl; every row ever written is scanned so ids are never reused). questions.jsonl is append-only: answering appends a status event, last event per id wins. Every mutator validates the notebook root before writing — no stray `log/` dirs outside notebooks |
| `claims.py` | `flip claim` | `add_claim`, `set_claim_status`, `list_claims`; `STATUSES` enum per SPEC §7.2; `corroboration_count(source_rows, source_ids)` is the one shared bar: deduped source ids whose row is judged (grade A/B/C — `?` never counts) with `independence == "original"`; doctor uses it too |
| `sessions.py` | `flip session` | `start_session(root, slug, model=None, tools=None) -> Path` (stamped file from template), `end_session(root, path_or_slug, summary)` — path or slug; slug matching parses `<15-char stamp>-<slug>.md` and requires exact slug equality (no suffix collisions); newest exact match wins |
| `views.py` | `flip show` | `hot_view(root)`, `claims_view(root)`, `stale_view(root)` → rendered text, or a plain dict with `as_data=True` (backs `--json`); reads ledgers only, computes never stores (SPEC §10) |
| `doctor.py` | `flip doctor` | `run_doctor(root) -> list[Finding]`; profile minimums (missing required paths WARN while manifest status is active/dormant, ERROR once done/published/archived — SPEC §12), orphan sources, unhashed raw files, load-bearing claims below the bar (via `claims.corroboration_count`), stale freshness (date past the profile threshold but still judged "fresh" → WARN `stale-freshness`), manifest sanity; exit 1 on ERROR findings |
| `registry.py` | `flip index` | `build_index(roots) -> list[dict]` scanning for notebook.toml, writing `~/.flip/index.jsonl` (env `FLIP_HOME` overrides `~/.flip`); prunes any directory containing bagit.txt so export bags (whose data/ holds a notebook copy) are never indexed |
| `export.py` | `flip export` | `export_bag(root, dest)` (BagIt 1.0: bagit.txt, manifest-sha256.txt, data/; valid symlinks are materialized — content copied under the link's name, so `drafts/current/` ships as a full copy; dangling links skipped with a stderr warning; any mid-export failure removes the partial bag before SystemExit), `export_csl(root) -> list[dict]` (CSL JSON from ledger; ledger kinds "web" and "article" both map to `webpage`), `export_okf(root, dest)` (OKF bundle; see docs/wiki-alignment.md) |
| `cli.py` | wiring | click group `main`; one subcommand per module surface; `--json` on read commands for agent consumption. Every write echoes something citable — ids where ledgers allocate them (`F1`, `C3`, `D2`, `Q4`), the recorded ts + reason for `flip pass` (passed.jsonl rows carry no id per SPEC §8) |

## Config resolution

- `FLIP_HOME` (default `~/.flip`) holds `config.toml` and `index.jsonl`.
- `config.toml` `[fetchers]` maps kind → command template with `{url}`/`{id}`/
  `{dest}` placeholders (SPEC §14). Unknown kind or missing fetcher →
  actionable error naming the config file. `builtin:copy` needs no config.
- Notebook-local `.flip/profiles/*.toml` overrides shipped profiles.

## Data shapes (authoritative examples in SPEC §5–§8)

- provenance event: `ts, source_id, url?, url_used?, local_path, sha256,
  bytes, http_status?, tool, tool_version?, strategy?, actor, note?`
- ledger row: `id, kind, title?, authors?, date?, publisher?, url?, local,
  text?, grade(A|B|C|?), independence(original|republisher|derivative|
  self-interested), freshness(fresh|dated), status, supports[], notes?`
- claim: `id, text, status(asserted|verified|needs-2nd|unconfirmed|
  false-positive|retracted|superseded), load_bearing, sources[],
  independent_corroboration, first_asserted, actor, notes?`
- decision: `ts, id, question, decision, why, alternatives_rejected?, actor`
- passed: `ts, text, url?, reason, actor`
- question: ask event `ts, id, text, actor, status: "open"`; answer event
  `ts, id, status: "answered", actor` (append-only; last event per id wins)
- log event: `ts, text, actor`
