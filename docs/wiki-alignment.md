# flip and the LLM-wiki pattern — OKF and OpenWiki alignment

**Status:** design note, updated for spec v0.4. Explains how a flip notebook
relates to OKF and repo wikis, and what `flip export okf` does now that the
notebook itself is a bundle.

## The grain

Karpathy's LLM-wiki framing ([gist, 2026-04][karpathy]) is three layers: raw
sources dropped immutably in `raw/`, an LLM-compiled interlinked markdown wiki,
and a conventions doc — all in git, "a persistent, compounding artifact"
instead of RAG rediscovering knowledge from scratch per question. Google's
[Open Knowledge Format (OKF) v0.1][okf-spec] (June 2026) formalizes the wiki
layer: a **bundle** is a directory of markdown **concepts** with YAML
frontmatter (`type` is the only required field), reserved `index.md`/`log.md`
files, untyped links, `# Citations` blocks, and consumers that must tolerate
anything they don't understand. [LangChain's OpenWiki][openwiki] is the same
idea pointed at codebases: an agent generates and incrementally maintains
`openwiki/` in your repo.

Through v0.3, flip sat *beside* this pattern and projected into it: the
notebook was JSONL ledgers, and `flip export okf` transformed them into a
bundle. **As of v0.4 the notebook is a citizen, not an export surface: a
flip notebook is a conformant OKF v0.1 bundle at rest.** Every source,
claim, decision, question, and session is an OKF concept page; the manifest
lives in the bundle root's `index.md` frontmatter (the one index OKF allows
frontmatter on); `log.md` is the reserved update log; `sources/raw/` and the
`_*.jsonl` ledgers ride along as non-markdown sidecar content, which OKF
explicitly leaves unconstrained. Any OKF consumer — Google's graph
visualizer, a catalog, another agent — can browse a live notebook directly.

## flip as an OKF extension profile

What flip adds is what OKF v0.1 deliberately leaves open: a provenance
scheme. The difference is what the layers are *for*:

| | LLM wiki / OKF bundle | flip notebook |
|---|---|---|
| unit | distilled knowledge (concepts) | evidence + reasoning (sources, claims, logs) |
| trust model | consumer tolerance, citations optional | custody, hashes, grading, corroboration bars |
| maintenance | regenerate from the world | pages revised in place, events append-only, history in git |

SPEC §6 states the profile as eight lineage rules — capture before cite,
judgment separate from capture, status-carrying claims, logged generation,
append-only events with regenerated views, unknown-key preservation,
attribution everywhere, renders never edited — plus an extension vocabulary
(`id`, `aliases`, `grade`, `independence`, `freshness`, `status`, `sources`,
`supports`, `actor`, …) layered on OKF's base keys. Everything conformant:

- **`references/` as the custody layer.** The OKF spec blesses `references/`
  as the home for external material mirrored as first-class concepts; flip's
  source pages live there, with custody (`local`, capture provenance) and
  judgment (`grade`/`independence`/`freshness`) as extension frontmatter.
  Consumers MUST preserve unknown keys, so lineage survives round-trips
  through stock tooling.
- **Claims with machine edges and human citations.** `sources: [A3]` (stable
  ids) and `supports: [/references/<slug>]` (bundle paths) in frontmatter;
  a numbered `# Citations` block in the body. Dangling citations are legal
  in OKF ("broken links may represent not-yet-written knowledge") — flip
  keeps them legal but `flip doctor` counts them.
- **Untyped links, typed frontmatter.** OKF links are deliberately untyped;
  epistemics ("corroborated by", "contradicts") live in prose and extension
  frontmatter lists. The W3C Holon CG is exploring formal-semantics profiles
  for exactly this layer; OKF v0.1 has no provenance scheme and flip has a
  worked one, so proposing flip's vocabulary upstream as a candidate OKF
  provenance profile is an open question the spec tracks (SPEC §18).
- **Generated views where OKF expects them.** `index.md` listing bodies and
  `log.md` regenerate deterministically from pages and ledgers on every
  mutating command — reproducible and diff-auditable, no LLM in the loop.

## `flip export okf <dest>` — now a policy filter

Since the notebook already is a bundle, the exporter no longer transforms
formats; it produces the **outside-facing copy** your visibility policy
allows:

- **Visibility gate.** Refuses unless the manifest says `visibility: public`
  or you pass `--include-private` — the live notebook may be internal; the
  export is for outside consumption.
- **Source-trail policy.** With the full trail (`source_trail_public: true`
  or `--include-private`), `sources/` and `log/` ship wholesale (with the
  generated `log.md`) and reference pages gain fixity keys (`sha256`, capture
  metadata for the file `local` points at). Without it, custody detail is
  withheld: raw bytes, event ledgers, and `log.md` stay home, and each
  reference page reduces to a judgment stub headed by its id — grade,
  independence, freshness survive; the capture-note `description` and
  captured-file `title` do not, and `references/index.md` regenerates from
  the stubs; the body notes *"Source trail withheld by notebook policy."*
  Exports nested inside the notebook (bags, previous bundles) never ship.
- **The bundle is a render** (SPEC §11): `.last-export.json` marks it as
  generated; never edit it in place — edit the notebook and re-export. `flip
  index` recognizes the marker and won't register exports as notebooks.
- **`--announce <AGENTS.md>`** appends a marker block to a host repo's
  agent instructions, pointing agents at the bundle root — the proven
  OpenWiki idiom for getting agents to find and traverse a wiki:

  ```markdown
  <!-- FLIP:START -->
  This repository contains an OKF knowledge bundle exported from the flip
  notebook `nj-schools`. Start at [nj-schools-public/index.md](nj-schools-public/index.md)
  and follow links; the bundle is generated — do not edit it by hand (edit
  the notebook and re-export instead).
  <!-- FLIP:END -->
  ```

## Coexisting with OpenWiki

Unchanged by v0.4:

- **Never write into `openwiki/`** — its updater owns that directory and will
  regenerate over anything else.
- flip's notebook (or its exported bundle) lives in a sibling directory; the
  two cross-link freely (OKF links are just markdown links). Division of
  labor: OpenWiki documents *the code*, flip documents *the investigation*.
- Both use marker blocks in AGENTS.md as the consumption path
  (`flip export okf --announce`).

## Beats are the compounding wiki

Karpathy's core claim — "humans abandon wikis because the maintenance burden
grows faster than the value; LLMs don't get bored" — is flip's beat layer
(SPEC §14) seen from the wiki side. A beat's cross-notebook memory (coverage,
lessons, recurring wells) is exactly the persistent compounding artifact; its
notebooks are the evidence behind each page. When the beat layer lands, a
beat should be exportable as an OKF bundle whose concepts cite into
per-notebook bundles — a wiki with receipts all the way down.

[karpathy]: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
[okf-spec]: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
[openwiki]: https://github.com/langchain-ai/openwiki

Further reading: [OKF announcement][okf-blog] · [OKF FAQ](https://okf.md/faq/) ·
[OpenWiki announcement](https://www.langchain.com/blog/introducing-openwiki-an-open-source-agent-for-repo-documentation)

[okf-blog]: https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/
