# Publication readiness check

This provider demonstrates a team-local editorial rule without adding it to
Flip core. Once explicitly enabled, `flip doctor` runs the check and reports a
stable core code (`extension-check`) whose message preserves the provider's
qualified id and local `missing-disclosure` code. It never creates the file or
edits the notebook to make its own finding disappear.

The fixture path is illustrative; use `flip filter test` with a fixture whose
`scope.root` points at a disposable notebook. A passing check establishes only
that this file predicate passed at that path and time.
