---
type: Claim
id: C1
aliases:
- C1
description: 'flip''s core depends on exactly two third-party libraries: click and PyYAML'
status: verified
load_bearing: true
sources:
- id: F2
  resource: /references/flip-pyproject.md
  title: pyproject.toml
independent_corroboration: 0
first_asserted: '2026-07-25'
generated:
  by: human:marc
verified:
- by: human:marc
  at: '2026-07-25'
  method: recomputation
  against:
  - F2
  note: The site build reads pyproject.toml at every build and publishes the dependency list
    from it; a drift changes the rendered page rather than going unnoticed.
---

flip's core depends on exactly two third-party libraries: click and PyYAML[^F2]

[^F2]: [pyproject.toml](../references/flip-pyproject.md)
