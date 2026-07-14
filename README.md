# flip

Format and tooling for **reporter's notebooks** — source-controlled research
corpora created and maintained by any mix of humans and agents.

A flip notebook **is an
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
(OKF v0.1) knowledge bundle at rest**: a directory of markdown pages with
YAML frontmatter, an `index.md` root, and a generated `log.md`. Any OKF
consumer can browse one; any markdown editor can edit one. What flip adds is
an **extension profile for lineage** — the discipline the LLM-wiki pattern
(Karpathy's framing, OKF, LangChain's OpenWiki) deliberately leaves open:
custody of the sources you rely on (local bytes, hashed at capture),
explicit source grading, claims gated by a corroboration bar, work and
LLM-session logs, and a timestamped history. A wiki tells an agent what we
know; a notebook can prove where it came from.

Humans and agents work **in the same files**. Every source, claim, decision,
question, and session is one page with a human-slug filename and its
immutable id in frontmatter — open the notebook as an
[Obsidian](https://obsidian.md) vault and frontmatter is the properties
panel, `aliases` make `[[A3]]`-style id links resolve, and relative links
light up the graph view. Re-grading a source from the properties panel is a
legitimate flip operation; `flip doctor` validates after the fact instead of
gatekeeping before.

**[SPEC.md](SPEC.md)** has the full format: directory layout, the manifest
(root `index.md` frontmatter), source pages and capture provenance, claims
and the verification bar, logs and sessions, the flip lineage profile
(SPEC §6), profiles, the beat layer, the CLI, skills, and the integration
contract.

Design commitments:

- **Plain files, no services.** Markdown + YAML frontmatter for entities,
  append-only JSONL for events. Readable with `less`, diffable with `git`,
  browsable by any OKF consumer or markdown tool. Standards (BagIt, CSL,
  RO-Crate, Web Annotation) are generated exports, never the canonical
  format — except OKF, which the notebook natively is.
- **No proprietary dependencies.** Capture tools, retrieval services, and
  render targets are all pluggable; a notebook is intelligible from its
  local files alone. Site-specific implementations live in operator config
  or private integration repositories, never in public defaults, docs, or
  packaged skills.
- **Custody first.** Local archival copies with hashes at capture; processing
  is logged and re-runnable; LLM output is a lead, not evidence, until
  promoted through `references/` and graded.
- **Graceful co-editing.** One entity per file, metadata in frontmatter,
  prose in the body; tools preserve frontmatter keys they don't own, so
  human edits and agent edits round-trip through each other.

## Install

```bash
uv tool install flip-notebook      # or: pipx install flip-notebook
```

From source: `git clone https://github.com/lavallee/flip && cd flip && uv sync`,
then `uv run flip --help`. Python 3.12+; the core is stdlib + click + PyYAML.

## Quickstart

```bash
flip new nj-schools --kind scout --title "NJ enrollment dip"
cd nj-schools
flip add-source ./districts.csv --note "district enrollment table"
# F1 · sources/raw/F1.csv · references/districts.md (grade ?)
flip grade F1 --grade A --independence original         # judge it after reading
flip claim add "Enrollment fell 4.2% since 2021" --source F1 --load-bearing
# C1 asserted · sources: F1 · corroboration: 1
flip claim status C1 verified      # gated: refused until the corroboration bar is met
flip decide --question "Which county first?" --decision "Start with Essex" --why "largest swing"
flip pass "2019 funding blog post" --reason "republishes state PR verbatim"
flip show                          # the hot view: open questions, claims needing work, recent log
flip doctor                        # lint: OKF conformance, profile minimums, verification bar
```

Filenames are human slugs (`references/districts.md`); the immutable id
(`F1`) lives in frontmatter. `flip open F1` resolves an id to its page;
`flip rename F1 district-enrollment-table` renames the file and rewrites
every link to it. `flip migrate` upgrades a pre-0.4 notebook in place.

URL and DOI capture route through fetchers you configure. Commands can write
files into flip's destination or emit JSON/text on stdout; either way, flip
preserves and hashes the artifact, and an optional return envelope lets a tool
hand back a title, canonical URL, and the strategy it used. Two more configured
roles take a question rather than a target: `flip find`/`flip ask` (research —
candidate leads and cited synthesis, a grade-C lead) and `flip recall`
(knowledge — what you already hold locally). See
[docs/quickstart.md](docs/quickstart.md) for the walkthrough, tool-neutral
integration config, profiles, and the Obsidian setup.

## For agents

Notebooks are built to be maintained by humans and agents together:

- **[AGENTS.md](AGENTS.md)** — the five-minute tour, the lineage rules
  agents must honor (capture before cite, grade-C-until-promoted, the
  verification bar, the round-trip rule, `flip doctor`, `FLIP_ACTOR`), and
  task recipes.
- **[llms.txt](llms.txt)** — doc map for LLM consumption.
- **[src/flip/skills/](src/flip/skills/)** — procedural skills
  (`notebook-create`, `notebook-source`, `notebook-log`, `notebook-audit`,
  `notebook-handoff`, `notebook-lessons`) as plain `SKILL.md` files usable by
  any agent runtime. The skills also ship as a
  [spindle](https://github.com/lavallee/spindle) package named `flip`.

### For humans (Obsidian)

A notebook is already a valid Obsidian vault; `flip obsidian` finishes the
job — it writes the vault link config to match flip's relative markdown
links and installs the packaged companion plugin (doctor findings and the
hot view in the sidebar, a status bar summary, open-by-id navigation, all
driven by `flip … --json`). The walkthrough is
[docs/obsidian.md](docs/obsidian.md).

Status: spec draft v0.5 — notebooks are native OKF v0.1 bundles. The CLI
covers the full surface (`new`, `add-source`, `grade`, `log`, `decide`,
`pass`, `question`, `claim`, `session`, `show`, `open`, `rename`, `doctor`,
`index`, `migrate`, `export bag|csl|okf`), plus **beats** — the standing
layer above notebooks (`flip beat new / thread add / graduate / show`): a
mission with weighted-triage threads that graduate into notebooks and keep
cross-notebook coverage memory. `flip migrate` converts v0.3 notebooks in
place. See [docs/wiki-alignment.md](docs/wiki-alignment.md) for how flip
relates to OKF and OpenWiki, and
[docs/okf-provenance-profile.md](docs/okf-provenance-profile.md) for flip's
vocabulary as a draft OKF provenance profile. `flip obsidian` prepares a
notebook as an Obsidian vault, with a packaged plugin surfacing doctor
findings inline ([docs/obsidian.md](docs/obsidian.md)).

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Changes are
tracked in [CHANGELOG.md](CHANGELOG.md). [MIT licensed](LICENSE).
