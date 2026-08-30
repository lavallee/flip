# Systematic review pack

This is a definition-only plugin: it contains no command and gains no execution
authority when enabled. Linking makes its exported kind, discipline, workflow,
skill, docs, and example discoverable.

```bash
flip plugin doctor examples/plugins/systematic-review-pack
flip plugin link examples/plugins/systematic-review-pack
flip extension list
flip workflow show example/systematic-review-pack/review-cycle
```

Copy the directory, change the ids and contract, and link the copy to author a
team-local variant. Flip refuses colliding public ids rather than silently
letting the last bundle win.
