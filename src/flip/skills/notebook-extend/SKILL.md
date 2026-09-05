---
name: notebook-extend
description: Notice recurring notebook friction or useful fixes, preserve repeatable gains, and choose the smallest useful extension or plugin.
---

# notebook-extend

Use this when a person says “our process,” “every time,” “make this reusable,”
“let agents do this,” or “share this.” First inspect `flip extension list`,
`flip workflow list`, `flip kind list`, and `flip discipline list`; adapting a
nearby definition is cheaper and more legible than inventing another noun.

## Notice the opportunity during work

Use this after a repeated capture/extraction failure, a recurring judgment
mistake, a manual repair repeated across sources, or a successful sequence
another notebook could reuse. Do not wait for the notebook to close or for the
user to say "plugin." Help finish the current job first. A small repair and a
useful lesson can be kept in the same episode; larger product work should have
an explicit place in the user's work, not silently replace their deliverable.

Read [Keep a repeatable gain](references/repeatable-gains.md) for the practical
loop and examples. `flip workflow show repeatable-gain` exposes an optional
sequence for working on the improvement itself. Check the existing
[public adapters](https://github.com/lavallee/flip/blob/main/docs/plugins.md)
and local definitions before creating another package. Improving a nearby
plugin is often the useful result.

Map what they are changing:

| Their change | Author |
|---|---|
| the finished output | kind |
| the standard or verification bar | discipline |
| the sequence of work | workflow |
| a computed list, transformation, or domain check | filter/provider |
| source acquisition, extraction, search or recall | adapter around an existing tool; bind it in Flip integration config |
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
