# Roadmap — flip

## Outcome 1 — Stabilize the OKF-native notebook contract

- Harden migration, key-preserving edits, relative links, ID/alias integrity,
  append-only events, and policy-filtered exports with adversarial fixtures.
- Clarify version compatibility and the migration promise before broadening the
  entity model.
- Exercise done/published/archived completion gates on real notebooks, not only
  fresh scaffolds.

*Graduation:* existing 0.4–0.6 notebooks round-trip through current tooling
without information loss and produce deterministic valid exports. *Kill:* any
feature that weakens plain-file readability or preservation is removed or made
supplemental.

## Outcome 2 — Prove handoff and reuse across real research

- Dogfood notebooks and beats in multiple projects with different profiles and
  more than one human/agent editor.
- Measure whether hot views, open questions, and claim status let a cold reader
  resume without loading the full history.
- Make handoff and lessons workflows promote durable findings without copying
  the notebook into another shadow summary.
- Exercise the shared orient → select → session → check → receipt loop at
  notebook, beat, and workspace scope; compare cold-pickup cost with and without
  the bounded context, frontier reasons, and prior receipt.

*Graduation:* a later worker reuses verified claims and closes an open thread
with no source-trail reconstruction, and can explain which workflow phase and
frontier reason led there. *Kill:* affordances that add files or phase ceremony
but do not improve pickup or auditability are removed.

## Outcome 3 — Make the lineage profile portable

- Bind and validate the skills on multiple harnesses through Spindle.
- Gather interoperability feedback on the draft OKF provenance vocabulary and
  keep exports aligned with the upstream format.
- Define narrow integration contracts for renderers and downstream consumers
  (via the `flip-render/1` JSON projection) while preserving canonical
  ownership.
- Keep extension definitions, hook schemas, and session receipts harness-neutral
  so a workflow shared as files does not depend on one model runtime.

*Graduation:* a non-Flip consumer can honor the lineage profile and a bound
agent follows it in a real notebook without bespoke prompting. *Kill:* avoid
interoperability layers that require a Flip service or fork the source files.

## Outcome 4 — Earn a user-owned extension commons

- Dogfood the built-in workflows through the same TOML registry, checks, and
  receipts available to an external author; remove privileged paths that make
  public examples dishonest.
- Have people outside core create or fork real workflows with the authoring
  skills, then share definition-only plugin bundles containing their kind,
  discipline, workflow, skill, and smallest reproducible fixture.
- Exercise the five hook contracts with at least two independent needs per seam
  before expanding them. Review timeout, ordering, failure, lock-drift, and
  explicit-enablement behavior on macOS, Linux, and Windows.
- Keep discovery and trust separate. Start with repository paths or a reviewed
  static index of definition-only bundles; do not add network acquisition or an
  executable catalog until local link/check/enable/test receipts are understood.

*Graduation:* someone who did not change Flip core authors a workflow from an
actual repeated practice, another person links and modifies it, and both can
inspect the definition, enabled handlers, fixture receipt, and limitations.
At least one executable provider survives use in two unrelated notebooks
without gaining canonical write authority. *Kill:* if only core maintainers can
author useful extensions, or if a hook exists solely for one built-in, simplify
back to plain local definitions rather than maintaining framework theater.

## Keeping this file honest

Released features belong in `CHANGELOG.md`. Registry presence, green fixtures,
and enabled handlers are implementation evidence, not adoption. New roadmap
work needs a real notebook, editor, external author, or consumer that exposes
the gap.
