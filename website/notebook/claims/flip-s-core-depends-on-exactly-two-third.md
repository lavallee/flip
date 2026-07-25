---
type: Claim
id: C1
aliases:
- C1
description: 'flip''s core depends on exactly two third-party libraries: click and PyYAML'
status: verified
load_bearing: true
sources:
- F2
supports:
- /references/flip-pyproject
independent_corroboration: 1
first_asserted: '2026-07-25'
actor: human:marc
verifications:
- method: recomputation
  by: human:marc
  against:
  - F2
  date: '2026-07-25'
  note: The site build reads pyproject.toml at every build and publishes the dependency list
    from it; a drift changes the rendered page rather than going unnoticed.
---

flip's core depends on exactly two third-party libraries: click and PyYAML

# Citations
[1] [pyproject.toml](../references/flip-pyproject.md)
