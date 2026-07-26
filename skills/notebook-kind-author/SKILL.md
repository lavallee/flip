---
name: notebook-kind-author
description: Turn a domain expert's description of their research process into a flip kind — invoke when someone wants their own notebook type ("our diligence memos always need X"), an in-house workflow captured, or an existing kind adapted.
---

# notebook-kind-author

Interview the expert in their own words; write the kind file; validate it.
The person you're talking to knows their craft — what a finished output
must contain, what disqualifies a source, when work goes stale. Your job
is translation: their knowledge in, one valid TOML out. They should never
need to learn the file format, and you should never invent requirements
they didn't state.

**Preflight:** `flip kind list` shows what already exists — adapting a
built-in beats authoring from scratch (`flip kind show lit-review` is the
richest worked example; the file it points at is meant to be forked).

## The interview (their vocabulary, not flip's)

Ask in plain language; map silently. One question at a time; stop when the
contract has 3–7 requirements — a kind with 20 is a compliance form.

1. **"What are you making?"** → the kind's `id` (kebab-case, named for the
   output) and `summary` (their words, tightened). Also collect the
   `aka` list: what do people on their team actually call this? Those
   phrases become `--kind` inputs that resolve — "diligence memo" should
   just work.
2. **"When it's done and someone challenges it, what do you point at?"**
   → `[[contract.require]]` entries. For each: what must exist (`what`),
   where it shows up in the output (`assembled_by` — a requirement no
   output section needs is cargo cult; push back), and how it's counted
   (`entity` + `field`, or `entity = "files"` + `path`).
3. **"Which of those can't be reconstructed after the fact?"** →
   `prospective = true` (criteria frozen before looking, contemporaneous
   decisions). Be strict: this is what makes late-adoption gap manifests
   honest.
4. **"Does this get redone on a schedule, or is it one-and-done?"** →
   `[versioning]` (`mode = "living"` with cadence, or `"one-shot"`).
5. **"What order does the work happen in, and what does each stage
   produce?"** → optional `[workflow]` phases with `produces`. Skip if
   they don't have a real phase structure — absent beats empty.

## Write, validate, hand over

```bash
flip kind new <id>          # scaffold at $FLIP_HOME/kinds/<id>.toml
# ...fill it from the interview (the template's comments document every key)
flip kind show <id>         # read back the parsed shape — this is the review
```

Then prove it: `flip new scratch-test --kind <id>` in a temp dir and run
`flip doctor` — every contract entry should appear as a kind-gap WARN on
the empty notebook. If one doesn't, its `entity`/`field`/`path` is wrong.
Delete the scratch notebook after.

Ship it to the team however files travel — the kind is one file (or a
`<id>/kind.toml` directory when it grows); anyone who drops it in
`$FLIP_HOME/kinds/` has it. Read their next real notebook's gap manifest
together once: if the tiers surprise them, the `prospective` flags are
wrong, and fixing those now is cheap.

## Authoring a discipline

Sometimes the interview surfaces a *standard*, not an output: "any source
that counts must have been screened," "peer review gets recorded, not
trusted." That's a **discipline** — kind = what you're making; discipline =
the standard it's held to. Same interview philosophy: their standard made
checkable, not your opinion of their field.

```bash
flip discipline new <id>    # scaffold at $FLIP_HOME/disciplines/<id>.toml
# ...fill it, then:
flip discipline show <id>   # read back the parsed shape — this is the review
```

Map their answers to: `[[slot]]` (the policy areas the standard owns —
reuse existing slot names so genuine collisions collide), `[[gate]]` (the
bars — `enforced` when flip should block, `attested` when a third party
already ran the verification and flip only records it), `[[check]]` (the
advisory rubric). A check is either an existing doctor code or a simple
field predicate (`class` + `field` + present/absent/one_of) — when their
rule needs more than that, keep it in prose and say so; never fake it.

Start the version at `0.1` — 0.x marks authored content still earning its
stability; 1.x is reserved for enforcement flip itself guarantees. Notebooks
adopt it by declaring the pin in the manifest (`disciplines:
[<id>@0.1]`); `flip discipline show <id>` flags problems doctor would
report as bad-discipline.

Never: invent requirements the expert didn't state; write a requirement
without `assembled_by`; mark something prospective to seem rigorous. The
kind is their standard made checkable — not your opinion of their field.
