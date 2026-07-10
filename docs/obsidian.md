# flip + Obsidian — the test drive

Success for flip is humans and agents collaborating gracefully **in the same
files** (SPEC §12). Obsidian is the reference human client: a notebook is
already a valid vault, and `flip obsidian` plus the packaged companion
plugin close the remaining gap — doctor findings, verification status, and
id navigation, live in the sidebar.

## 1. Prepare the vault

From anywhere inside a notebook (or a beat):

```bash
flip obsidian
# created .obsidian/app.json (useMarkdownLinks: true, newLinkFormat: relative)
# installed .obsidian/plugins/flip-notebook/ (manifest.json, main.js, styles.css)
# enabled flip-notebook in .obsidian/community-plugins.json
```

What it does, and nothing more:

- **Merge-writes `.obsidian/app.json`** with `useMarkdownLinks: true` and
  `newLinkFormat: "relative"` — flip writes relative markdown links
  (SPEC §9), and this makes the links Obsidian authors (drag a note into a
  page, paste a link) match them. Every other key in an existing app.json
  survives.
- **Installs the flip plugin** into `.obsidian/plugins/flip-notebook/` and
  enables it in `community-plugins.json`. Pass `--no-plugin` for the link
  config alone.

It is idempotent — a second run changes nothing and says so — and it
refuses to run anywhere that isn't a notebook or beat root.

`.obsidian/` is **editor-local state**: flip never reads it, exports never
ship it, and if the notebook is committed it belongs in the repo's
gitignore.

## 2. Open the folder as a vault

Obsidian → "Open folder as vault" → pick the notebook directory. First
time in this vault: **Settings → Community plugins → turn off Restricted
mode**, then enable **flip** in the list (already toggled on by
`flip obsidian`; Obsidian just needs restricted mode off to load it).

The plugin runs the `flip` CLI in the vault directory. If `flip` isn't on
the PATH Obsidian inherits (common on macOS, or with `uv tool` installs in
non-login shells), set the plugin's **flip path** setting to the absolute
binary path (`which flip`).

## 3. What vanilla Obsidian already gives you

- **Properties panel = frontmatter.** Open any `references/` page: grade,
  independence, freshness are editable properties. Re-grading a source
  there is a legitimate flip operation — the next `flip doctor` run
  validates it after the fact.
- **`[[A3]]` resolves.** Every entity page carries its id in `aliases`, so
  id wikilinks find the page whatever its filename; filenames stay human
  slugs.
- **Graph view lights up.** flip's citations and listings are relative
  markdown links; the folder taxonomy (references / claims / decisions /
  questions / sessions) reads as intended structure.

## 4. What the plugin adds

- **The flip panel** (right sidebar; ribbon stethoscope icon, or the
  "flip: Open doctor & hot view panel" command):
  - **Doctor** — findings from `flip doctor --json`, ERRORs before WARNs,
    each row a level badge · code · message. Rows with a file path open
    that file on click.
  - **Hot view** — from `flip show --json`: open questions and claims
    needing work, each row clickable (resolved via `flip open <id>`).
  - A Refresh button in the header; the panel also auto-refreshes ~2.5s
    after a vault file changes (toggle in settings).
- **Status bar** — `flip: 0❗ 3⚠ · 2 claims open` (doctor error/warn
  counts, claims needing work). Click it to open the panel.
- **Open by id** — the "flip: Open by id" command suggests every source,
  claim, and question (id + title/text); free-typed ids (D2, H1…) work
  too. Choosing one opens the page.

## 5. Two caveats

- **Don't hand-edit generated views.** `index.md` bodies (the root and
  each entity dir's listing) and `log.md` are projections flip rewrites on
  every mutating command — edit the entity pages, not the listings.
- **Beat roots degrade gracefully.** Opened at a beat root, the panel
  explains that doctor and the hot view work at notebook roots — open a
  notebook inside the beat (`notebooks/<slug>/`) as its own vault. (`flip
  obsidian` still works at a beat root, so the vault link config and
  plugin are in place for browsing threads.)

## Uninstall

Delete `.obsidian/plugins/flip-notebook/` (or toggle the plugin off).
Nothing else in the notebook was touched.
