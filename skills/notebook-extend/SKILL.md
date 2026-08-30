---
name: notebook-extend
description: Route requests to make a Flip process reusable, team-local, or shareable to the smallest correct extension type: kind, discipline, workflow, filter, adapter, skill, or plugin.
---

# notebook-extend

Use this when a person says “our process,” “every time,” “make this reusable,”
“let agents do this,” or “share this.” First inspect `flip extension list`,
`flip workflow list`, `flip kind list`, and `flip discipline list`; adapting a
nearby definition is cheaper and more legible than inventing another noun.

Map what they are changing:

| Their change | Author |
|---|---|
| the finished output | kind |
| the standard or verification bar | discipline |
| the sequence of work | workflow |
| a computed list, transformation, or domain check | filter/provider |
| a private external tool binding | adapter in Flip integration config |
| agent behavior and judgment | skill |
| a shareable combination | plugin bundle |

Do not turn a one-off instruction into infrastructure unless they asked to
share it or there are repeated runs to extract. A requested team-local process
already supplies the reuse case.

Prefer a data-only definition. Introduce executable filters only when the need
is a stable computed seam that two independent workflows could use. Never give
a plugin direct notebook mutation authority: it proposes context, candidates,
filtered data, or findings; canonical Flip commands perform writes.

Hand off by naming the extension noun, why it fits, its source path, how it was
validated, and which evidence state actually exists: linked is not enabled;
enabled is not exercised; a fixture is not a human outcome.
