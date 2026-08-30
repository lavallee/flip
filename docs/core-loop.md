# The Flip core loop

Flip has one operating lifecycle across a notebook, beat, or workspace:

```text
orient → select → open → work → check → close → continue or stop
```

Core owns the inspectable path and receipts. A human or agent supplies research
judgment. A harness may decide when to invoke another pass. Flip is not a
scheduler, daemon, model runner, or work-DAG engine.

## 1. Orient

Run `flip next`. At the nearest scope it returns a bounded descriptor: kind,
disciplines, workflow pin and suggested phase, enabled plugin pins, latest
session receipt, applicable beat policy, and unreadable children. It does not
load the whole notebook into context.

```bash
flip next --json
flip next --limit 1 --explain
```

At a notebook, core reads in-flight claims, dispatched commissions, due work,
and open questions. At a beat it adds child notebooks and ungraduated threads.
At a workspace it aggregates bound notebooks using their handles. The old
`flip beat next` remains the explicit beat spelling and uses the same path.

## 2. Select

Every frontier row has `lane`, `notebook`, `id`, `text`, and `why`. Core rows
are deterministic. Enabled `frontier.provide@1` handlers may add rows and
`frontier.filter@1` handlers may transform them. `--explain` names every
handler, how many rows it saw or returned, declared reasons, declines, and
failures. A failed handler is skipped; it cannot sink the core frontier.

An empty list is not proof of completion. The beat's `auto.stop` prose, or the
human's stated stopping rule, decides whether empty means done or blocked.

## 3. Open

A pass is a Work Session, not a second entity type:

```bash
flip session start weekly-refresh \
  --workflow weekly-watch@1 --phase refresh --item sources:Q1 \
  --model <model> --tools <tool>
```

The session stores the exact resolved workflow version, phase, selected item,
and enabled extension versions. If `--phase` is omitted, Flip uses `flip
workflow next`'s receipt-derived suggestion. It never executes the phase.

## 4. Work

The workflow guide tells the actor what this phase is for and which inspectable
outputs it should leave. The actor uses normal Flip commands. No plugin hook can
write canonical pages, allocate ids, edit immutable custody, or append to an
event ledger on the actor's behalf.

## 5. Check

Run core doctor checks. Enabled `check.provide@1` providers may add read-only
domain findings. Doctor gives those findings the stable code
`extension-check`, while preserving the qualified handler and provider-local
code in the message. A provider failure is `extension-failure`; it is never a
clean result.

```bash
flip doctor
flip doctor --code extension-check
```

## 6. Close

Declare the outputs and checks that actually happened:

```bash
flip session end weekly-refresh \
  --summary "refreshed Q1; no new corroborating source" \
  --output Q1 --output log/passed.jsonl --check doctor
```

The session frontmatter gains a `flip-session-receipt/1` object. Flip derives a
conservative floor from append-only events and canonical entity-page mtimes
since `started`, then records declared outputs/checks. A `receipt.filter@1`
handler may enrich the receipt, but core measurements overwrite any attempted
rewrite of them.

The receipt can establish “two provenance events and one entity page changed.”
It cannot establish reader relevance, correctness, demand, commercial value, or
an external outcome, and says so in `does_not_establish`.

## 7. Continue or stop

Run `flip next` again. For a reusable workflow, `flip workflow next --explain`
derives state from the newest matching Work Session:

- an open session resumes its phase;
- a closed session suggests that phase's `next`;
- a closed terminal phase reports complete;
- no matching receipt starts at `entry`.

There is no mutable current-phase file to race or repair. A recurring workflow
may point its audit phase back to orient; the recorded stop condition still
decides whether another pass runs.

## Safe loop harness

A harness needs only a local read, one explicitly authorized work episode, and
the durable receipt:

```bash
cd /path/to/scope
flip next --json --limit 1 --explain > /tmp/flip-next.json
your-agent-runtime --context /tmp/flip-next.json --prompt-file prompts/pass.md
```

For multiple writers, this does not replace normal repository coordination.
Give workers disjoint item custody where possible, make canonical writes through
Flip, and merge append-only ledgers without deleting either side. See
[`extensions.md`](extensions.md) for hook authority and [`loops.md`](loops.md)
for beat policy.
