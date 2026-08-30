# Extension examples

These examples are intentionally small enough to inspect before running.

- [`weekly-watch/`](weekly-watch/) walks the same built-in workflow through
  three Work Session receipts and shows how the frontier changes.
- [`plugins/systematic-review-pack/`](plugins/systematic-review-pack/) is a
  definition-only bundle: kind, discipline, workflow, and agent skill.
- [`plugins/local-worklist-provider/`](plugins/local-worklist-provider/) is a
  dependency-free `frontier.provide@1` handler over a checked-in JSON file.
- [`plugins/publication-readiness/`](plugins/publication-readiness/) contributes
  a read-only editorial finding through `check.provide@1`.

Linking is local registration, not acquisition or activation:

```bash
flip plugin doctor examples/plugins/local-worklist-provider
flip plugin link examples/plugins/local-worklist-provider
flip plugin list
```

Run `flip plugin enable example/local-worklist` only from the notebook, beat,
or workspace that should trust its executable. A passed fixture establishes
protocol compatibility for that input. It does not establish usefulness,
research quality, external authentication, or safe behavior against live data.
