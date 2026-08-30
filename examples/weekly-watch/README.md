# Three-pass weekly watch

This is the small counterpart to a long-running autonomous corpus: one workflow,
three receipts, no scheduler. Run it in a disposable directory with Flip on the
path.

```bash
export FLIP_ACTOR=human:example
flip new tiny-watch --kind pursuit
cd tiny-watch
flip workflow use weekly-watch@1

# Pass 1: orient. Add a real Q1 with `flip question add` if the pursuit seed is absent.
flip next --explain
flip session start weekly-1 --workflow weekly-watch --phase orient --item Q1
flip session end weekly-1 --summary "selected Q1 and named the surface" \
  --output Q1 --check doctor
flip workflow next --explain

# Pass 2: refresh. In a real watch, capture or explicitly pass on what the surface returned.
flip session start weekly-2 --phase refresh --item Q1
flip log "weekly surface returned no new citable material"
flip session end weekly-2 --summary "zero-yield refresh recorded" \
  --output log/log.jsonl --check doctor
flip workflow next --explain

# Pass 3: assess. Record the evidence note before closing.
flip session start weekly-3 --phase assess --item Q1
flip question note Q1 "No change on the named surface this pass." --answers adjacent
flip session end weekly-3 --summary "Q1 evidence trail updated" \
  --output Q1 --check doctor
flip next --explain
```

Inspect the three pages under `sessions/`. Each records workflow, phase, item,
declared outputs/checks, enabled extension versions, and Flip's conservative
materiality floor. That floor says what changed in the bundle. It does not say
the pass was reader-relevant, correct, commercially useful, or worth repeating;
the mission's materiality and stop policies remain human or agent judgment.
