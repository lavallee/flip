---
type: Claim
id: C9
aliases:
- C9
description: In DeepTRACE's audit of public systems accessed on 2025-08-27, deep-research
  modes were one-sided on 54.7% to 94.8% of debate queries, while citation accu…
status: verified
load_bearing: true
sources:
- id: A4
  role: subject
  resource: /references/deeptrace-deep-research-citation-audit.md
  title: 'DeepTRACE: Auditing Deep Research AI Systems for Tracking Reliability Across Citations
    and Evidence'
first_asserted: '2026-08-20'
generated:
  by: agent:codex
  at: '2026-08-20T15:40:38Z'
tests:
- probe: attribution
  error: The captured paper does not report these one-sidedness and citation-accuracy ranges
    for deep-research configurations.
  would_detect: Table 1 or the results discussion would show different minima and maxima.
  if_absent: Table 1 reports one-sidedness values spanning 54.67 to 94.8 among the nonzero
    deep-research modes and citation accuracy spanning 31.4 to 79.1 across the evaluated configurations.
  result: survived
  against:
  - A4
  at: '2026-08-20T15:40:38Z'
  by: agent:codex
---

In DeepTRACE's audit of public systems accessed on 2025-08-27, deep-research modes were one-sided on 54.7% to 94.8% of debate queries, while citation accuracy across the evaluated deep-research configurations ranged from 31.4% to 79.1%.[^A4]

[^A4]: [DeepTRACE: Auditing Deep Research AI Systems for Tracking Reliability Across Citations and Evidence](../references/deeptrace-deep-research-citation-audit.md)
