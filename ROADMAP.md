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

*Graduation:* a later worker reuses verified claims and closes an open thread
with no source-trail reconstruction. *Kill:* affordances that add files but do
not improve pickup or auditability are removed.

## Outcome 3 — Make the lineage profile portable

- Bind and validate the skills on multiple harnesses through Spindle.
- Gather interoperability feedback on the draft OKF provenance vocabulary and
  keep exports aligned with the upstream format.
- Define narrow integration contracts for tools such as Artoo and Ergo while
  preserving canonical ownership.

*Graduation:* a non-Flip consumer can honor the lineage profile and a bound
agent follows it in a real notebook without bespoke prompting. *Kill:* avoid
interoperability layers that require a Flip service or fork the source files.

## Keeping this file honest

Released features belong in `CHANGELOG.md`. New roadmap work needs a real
notebook, editor, or external consumer that exposes the gap.
