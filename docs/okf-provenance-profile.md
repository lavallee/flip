# A provenance profile for OKF — draft proposal

**Status:** draft for community discussion, 2026-07-10; revised 2026-07-25
against OKF v0.2. Not yet submitted anywhere; this document is written so it
*could* be — to the
[OKF repository](https://github.com/GoogleCloudPlatform/knowledge-catalog)
or the W3C Holon Community Group — if and when the maintainers of flip
choose to start that conversation.

## The gap

[OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
made real provenance moves: `sources` entries with objective credibility
signals (`author`, `usage_count`, `last_modified`), `generated: {by, at}`,
`verified` events with derived trust tiers, `status`, and `stale_after` are
core frontmatter now. The spec records *signals* and deliberately refuses to
store judgments ("a score is subjective, unportable across consumers, and
goes stale"). That is the right base-format call — and it leaves exactly the
layer agent-written research needs still open:

- **Custody**: `sources[].resource` may be a URL that rots; nothing in core
  OKF says "we hold the bytes, hashed at capture."
- **Judgment**: credibility signals let a consumer *infer* trust, but the
  recorded, named-actor judgment ("I read this; it grades B; it republishes
  the wire story") has no slot — and a corroboration *bar* that gates what a
  claim may assert has none either.
- **Generation context**: `generated.by` names the actor; the session — the
  model, the tools, the goal, the transcript pointer — has no concept type.
- **Negative evidence**: considered-and-rejected has no home, so agents
  rediscover the same dead ends.

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
okf_version: "0.2"
profiles: [provenance/0.2]
```

### Concept types and keys

| addition | on | semantics |
|---|---|---|
| `type: Source` concepts in `references/` | source pages | one concept per external artifact the bundle relies on, mirroring OKF's existing `references/` convention |
| `support: {basis, n, method, base_defined, vintage}` | Source | the evidence described, not scored: basis (official-record/platform-data/measured/survey/panel/single-operator/synthesis), n **as stated, a string**, and `base_defined` — is the measured quantity itself specified? |
| `independence: independent\|corroborated\|self-reported\|derivative` | Source | the tuple's spine, judged separately from basis (Admiralty-style split); only `independent` corroborates |
| `grade: A\|B\|C\|D\|?` | Source | a **derived digest** of the tuple, never authored — a summary, not a store |
| `freshness: fresh\|dated` | Source | explicit staleness *judgment*, complementing v0.2's mechanical `stale_after` date and `sources[].last_modified` signal |
| `local`, `sha256`, `retrieved_at`, `captured_with` | Source | custody: the archived copy's bundle-relative path and fixity at capture |
| `type: Claim` concepts | claim pages | one concept per load-bearing assertion |
| `status: asserted\|verified\|needs-2nd\|unconfirmed\|false-positive\|retracted\|superseded` | Claim | machine-generated assertions enter `asserted`; `verified` is gated |
| `sources[].id` as footnote keys | Claim | v0.2's own `sources` + footnote-attribution idiom, used exactly as specified — the profile adds only the gate below |
| `independent_corroboration` + gated `status` | Claim | `verified` status is *refused* until the declared corroboration bar is met — the judgment layer v0.2 deliberately leaves to profiles |
| `role: evidence\|subject` on a `sources` entry | Claim | what the citation is FOR. `evidence` (the default, and the meaning of the key's absence) is a witness and corroborates; `subject` is the source the claim is ABOUT, never counts, and drops `independent_corroboration` from the page entirely rather than reporting a zero the axis cannot support |
| `method` on `verified[]` events | Claim | how the check was performed (`adversarial` / `independent-sources` / `recomputation`); only the first and last clear the gate alone |
| `type: Work Session` concepts | session pages | one concept per generation episode: `generated: {by, at}`, `model`, `tools`, `started`, `ended` |
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
