# Public source plugins

Flip owns custody, judgments and claims. These optional tools acquire or derive
material; their linked Flip bundles supply workflows and interpretation skills.
Installing a command, linking definitions, configuring a lane, and successfully
capturing a source are separate steps. None assigns a source grade.

| Source job | Public adapter | Check before relying on it |
|---|---|---|
| GitHub issues, PRs and Discussions with later replies/state | [flip-github](https://github.com/lavallee/flip-github) | Read comments and lifecycle; closure or merge does not prove a fix reached users. Discussions need authorized GitHub credentials. |
| Original PDF, DOCX, XLSX or PPTX and reading derivatives | [flip-documents](https://github.com/lavallee/flip-documents) | MarkItDown is optional. Check layout and numbers against originals; use structured cells for spreadsheet identifiers/formulas when available. Scans need an explicit OCR tool. |
| A named Reddit conversation | [flip-reddit](https://github.com/lavallee/flip-reddit) | RSS is partial. Authenticated backend support depends on the installed version and authorized credentials; inspect expansion limits and unresolved comments. Votes are not corroboration. |
| Timestamped YouTube captions or imported ASR | [flip-youtube](https://github.com/lavallee/flip-youtube) | Read track origin, language and coverage. Check quotations against audio. Backend installation does not establish live availability. |
| Exact DOI/arXiv identity, version and optional full text | [flip-papers](https://github.com/lavallee/flip-papers) | Metadata is not the paper. Use `--require-full-text` when the task needs the PDF; DOI full text requires a real Unpaywall contact email. |

For an editorial evidence handoff, use
[flip-publication](https://github.com/lavallee/flip-publication): definitions and
templates only, with optional external Pandoc/Quarto rendering. It acquires no
sources and does not establish editorial approval or publication.

## Get and connect the relevant tool

Read the selected repository's README and release notes for current extras,
backend flags and lane stanzas. Prefer a tagged release for repeatable work.
For example, install the paper adapter independently of the notebook/project:

```bash
uv tool install --python 3.12 'git+https://github.com/lavallee/flip-papers@v0.1.1'
flip-papers --help
flip plugin doctor "$(flip-papers --plugin-path)"
flip plugin link "$(flip-papers --plugin-path)"
```

The documents, Reddit and YouTube packages also expose `--plugin-path`.
For GitHub's definitions or the publication bundle, use a persistent checkout:

```bash
git clone https://github.com/lavallee/flip-publication /path/to/flip-publication
flip plugin doctor /path/to/flip-publication
flip plugin link /path/to/flip-publication
```

Replace the destination with your own persistent tool directory. Linking these
definition bundles requires no `flip plugin enable`; it does not configure a
fetcher, install conversion dependencies, or authenticate a backend. Do not
add a Codex/Claude marketplace entry merely to bind a Flip fetcher.

Merge the selected README's named lanes into the intended
`$FLIP_HOME/config.toml`; avoid duplicate TOML tables and preserve existing lanes.
For example:

```toml
[fetchers.paper]
papers = "flip-papers {id} {dest} --require-full-text"
[fetchers.web]
papers = "flip-papers {url} {dest} --require-full-text"
```

The web lane also supports URL-based rechecks in Flip 0.22. Confirm with
`flip config show`, then capture within an attributed notebook session:

```bash
flip add-source arxiv:1706.03762v1 --kind paper --via papers
```

Open what landed, derive text through `flip extract` using the adapter README's
media-family lanes, then grade it. Explicitly select `--kind social` for Reddit
and `--kind talk` for YouTube. A linked workflow does not imply these lanes exist.
When current state matters, exercise `flip source recheck <id> --via <lane>`.
Check the adapter version's refresh semantics: older YouTube bundles could miss
a transcript-only change when audio was the largest file.

## Discovery tools are leads

Tools such as [last30days](https://github.com/mvanhorn/last30days-skill) can find
candidate discussions and videos across sources. Their ranked or shortened
results are discovery output. Capture the selected original thread, video or
document through a suitable lane before citing it; preserve timestamps,
parentage and coverage instead of treating a summary as the whole source.
Distinguish no results from access failure or partial coverage. Relevance,
recency and engagement scores do not set Flip grades or corroboration counts.
