# flip

Format and tooling for **reporter's notebooks** — source-controlled research
corpora created and maintained by any mix of humans and agents.

A notebook gives you: custody of the sources you rely on, reprocessable
enrichment (OCR/parsing/transcripts), layered hypotheses and findings on top,
explicit source-quality judgment, work and LLM-session logs, and a timestamped
history — all as plain files that live happily in git, with no service
required to read them.

**[SPEC.md](SPEC.md)** has the full format: directory layout, manifest, source
ledger and capture provenance, claim ledger, logs, profiles, the beat layer,
the CLI, skills, and integration contract.

Design commitments:

- **Plain files, no services.** Markdown, TOML, JSONL. Readable with `less`,
  diffable with `git`. Standards (BagIt, RO-Crate, CSL, Web Annotation) are
  generated exports, never the canonical format.
- **No proprietary dependencies.** Capture tools, retrieval services, and
  render targets are all pluggable; a notebook is intelligible from its local
  files alone.
- **Custody first.** Local archival copies with hashes at capture; processing
  is logged and re-runnable; LLM output is a lead, not evidence, until
  promoted through the source ledger.

## Install

```bash
uv tool install flip-notebook      # or: pipx install flip-notebook
```

From source: `git clone https://github.com/lavallee/flip && cd flip && uv sync`,
then `uv run flip --help`. Python 3.12+; the core is stdlib + click.

## Quickstart

```bash
flip new nj-schools --kind scout --title "NJ enrollment dip"
cd nj-schools
flip add-source ./districts.csv --note "district enrollment table"   # capture: F1, hashed, grade ?
flip grade F1 --grade A --independence original                      # judge it after reading
flip claim add "Enrollment fell 4.2% since 2021" --source F1 --load-bearing
flip claim status C1 verified      # gated: refused until the corroboration bar is met
flip decide --question "Which county first?" --decision "Start with Essex" --why "largest swing"
flip pass "2019 funding blog post" --reason "republishes state PR verbatim"
flip show                          # the hot view: open questions, claims needing work, recent log
flip doctor                        # lint against the spec and the notebook's profile
```

URL and DOI capture route through fetchers you configure (e.g.
[SingleFile](https://github.com/gildas-lormeau/single-file-cli) for web
pages) — see [docs/quickstart.md](docs/quickstart.md) for the walkthrough,
fetcher config, and profiles.

## For agents

Notebooks are built to be maintained by humans and agents together:

- **[AGENTS.md](AGENTS.md)** — the five-minute tour, the conventions agents
  must honor (append-only ledgers, grade-C-until-promoted, the verification
  bar, `flip doctor`, `FLIP_ACTOR`), and task recipes.
- **[llms.txt](llms.txt)** — doc map for LLM consumption.
- **[src/flip/skills/](src/flip/skills/)** — procedural skills
  (`notebook-create`, `notebook-source`, `notebook-log`, `notebook-audit`,
  `notebook-handoff`, `notebook-lessons`) as plain `SKILL.md` files usable by
  any agent runtime. The skills also ship as a
  [spindle](https://github.com/lavallee/spindle) package named `flip`.

Status: spec draft v0.3; CLI core (`new`, `add-source`, `grade`, `log`,
`claim`, `session`, `show`, `doctor`, `export`, `index`) shipped, including
OKF knowledge-bundle export (`flip export okf` — see
[docs/wiki-alignment.md](docs/wiki-alignment.md)). Next: migration adapters
and the beat layer.

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Changes are
tracked in [CHANGELOG.md](CHANGELOG.md). [MIT licensed](LICENSE).
