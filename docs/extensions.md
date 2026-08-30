# Workflows, plugins, filters, and hooks

Flip's extension surface keeps the nouns separate:

| Noun | Answers |
|---|---|
| kind | What are we making? |
| discipline | What standard is it held to? |
| workflow | What reusable sequence helps make or maintain it? |
| hook | At what stable lifecycle point may something contribute? |
| provider/filter | What contribution or transformation attaches there? |
| adapter | Which private external capability fills capture, extraction, research, or recall? |
| skill | What behavior and judgment should an agent learn? |
| plugin | Which versioned directory transports one or more of the above? |

A plugin is packaging, not a new epistemic concept.

## Workflow registry

`flip workflow list` discovers definitions in this order:

1. built-ins shipped by Flip;
2. exports from locally linked plugins;
3. loose user files in `$FLIP_HOME/workflows/`;
4. notebook files in `.flip/workflows/`;
5. a `kind:<id>` compatibility adapter for an existing kind's inline phases.

Public ids never use last-wins replacement. A collision is an error. Plugin
workflow ids are qualified (`publisher/plugin/workflow`); a short id resolves
only when unambiguous. Notebook manifests store exact pins such as
`workflow: weekly-watch@1.0`.

The smallest definition is one TOML file:

```toml
id = "source-audit"
version = "0.1"
summary = "Recheck source custody and judgment before handoff."
entry = "orient"

[[phase]]
id = "orient"
guide = "Read doctor and choose one source finding."
produces = ["selected-source"]
next = "repair"

[[phase]]
id = "repair"
guide = "Use canonical capture, extraction, or grade commands."
produces = ["source-event-or-passed-event"]
next = "audit"

[[phase]]
id = "audit"
guide = "Run doctor and close the session receipt."
produces = ["doctor-run", "session-receipt"]
```

Use `workflow new`, `check`, `show`, `use`, and `next`. Built-in
`question-pursuit` and `weekly-watch` definitions use exactly this public
format.

## Plugin registry and honest states

A local bundle is self-describing before installation:

```text
my-pack/
  flip-plugin.toml
  README.md
  LICENSE
  kinds/ disciplines/ workflows/ skills/
  filters/ examples/ tests/
```

```toml
[plugin]
id = "team/my-pack"
version = "0.1.0"
summary = "Team review process."
license = "MIT"
requires_flip = ">=0.21"
capabilities = ["definitions"]

[exports]
workflows = ["workflows/review.toml"]
skills = ["skills/notebook-review/SKILL.md"]
examples = ["examples/tiny-review/"]
```

The CLI keeps five states distinct:

| State | Receipt |
|---|---|
| cataloged | metadata exists in some catalog; Flip core has no catalog yet |
| materialized | the bundle directory exists on this machine |
| valid | `plugin doctor` accepted its manifest and referenced files |
| enabled | this notebook, beat, or workspace explicitly opted in |
| exercised | `filter test` returned a compatible result for one fixture |

`plugin link <path>` records an already-materialized path in
`$FLIP_HOME/plugins.json`. It does not download or enable anything. `plugin
enable <id>` writes an exact version to the scope and a deterministic
`.flip/extensions.lock` with path and bundle hash. Doctor reports missing pins,
path/version drift, and changed bundle content. Review a change before
re-enabling it. `plugin disable` removes scope authority; `plugin unlink`
removes only the user-registry pointer, so any forgotten scope pin remains an
honest unresolved doctor finding rather than being silently erased.

Kinds and disciplines exported by plugins use their ordinary ids and collisions
are refused. Plugin workflows are qualified because the workflow registry is
new and can make that identity guarantee without breaking old manifests.

## Hook contracts

The first hook set is deliberately closed:

| Hook | Strategy | Input → output | Failure |
|---|---|---|---|
| `context.provide@1` | provide all | scope + selected item → context refs | skip and explain |
| `frontier.provide@1` | provide all | scope + policy + rows → candidate rows | skip and explain |
| `frontier.filter@1` | ordered chain | candidate rows → candidate rows + reasons | keep prior rows; explain |
| `check.provide@1` | provide all | scope → findings | doctor warning |
| `receipt.filter@1` | ordered chain | draft receipt → enriched receipt | keep prior receipt; explain |

Inspect them with `flip hook list`, `flip hook show frontier.filter`, and
`flip hook show frontier.filter --handlers --json`. `before` and `after`
relationships determine a stable topological order; an ordering cycle is
refused. Providers may decline with a reason.

Every executable handler uses the `flip-filter/1` transport: one JSON request
on stdin, one JSON object on stdout, direct argv execution, bundle root as cwd,
a declared timeout (maximum 60 seconds), and a 1 MiB output cap. Returned
frontier rows and findings are structurally validated. No handler is imported
into the Flip process.

An executable manifest entry:

```toml
[plugin]
id = "team/publication"
version = "0.1.0"
capabilities = ["execute:filter", "read:notebook"]

[[filters]]
id = "disclosure"
hook = "check.provide@1"
protocol = "flip-filter/1"
command = ["python3", "bin/check.py"]
needs = ["execute:filter", "read:notebook"]
timeout = 5
after = ["other-team/base-check"]
```

This containment is not a security sandbox. Once explicitly enabled, the
command has the operating-system permissions of the Flip user. Capability
declarations make authority inspectable; they do not enforce it. Prefer
definition-only bundles and checked-in, dependency-free filters. Keep private
capture/extract/research/recall bindings in the existing integration config.

## Authoring and sharing

Agents should use the packaged `notebook-extend` skill to route a reusable
request, `notebook-workflow-author` to interview and exercise a phase sequence,
and `notebook-plugin-author` to package it. The preferred loop is:

```text
describe → fork/scaffold → edit plain files → check → run tiny fixture
→ inspect receipt → share the directory
```

Start with [`examples/plugins/systematic-review-pack/`](../examples/plugins/systematic-review-pack/),
then inspect the executable [`local-worklist-provider`](../examples/plugins/local-worklist-provider/)
and [`publication-readiness`](../examples/plugins/publication-readiness/).
