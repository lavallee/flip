# Migrating older notebooks

Run `flip migrate` from anywhere inside an older notebook, then audit the
result:

```bash
flip migrate
flip doctor
```

Migration is in-place and resumable. Back up or commit the notebook first so
the resulting diff is reviewable.

## v0.3 JSONL notebooks

A pre-page notebook has `notebook.toml` at its root and entity JSONL ledgers.
Migration:

- moves the manifest into `index.md` frontmatter;
- turns every source, claim, decision, question, and session into a Markdown
  page;
- preserves ids, judgments, raw custody, provenance, and append-only work
  history;
- adds the stable notebook `uid` and current profile metadata.

Each ledger is retired only after its pages have been written, and the manifest
moves last, so an interrupted run can continue without duplicating ids.

## Page-shaped older notebooks

Already page-shaped notebooks receive the current profile pass: missing stable
identity is added, legacy beat links are normalized, and current views are
regenerated. `flip doctor` may report missing profile sections; add the named
headings without discarding existing prose.

## Pre-0.8 source judgments

The meaning of `independence` changed from custody vocabulary to epistemic
independence. A source still carrying the older vocabulary is unjudged under
the current model even if an old letter grade remains.

`flip migrate` translates only cases that are mechanically safe. Ambiguous
sources keep their old value under `support.pre_08_grade`, reset to grade `?`,
and wait for a human or agent to reread them:

```bash
flip doctor             # vocabulary-drift names the affected sources and claims
flip migrate
flip grade A3 --explain
flip grade A3 --independence self-reported --basis single-operator
```

Claims may lose corroboration until those sources are judged again. That is
intentional: an unreadable old vocabulary must not silently count as current
evidence.

## Completion check

Before handing the migrated notebook on:

```bash
flip source list
flip show --claims
flip doctor
```

Fix every ERROR. Read every WARN and either repair it or record why it remains.
The detailed format history is in [SPEC.md](../SPEC.md) and
[CHANGELOG.md](../CHANGELOG.md).
