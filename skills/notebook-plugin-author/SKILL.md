---
name: notebook-plugin-author
description: Package Flip kinds, disciplines, workflows, skills, examples, and typed filters into an inspectable versioned local plugin bundle.
---

# notebook-plugin-author

Start definition-only. A plugin is the folder that transports capabilities;
it is not another research concept.

Before packaging, name the user problem, its trigger, and the result the
plugin helps produce. Inspect nearby plugins and prefer extending one that
already owns the job. Use notebook-extend's repeatable-gain guide to retain a
working example, a relevant second case and honest limits. A request to share
a new process can start a prototype; label it as such until tried.

The README should let a new user answer: Is this my problem? How do I get it?
What do I run? What should land? What can fail? What was actually verified?
Teach the applicable agent skill when to select this plugin. Include the
upstream tool/dependency boundary and preserve private evidence outside the
shared bundle. A package that only passes manifest checks is not yet a usable
solution to the user's problem.

1. Create a directory with `flip-plugin.toml`, README, license, and only the
   needed noun folders. Use a qualified id such as `team/review-pack`, a
   semantic version, `requires_flip`, and an honest capability list.
2. Put definitions under `[exports]`. Run their own checks, then `flip plugin
   doctor <path>`. Link with `flip plugin link <path>` and inspect `flip
   extension list` without enabling it.
3. Include the smallest public-clean fixture and expected output that would
   catch a broken definition. State what passing the fixture does not prove.
4. Add an executable `[[filters]]` only for a named hook contract. Declare its
   protocol, command, timeout, data needs, dependencies, network/credential
   needs, and ordering. Prefer stdlib and checked-in inputs.
5. Exercise it without activation using `flip filter test <qualified-id>
   --fixture <json>`. Ask before `flip plugin enable`: executable handlers run
   with the local user's operating-system permissions and Flip's transport is
   not a sandbox.
6. After explicit enablement, inspect `flip hook show <hook> --handlers`, run
   `flip next --explain` or `flip doctor`, and inspect `.flip/extensions.lock`.

Never report cataloged, materialized, valid, enabled, exercised, authenticated,
or useful as synonyms. Never let a filter edit canonical pages or ledgers, hide
a failure, silently win an id collision, or activate merely because its bundle
was downloaded or linked.
