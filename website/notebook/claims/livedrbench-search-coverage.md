---
type: Claim
id: C8
aliases:
- C8
description: The ICLR 2026 LiveDRBench paper reports that the best evaluated deep-research
  system achieved 0.55 overall F1 and that evaluated systems covered only about hal…
status: verified
load_bearing: true
sources:
- id: A3
  role: subject
  resource: /references/characterizing-deep-research-livedrbench.md
  title: 'Characterizing Deep Research: A Benchmark and Formal Definition'
first_asserted: '2026-08-20'
generated:
  by: agent:codex
  at: '2026-08-20T15:40:37Z'
tests:
- probe: attribution
  error: The captured paper does not report 0.55 overall F1 or about-half search-query coverage.
  would_detect: The abstract, results, or trace analysis would give different values or omit
    those findings.
  if_absent: The captured abstract states both 0.55 overall F1 for the best system and coverage
    of only about half the necessary search queries.
  result: survived
  against:
  - A3
  at: '2026-08-20T15:40:38Z'
  by: agent:codex
---

The ICLR 2026 LiveDRBench paper reports that the best evaluated deep-research system achieved 0.55 overall F1 and that evaluated systems covered only about half of the necessary search queries.[^A3]

[^A3]: [Characterizing Deep Research: A Benchmark and Formal Definition](../references/characterizing-deep-research-livedrbench.md)
