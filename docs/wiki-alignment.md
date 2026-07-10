# flip and the LLM-wiki pattern — OKF and OpenWiki alignment

**Status:** design note, 2026-07-10. Defines `flip export okf` and how notebooks
coexist with repo wikis.

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

flip sits one layer below all of this and shares every substrate choice:
plain markdown + git, timestamped evolution, agents as first-class authors.
The difference is what the layers are *for*:

| | LLM wiki / OKF bundle | flip notebook |
|---|---|---|
| unit | distilled knowledge (concepts) | evidence + reasoning (sources, claims, logs) |
| trust model | consumer tolerance, citations optional | custody, hashes, grading, corroboration bars |
| maintenance | regenerate from the world | append-only; judgments revised in place, history in git |

So the alignment is a projection, not a merger: **the notebook is the
evidence-grade substrate; an OKF bundle is one of its renders.** A wiki tells
an agent what we know; the notebook can prove where it came from.

## `flip export okf <dest>`

Deterministic projection of a notebook into an OKF v0.1 bundle — no LLM in
the loop, reproducible, diff-auditable (stronger than LLM re-summarization:
the pages regenerate byte-identically from the ledgers).

Mapping (per the [OKF spec][okf-spec] mechanics):

- **Bundle root `index.md`** — the only index allowed frontmatter; carries
  `okf_version: "0.1"` plus extension keys: `notebook` (slug), `generated_by`
  (`flip <version>`), `generated_at`, and the source notebook's git commit
  when available. Body: the standard `* [Title](url) - description` listing.
- **Sources → `references/<id>.md`** with `type: Source`. The spec explicitly
  blesses `references/` as the home for external material mirrored as
  first-class concepts — that is flip's custody layer, verbatim. Frontmatter
  carries the ledger row as extension keys (`url`, `sha256`, `retrieved_at`,
  `grade`, `independence`, `freshness`); consumers MUST preserve unknown keys,
  so custody metadata survives round-trips through stock tooling. Body: title,
  capture note, and a pointer to the raw file (non-`.md` files in a bundle are
  unconstrained, so `sources/raw/` can ship inside the bundle when policy
  allows).
- **Claims → `claims/<id>.md`** with `type: Claim`; `status`, `load_bearing`,
  and machine-usable `supports: [/references/A3]` lists as extension
  frontmatter; the human-facing links go in a numbered `# Citations` block
  targeting the reference pages. Dangling citations are legal in OKF ("broken
  links may represent not-yet-written knowledge") — which matches claims whose
  sources are graded `?`.
- **Decisions → `decisions/<id>.md`** with `type: Decision`.
- **`log.md`** — generated from `log/log.jsonl`: ISO `YYYY-MM-DD` headings,
  newest first, `**Update**`-style bold prefixes. The JSONL stays the
  substrate; `log.md` is the lossy human/agent view.
- **Per-directory `index.md`** in the exact listing shape, so progressive
  disclosure works in stock OKF viewers (including Google's graph visualizer).
- **Untyped links, typed frontmatter.** OKF links are deliberately untyped;
  epistemics ("corroborated by", "contradicts") live in prose and in extension
  frontmatter lists — conformant today, positioned for richer profiles (the
  W3C Holon CG is exploring formal semantics) without a private dialect.

**Policy gate:** export refuses unless `[policy] visibility = "public"` or
`--include-private` is passed explicitly; `source_trail_public = false` strips
`references/` down to grade + title stubs. The bundle is a *render* — SPEC §11
applies: it is never edited in place, only regenerated.

**Incremental:** the exporter writes `.last-export.json` (`generated_at`,
ledger cursor, tool version) into the bundle and regenerates only pages whose
ledger entries changed — OpenWiki's update discipline, minus the LLM.

## Coexisting with OpenWiki

- **Never write into `openwiki/`** — its updater owns that directory and will
  regenerate over anything else.
- flip's bundle exports to a sibling directory (`notebook-export/` by
  default); the two cross-link freely (OKF links are just markdown links).
  Division of labor: OpenWiki documents *the code*, flip documents *the
  investigation*.
- **Consumption path:** like OpenWiki's marker blocks, `flip export okf
  --announce` appends a `<!-- FLIP:START -->…<!-- FLIP:END -->` block to the
  host repo's `AGENTS.md`, pointing agents at the bundle's root `index.md` —
  the proven idiom for getting agents to find and traverse a wiki.

## Beats are the compounding wiki

Karpathy's core claim — "humans abandon wikis because the maintenance burden
grows faster than the value; LLMs don't get bored" — is flip's beat layer
(SPEC §13) seen from the wiki side. A beat's cross-notebook memory (coverage,
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
