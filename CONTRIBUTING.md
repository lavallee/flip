# Contributing to flip

flip is at the **spec stage** — the highest-value contributions right now are
critiques of the format itself: places where the spec would fight real
reporting or research practice, gaps in the provenance model, profile shapes
you'd need that don't fit.

## How

- **Open an issue** for design discussion — the smaller and more concrete the
  scenario, the better ("here's a capture case the provenance record can't
  express" beats "custody should be more flexible").
- **PRs against SPEC.md** are welcome for wording, structure, and fixes. For
  substantive design changes, open an issue first; accepted changes land with
  a CHANGELOG entry and, when they alter meaning, a version bump.
- Spec changes that alter the meaning of existing files on disk (ledger
  fields, status enums, layout) are **breaking** and versioned accordingly —
  notebooks in the wild must never be silently reinterpreted.

## Style

- Plain text first; examples over abstractions; every normative rule should
  say what failure it prevents.
- Keep the core small. New requirements belong in a profile unless every
  notebook needs them.

## Code (upcoming)

The `flip` CLI will live in this repo. Once it lands: tests required for
behavior changes, CI must be green, and the library core stays
filesystem-only — no network calls, no LLM calls, no required services.
