# Local worklist provider

The first executable hook example reads only this bundle's checked-in
`worklist.json` and returns typed frontier rows. It has no dependency, network,
credential, or notebook write path.

```bash
flip plugin doctor examples/plugins/local-worklist-provider
flip plugin link examples/plugins/local-worklist-provider
flip filter test example/local-worklist/worklist \
  --fixture examples/plugins/local-worklist-provider/fixtures/provider-input.json
cd /path/to/notebook
flip plugin enable example/local-worklist
flip next --explain
```

Try deleting `worklist.json` after linking: the handler declines with a reason.
Try making the command fail: the core frontier survives and `--explain` reports
`error-skipped`. Editing the bundle changes its content hash, so doctor reports
lock drift until the operator reviews the change and enables it again.

The executable runs with the current user's operating-system permissions. The
JSON protocol, timeout, and output cap contain failures; they are not a sandbox.
