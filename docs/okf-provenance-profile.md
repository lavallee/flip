# A provenance profile for OKF — draft proposal

**Status:** draft for community discussion, 2026-07-10. Not yet submitted
anywhere; this document is written so it *could* be — to the
[OKF repository](https://github.com/GoogleCloudPlatform/knowledge-catalog)
or the W3C Holon Community Group — if and when the maintainers of flip
choose to start that conversation.

## The gap

[OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
deliberately ships without a provenance scheme: bundle identity is delegated
to git, freshness to per-concept `timestamp` fields, and history to `log.md`.
That minimalism is right for v0.1 — but the spec's own first goal is "a
universal format that enrichment agents can write into," and agent-written
knowledge raises questions the base format cannot answer:

- Where did this concept's facts come from — and do we have custody of that
  source, or just a link that may rot?
- Who judged the source, and separately, how corroborated is the claim?
- Which agent run produced this page, with what model and inputs?
- When a consumer re-syncs a bundle, can it distinguish "the world changed"
  from "an agent hallucinated a revision"?

The LLM-wiki pattern compounds knowledge; without lineage it compounds
*unaudited* knowledge.

## The proposal

A conformance profile — bundles opt in by declaring it in the root
`index.md` frontmatter — that standardizes extension keys OKF consumers
already tolerate (unknown keys MUST be preserved, so profile bundles degrade
gracefully in stock tooling). The vocabulary is extracted from
[flip](https://github.com/lavallee/flip), where it is implemented, tested,
and in production use; the normative statement of the rules is
[flip's SPEC §6](https://github.com/lavallee/flip/blob/main/SPEC.md).

### Profile declaration

```yaml
# bundle-root index.md frontmatter
okf_version: "0.1"
profiles: [provenance/0.1]
```

### Concept types and keys

| addition | on | semantics |
|---|---|---|
| `type: Source` concepts in `references/` | source pages | one concept per external artifact the bundle relies on, mirroring OKF's existing `references/` convention |
| `grade: A\|B\|C\|?` | Source | source reliability: authoritative primary / official-independent / vendor-practitioner-synthesis / not yet judged |
| `independence: original\|republisher\|derivative\|self-interested` | Source | judged separately from grade (Admiralty-style split) |
| `freshness: fresh\|dated` | Source | explicit staleness judgment, distinct from `timestamp` |
| `local`, `sha256`, `retrieved_at`, `captured_with` | Source | custody: the archived copy's bundle-relative path and fixity at capture |
| `type: Claim` concepts | claim pages | one concept per load-bearing assertion |
| `status: asserted\|verified\|needs-2nd\|unconfirmed\|false-positive\|retracted\|superseded` | Claim | machine-generated assertions enter `asserted`; `verified` is gated |
| `sources: [<id>]` + `supports: [/references/<concept>]` | Claim | machine edges (stable ids + bundle paths) duplicating the human `# Citations` block |
| `type: Work Session` concepts | session pages | one concept per generation episode: `actor`, `model`, `tools`, `started`, `ended` |
| `actor: human:<name> \| agent:<name>` | any concept | attribution on every page |
| `id` + `aliases` | any concept | short immutable identifier surviving file renames |

### Profile rules (normative summary)

1. **Capture before cite** — a profile bundle cites only sources it has
   custody of (a `references/` concept with fixity), or the citation is
   visibly dangling.
2. **Judgment is explicit** — `grade: ?` confers nothing; verification bars
   count only judged sources.
3. **Generation is logged** — pages written by agents trace to a Work
   Session concept.
4. **Events append, views regenerate** — history is append-only sidecar
   data; `index.md`/`log.md` are disposable projections.
5. **Writers preserve unknown keys** — OKF's consumer rule, extended to
   producers, so co-editing tools never destroy each other's metadata.

### What this deliberately does not do

No RDF, no new link syntax, no required SDK — the profile is frontmatter
conventions plus discipline, in OKF's own spirit ("if you need an SDK to
write Markdown files, we have bigger problems"). Formal semantics can layer
on later; the W3C Holon CG's exploration of typed profiles is the natural
venue for that stage.

## Reference implementation

flip (`pip install flip-notebook`, MIT) produces and audits profile bundles:
`flip doctor` lints conformance, custody, judgment, and verification bars;
`flip export okf` produces policy-filtered public bundles. Sample bundles:
any flip notebook, including flip's own.
