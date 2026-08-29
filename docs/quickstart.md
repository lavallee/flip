# CLI quickstart

This is the shortest path from an installed `flip` command to a notebook that
captures a source, judges it, verifies a claim, and passes its structural
check. It uses a local fixture, so no network or integration configuration is
required.

For harness installation, PATH fixes, updates, and removal, start with
[Getting started](getting-started.md).

## Preflight

```bash
flip --version
flip kind list
```

Set attribution before the first write. A `pursuit` notebook creates Q1 during
`flip new`, so setting the actor afterwards is too late:

```bash
export FLIP_ACTOR="human:your-name"  # or agent:claude, agent:codex, tool:name
```

## Run the first notebook

Create a tiny source fixture, then open a one-question pursuit:

```bash
printf 'district,enrollment\nNorth,100\n' > districts.csv
flip new enrollment-check --kind pursuit --title "What enrollment does the fixture report?"
cd enrollment-check
flip session start first-pass --tools local-files
flip log "started: check the enrollment fixture"
```

The examples use a POSIX shell. In PowerShell, create the fixture with
`@("district,enrollment", "North,100") | Set-Content -Encoding utf8
districts.csv`, and enter the backslash-wrapped `flip grade` command below as
one line.

`flip new` prints the actor it used. Confirm it is the intended human, agent,
or tool before continuing.

Capture and read the source:

```bash
flip add-source ../districts.csv --note "first-run fixture"
flip open F1
```

Capture creates custody, not authority. After checking the file, record the
judgment separately:

```bash
flip grade F1 --independence independent --basis measured --base-defined \
  --method "direct row inspection" --freshness fresh \
  --notes "one-row tutorial fixture; base and value are explicit"
flip grade F1 --explain
```

Assert what the work will rely on, then ask flip to apply the profile's gate:

```bash
flip claim add "The fixture reports enrollment of 100" --source F1 --load-bearing
flip claim status C1 verified
```

Finish the episode and inspect what remains:

```bash
flip session end first-pass --summary "captured the fixture and verified its reported value"
flip show --claims
flip doctor
```

Success means:

- `F1` resolves to a source page and raw custody;
- `C1` is verified through the recorded source judgment;
- the session has an end summary;
- `flip doctor` exits 0.

## Enable ordinary URL capture

Run this once per user environment, outside or inside a notebook:

```bash
flip config init
flip config show
```

Then capture URLs through the configured lane:

```bash
flip add-source https://example.com/report --note "why this report matters"
```

Open what landed before citing it. A successful HTTP response can still be a
consent wall or JavaScript shell; flip warns on thin captures.

## Choose a real notebook kind

`flip kind list` includes rigor profiles and outcome kinds, along with the
plain-language phrases they accept. Common choices:

| Need | Kind |
|---|---|
| One question | `pursuit` |
| Fast screen | `scout` |
| Publishable survey | `research-review` or `lit-review` |
| Data reconciliation | `data-investigation` |
| Evidence-backed choice | `decision-packet` |
| Source spine | `ledger` |
| Confidential work | `engagement` |

Most kinds initially create `index.md` and `notebook.md`; `pursuit` also seeds
Q1 and `drafts/question-plan.md`. Entity directories otherwise appear with
use.

## Before real custody grows

Decide how `sources/raw/` belongs in version control. The default recommendation
is Git LFS:

```bash
git lfs track "sources/raw/**"
```

Alternatives are to keep raw custody local while committing its provenance
ledger, or to commit it directly and accept repository growth. `flip doctor`
warns when tracked custody becomes large without an LFS filter.

## Continue

- [Evidence workflow](evidence-workflow.md) — grades, claims, tests, questions,
  transcripts, ids, and renames.
- [Integrations](integrations.md) — capture and extraction lanes.
- [Migration](migration.md) — older notebooks.
- [Obsidian](obsidian.md) — use a notebook as a vault.
- `flip cli` — the always-current command map.
