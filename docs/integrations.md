# Integrations

flip owns the notebook and provenance protocol, not the tools that search,
fetch, extract, or recall. Those tools are configured under four roles in
`$FLIP_HOME/config.toml` (default `~/.flip/config.toml`).

## Optional public adapters

See [Public source plugins](plugins.md) for GitHub, documents, Reddit, YouTube,
papers and editorial handoffs, including how to install a tool, link its
definitions and configure a named lane. Start there when ordinary URL capture
cannot preserve the source you need.

## Start with web capture

```bash
flip config init
flip config show
```

The starter config enables ordinary URL capture with the bundled
`flip-fetch` helper:

```toml
[fetchers]
web = "flip-fetch {url} {dest}"
```

`flip-fetch` performs a directed stdlib HTTP GET, follows redirects, extracts
the page title, and records the canonical URL and capture method. It does not
crawl. JavaScript-rendered pages, authenticated sessions, and faithful page
archives need a purpose-built lane.

Local files bypass integrations and always copy directly.

## The four roles

```toml
[fetchers]
web = "flip-fetch {url} {dest}"
# paper = "flip-fetch --method publisher-api --email you@example.com {id} {dest}"
# media = "your-media-fetcher {url} {dest}"

[extractors]
# pdf = "your-pdf-extractor {src} {out}"

[research]
# find = "your-research-tool {query}"
# ask = "your-research-tool {query}"

[knowledge]
# recall = "your-knowledge-tool {query}"
```

Placeholders are:

- `{url}` — the target as entered;
- `{id}` — the target with a known identifier prefix such as `doi:` removed;
- `{query}` — a research or recall question;
- `{dest}` — a source capture directory;
- `{src}` and `{out}` — an extraction input and text destination.

Commands that omit `{dest}` or `{out}` may emit their artifact on stdout. flip
records the command, tool identity when available, hashes, and outputs.

Named lanes allow alternatives without hard-coding deployment tools into a
notebook:

```toml
[fetchers.web]
default = "flip-fetch {url} {dest}"
archive = "flip-fetch --method archive-replay {url} {dest}"
render = "your-browser-renderer {url} {dest}"
```

Use one with `flip add-source <url> --via archive`. `flip config show` is the
authoritative inventory for the current machine.

## Capture failures are findings

A command that exits successfully but writes nothing found no artifact. The
document may be gated, withdrawn, or unavailable through that route. Do not
paste an improvised fetch into the notebook; that loses custody and provenance.

The legitimate next moves are:

1. Change capture method: alternate representation, archive, publisher API,
   browser render/session, self-contained archive, or human-in-loop.
2. Ask the configured tool directly about capabilities flip does not invoke,
   then feed any resulting file back through `flip add-source <file>`.
3. Record an unreachable source without pretending to hold it:

   ```bash
   flip add-source <target> --record --note "<rungs tried and outcomes>"
   ```

4. Close a ruled-out route with `flip pass` and the reason.

Open every capture before citing it. `warning: thin capture` means the bytes
may be a consent wall, metadata record, or JavaScript shell rather than the
document.

## Return envelopes

A fetcher may write `flip.json` in `{dest}`, or emit JSON whose top-level
`flip` object carries neutral metadata such as `title`, `canonical_url`,
`strategy`, `retrieved_at`, `status`, `mime`, `from_cache`, and `backend_ref`.
Independence or freshness hints are notes for later judgment, never a grade.

## Text extraction

Raw custody is immutable. `flip extract <id>` creates
`sources/text/<id>.txt` through the configured extractor for the input's media
family and appends a derivation receipt:

```toml
[extractors.pdf]
text-layer = "pdftotext -layout {src} {out}"
ocr = "your-ocr-tool {src} {out}"
```

```bash
flip extract F1 --via text-layer
```

Name a lane after its method (`text-layer`, `layout-text`, `ocr`,
`markup-strip`, `structured`, or `transcript`) so flip can record it. An OCR
reading and a publisher text layer are not equivalent evidence.

flip ships no extractor. A zero-word extraction is logged as not extracted and
writes no text file; a very thin extraction is kept with a warning so it
cannot masquerade as the document's full text. Re-running a better extractor
may replace the derivative, while the append-only derivation history preserves
both attempts. Raw custody is never overwritten.

## Discovery, synthesis, and recall

- `flip find "<question>"` returns candidate leads; capture anything used.
- `flip ask "<question>"` stores cited synthesis as a grade-C lead, not
  evidence. Capture and judge its public citations separately.
- `flip recall "<question>"` searches local holdings and captures nothing.

Integration commands are operator configuration. Keep site-specific tools and
credentials outside public notebooks and portable skills.
