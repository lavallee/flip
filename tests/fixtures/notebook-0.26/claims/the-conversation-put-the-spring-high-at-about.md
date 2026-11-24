---
type: Claim
id: C2
aliases:
- C2
description: The conversation put the spring high at about 4.2 m.
status: asserted
load_bearing: false
sources:
- id: T1
  role: subject
  excerpts:
  - high
  resource: /references/chat.md#high
  title: chat.md
first_asserted: '2026-11-24'
generated:
  by: human:jane
  at: '2026-11-24T12:03:02Z'
tests:
- probe: attribution
  error: not said
  would_detect: absent from line
  if_absent: line carries it
  result: survived
  against:
  - T1§high
  at: '2026-11-24T12:03:03Z'
  by: human:jane
---

The conversation put the spring high at about 4.2 m.[^T1]

[^T1]: [chat.md](../references/chat.md#high) — high
