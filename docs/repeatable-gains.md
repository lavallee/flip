# Make the next run easier

Flip should help users keep the improvements they discover while doing real
work: fewer repeated repairs, better preserved evidence, and a method another
person can pick up. Start with a recognizable problem. Build a plugin when it
is a useful way to share the solution.

## From a problem to something reusable

When the same capture fails, a conversion damages a value, or a handoff needs
the same repair again, inspect the notebook's actual source and session trail.
Solve the current case, then preserve the working method and its limits in
`lessons.md` or a decision page. You can do this while a notebook is active.

Try the improvement on another relevant case. Compare the old and new method
on the same inputs: did a code stay intact, did a later reply reach custody,
did a reviewer find the unresolved question without asking? Keep measured
benefits separate from hoped-for time savings. A failed replay can still yield
a valuable lesson about when a method is appropriate.

Use the optional built-in workflow when developing the improvement itself:

```bash
flip workflow show repeatable-gain
# In the notebook where you want to track the improvement:
flip workflow use repeatable-gain
flip workflow next --explain
```

This explicitly changes that notebook's workflow pin. It suggests four phases:
**select → solve → replay → keep**. It runs no tools and creates no plugin by
itself. Record the phase work through ordinary sessions; the terminal phase
stops. Keep a lesson if a shared tool is not warranted.

```bash
export FLIP_ACTOR="agent:builder"
flip session start gain-01-select --workflow repeatable-gain --phase select
# Record the problem, source/session pointers and comparison in lessons.md.
flip session end gain-01-select --summary "Selected one repair and its baseline." \
  --output lessons.md
flip workflow next --explain
```

## Improve what already fits

Check [public plugins](plugins.md), `flip extension list` and
`flip workflow list` first. Common useful changes include:

- an adapter around a maintained converter that preserves fields the ordinary
  reading output loses;
- a source-refresh workflow that captures later replies and state changes;
- a transcript plugin fix that catches changed text even with unchanged audio;
- a handoff template that makes evidence limitations easy for an editor to find.

A single skill, workflow or template may be enough. Package the parts together
when they form a useful shared tool. Avoid forcing a local tool binding or a
one-off workaround into a universal abstraction. Private configuration stays
local; standalone tools can serve people who do not use Flip.

## Make it usable by someone else

A shared plugin needs a recognizable job, setup instructions, a runnable small
example, expected output and honest failure behavior. Put the selection cue in
the relevant agent skill so the next agent knows when to get it. Run the
example through the actual consumer commands, beyond manifest validation.
Public fixtures should be synthetic or deliberately cleared for sharing; source
custody and credentials stay in their proper locations.

Report what exists precisely: a local prototype, a tested fixture, successful
live acquisition, another user's reuse, and a public release are different
results. None alone proves saved time or improved outcomes. See
[extension authoring](extensions.md#authoring-and-sharing) for packaging and
activation, and the packaged notebook-extend skill for the working checklist.

There is no plugin quota or mandatory improvement project at every handoff.
The point is to stop paying for the same avoidable problem when a useful fix
can be kept.
