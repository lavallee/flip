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
- F1
supports:
- /references/flip-spec
independent_corroboration: 0
first_asserted: '2026-07-25'
actor: human:marc
verifications:
- method: recomputation
  by: human:marc
  date: '2026-07-25'
  note: website/build.py step 'refused' executes flip claim status C1 verified against a one-source
    claim in a research-review notebook and requires a non-zero exit; if flip ever accepted
    it, the site build fails.
---

flip refuses to mark a load-bearing claim verified below its profile's corroboration bar, with a non-zero exit code

# Citations
[1] [SPEC.md](../references/flip-spec.md)
