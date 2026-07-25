---
type: Claim
id: C2
aliases:
- C2
description: flip refuses to mark a load-bearing claim verified below its profile's corroboration
  bar, with a non-zero exit code
status: verified
load_bearing: true
sources:
- id: F1
  resource: /references/flip-spec.md
  title: SPEC.md
independent_corroboration: 0
first_asserted: '2026-07-25'
generated:
  by: human:marc
verified:
- by: human:marc
  at: '2026-07-25'
  method: recomputation
  note: website/build.py step 'refused' executes flip claim status C1 verified against a one-source
    claim in a research-review notebook and requires a non-zero exit; if flip ever accepted
    it, the site build fails.
---

flip refuses to mark a load-bearing claim verified below its profile's corroboration bar, with a non-zero exit code[^F1]

[^F1]: [SPEC.md](../references/flip-spec.md)
