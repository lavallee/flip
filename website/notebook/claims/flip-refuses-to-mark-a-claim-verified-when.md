---
type: Claim
id: C7
aliases:
- C7
description: flip refuses to mark a claim verified when a severe test found the error it went
  looking for, whatever the corroboration count
status: asserted
load_bearing: true
sources:
- id: F3
  resource: /references/spec.md
  title: SPEC.md
independent_corroboration: 0
first_asserted: '2026-08-10'
generated:
  by: agent:claude
  at: '2026-08-10T21:06:09Z'
tests:
- probe: attribution
  error: the captured spec does not specify this gate, or specifies it only as a doctor warning
    rather than a refusal
  would_detect: SPEC §7.1 in custody names no consequence for a misattributed or refuted exposure,
    or names one that leaves the status change available
  if_absent: the captured §7.1 states the refusal in those words, which is what the site page
    says it does
  result: survived
  against:
  - F3
  note: 'Read at line 1037 of the captured copy: ''verified` is refused when the exposure
    is `misattributed` or `refuted`''. Checked against custody, not the working tree.'
  at: '2026-08-10T21:06:09Z'
  by: agent:claude
---

flip refuses to mark a claim verified when a severe test found the error it went looking for, whatever the corroboration count[^F3]

[^F3]: [SPEC.md](../references/spec.md)
