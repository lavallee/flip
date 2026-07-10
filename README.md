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

Status: spec draft v0.2. Next: the `flip` CLI core (`new`, `add-source`,
`log`, `doctor`, `show`), then the skills layer, then migration adapters.

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Changes are
tracked in [CHANGELOG.md](CHANGELOG.md). [MIT licensed](LICENSE).
