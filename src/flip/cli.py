"""The flip CLI — one subcommand per module surface (SPEC §15).

Thin wiring only: every command resolves the enclosing notebook with
util.require_notebook_root() (so commands work from any subdirectory of a
notebook), calls exactly one library function, and prints a terse result.
All failure modes are SystemExit one-liners raised by the library; every
mutating library function refreshes the generated views itself, so the CLI
never regenerates twice. Read commands take --json so agents can consume
output without scraping.
"""

from __future__ import annotations

import difflib
import json
import re
import shlex
from dataclasses import asdict
from pathlib import Path

import click

from . import (
    beat as beat_mod,
    claims,
    commissions as commissions_mod,
    integrations,
    pages,
    doctor as doctor_mod,
    export as export_mod,
    importer as importer_mod,
    ledgers,
    migrate as migrate_mod,
    obsidian as obsidian_mod,
    profiles as profiles_mod,
    query as query_mod,
    registry,
    rename as rename_mod,
    resolve as resolve_mod,
    scaffold,
    sessions,
    sources,
    stance as stance_mod,
    transcripts as transcripts_mod,
    util,
    views,
    workspace as workspace_mod,
)
from .util import (
    find_notebook_root_pinned,
    find_workspace_root,
    format_excerpt_ref,
    require_notebook_root,
    set_cli_overrides,
)


class SuggestGroup(click.Group):
    """A group that answers an unknown subcommand — or a bare argument handed
    to a noun group (`flip question "text…"`, `flip claim C1 …`) — with a
    nearest-leaf *suggestion* and the subcommand list, never auto-execution
    (Lane E). Applied to every flip group so the hint is uniform."""

    def resolve_command(self, ctx, args):
        if args:
            name = args[0]
            if not name.startswith("-") and self.get_command(ctx, name) is None:
                self._suggest(ctx, name)
        return super().resolve_command(ctx, args)

    def _suggest(self, ctx, name: str) -> None:
        names = sorted(self.list_commands(ctx))
        near = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
        path = ctx.command_path  # e.g. "flip question"
        if near:
            guess = f"did you mean `{path} {near[0]}`? "
        elif "add" in names:
            guess = f'did you mean `{path} add "{name}"`? '
        else:
            guess = ""
        raise click.UsageError(
            f"no such subcommand '{name}' under `{path}` — {guess}"
            f"(subcommands: {', '.join(names)}; full command map: `flip cli`)",
            ctx=ctx,
        )


# --- flip cli: the compact command map, generated from the Click tree (Lane E) ---


def _arg_metavar(param: click.Argument) -> str:
    mv = param.metavar or param.name.upper()
    if param.nargs == -1 and "..." not in mv:
        mv += "..."
    return mv


def _long_opt(param: click.Option) -> str:
    return next((o for o in param.opts if o.startswith("--")), param.opts[0])


def _purpose(cmd: click.Command) -> str:
    """The one-line purpose: explicit short_help, else the docstring's first line."""
    if cmd.short_help:
        return cmd.short_help
    return (cmd.help or "").strip().split("\n", 1)[0]


def _leaf_commands(group: click.Group, prefix: tuple[str, ...] = ()) -> list:
    """(path, command) for every leaf under `group`, group paths first,
    sorted at each level — walked from the live tree so the map can't drift."""
    out = []
    for name in sorted(group.commands):
        sub = group.commands[name]
        path = (*prefix, name)
        if isinstance(sub, click.Group):
            out.extend(_leaf_commands(sub, path))
        else:
            out.append((path, sub))
    return out


def _command_display(path: tuple[str, ...], cmd: click.Command) -> str:
    parts = ["flip", *path]
    parts += [f"<{_arg_metavar(p)}>" for p in cmd.params if isinstance(p, click.Argument)]
    return " ".join(parts)


def _global_options(group: click.Group) -> list[str]:
    return [_long_opt(p) for p in group.params if isinstance(p, click.Option)]


def _leaf_json(path: tuple[str, ...], cmd: click.Command) -> dict:
    return {
        "command": " ".join(["flip", *path]),
        "group": " ".join(["flip", *path[:-1]]) if len(path) > 1 else "flip",
        "name": path[-1],
        "purpose": _purpose(cmd),
        "arguments": [_arg_metavar(p) for p in cmd.params if isinstance(p, click.Argument)],
        "options": [
            {"name": _long_opt(p), "required": bool(p.required)}
            for p in cmd.params
            if isinstance(p, click.Option)
        ],
    }


@click.group(name="flip", cls=SuggestGroup)
@click.version_option(package_name="flip-notebook")
@click.option("--notebook", "notebook_pin", default=None, envvar="FLIP_NOTEBOOK",
              type=click.Path(path_type=Path),
              help="Pin the notebook root (env: FLIP_NOTEBOOK) instead of walking up "
                   "from the current directory; refuses if the two disagree.")
@click.option("--actor", "actor", default=None,
              help="Attribution for this command, overriding FLIP_ACTOR "
                   "(e.g. agent:claude, human:jane).")
def main(notebook_pin: Path | None, actor: str | None) -> None:
    """Reporter's notebooks: plain-file research corpora for humans and agents.

    A notebook is one directory and a conformant OKF knowledge bundle: the
    manifest lives in the root index.md frontmatter, notebook.md is the
    working memory, and every source, claim, decision, question, and session
    is one markdown page with YAML frontmatter (references/, claims/,
    decisions/, questions/, sessions/) — ids like A3/C7 resolve via
    `flip open`. Event history is append-only JSONL under log/ and sources/.
    Start with `flip new <slug> --kind <profile>`; run every other command
    from anywhere inside the notebook (flip walks up to find the root, or pin
    it with --notebook/FLIP_NOTEBOOK). `flip show` is the hot view, `flip
    doctor` the lint. Read commands accept --json for machine consumption.
    """
    set_cli_overrides(notebook_pin, actor)


# ---------------------------------------------------------------- cli map


@main.command("cli")
@click.option("--json", "as_json", is_flag=True, help="Emit the command map as JSON.")
@click.pass_context
def cli_map(ctx: click.Context, as_json: bool) -> None:
    """Print a compact map of every command: group path, one-line purpose, key
    flags — generated from the live CLI tree so it can't drift from the code.

    The discoverability shortcut for agents: one read instead of walking
    `--help` per group. Attribution is the global `--actor` flag or
    `FLIP_ACTOR` env — there is no other actor flag.
    """
    root = ctx.find_root().command
    leaves = _leaf_commands(root)
    global_opts = _global_options(root)
    if as_json:
        click.echo(json.dumps(
            {
                "global_options": global_opts,
                "commands": [_leaf_json(path, cmd) for path, cmd in leaves],
            },
            ensure_ascii=False, indent=2,
        ))
        return
    click.echo(f"flip — command map (global options: {', '.join(global_opts)})")
    click.echo("attribution: the --actor flag or FLIP_ACTOR env — there is no other actor flag")
    click.echo("")
    width = max((len(_command_display(p, c)) for p, c in leaves), default=0)
    for path, cmd in leaves:
        disp = _command_display(path, cmd)
        flags = [_long_opt(p) for p in cmd.params if isinstance(p, click.Option)]
        line = f"{disp:<{width}}  {_purpose(cmd)}"
        if flags:
            line += f"  [{' '.join(flags)}]"
        click.echo(line)


# ---------------------------------------------------------------- new


@main.command()
@click.argument("slug")
@click.option("--kind", default="ledger", show_default=True,
              help="Profile id (see `flip profiles`): sets required files, "
                   "notebook.md sections, and the claim-verification bar.")
@click.option("--title", default="", help="Human title; slug is used when omitted.")
@click.option("--visibility", default=None,
              type=click.Choice(["private", "internal", "client-confidential", "public"]),
              help="Override the profile's default visibility policy.")
@click.option("--dest", default=None, type=click.Path(path_type=Path),
              help="Directory to create the notebook in [default: ./<slug>].")
def new(slug: str, kind: str, title: str, visibility: str | None, dest: Path | None) -> None:
    """Create a notebook: index.md manifest + notebook.md stubs, nothing else.

    Use once per piece of research; entity directories (references/, claims/,
    log/, …) appear lazily as commands need them. Then cd in and start logging.
    """
    dest = dest if dest is not None else Path.cwd() / slug
    # Outcome-mode translation: "--kind 'literature review'" lands on
    # lit-review; the manifest always stores the canonical id.
    from . import kinds as kinds_mod_new
    canonical = kinds_mod_new.resolve_kind_id(kind)
    if canonical is not None:
        kind = canonical
    path = scaffold.create_notebook(dest, slug, kind, title=title, visibility=visibility)
    click.echo(f"created {kind} notebook '{slug}' at {path}")
    _autobind_new_notebook(path, slug)
    click.echo(f'next: cd {path} && flip log "started" — see `flip --help` for the toolkit')


def _autobind_new_notebook(path: Path, slug: str) -> None:
    """C2: a notebook created under a workspace root auto-binds into the table
    (slug-derived handle, -2 on collision) and says so — census found rich
    notebooks left unregistered. Binding failures never fail `flip new`."""
    ws_root = find_workspace_root(path.resolve().parent)
    if ws_root is None:
        return
    try:
        ws = workspace_mod.load_workspace(ws_root)
        handle = workspace_mod.default_handle(slug, set(ws.notebooks))
        bound, rel = workspace_mod.ws_add(ws_root, path, handle)
    except SystemExit as e:
        click.echo(f"note: not auto-bound into the workspace ({e})", err=True)
        return
    click.echo(f"bound into workspace as '{bound}' → {rel} (`flip ws list`)")


# ---------------------------------------------------------------- sources


def _warn_if_thin(root: Path, source_id: str, target: str, kind: str | None,
                  via: str | None) -> None:
    """Say at CAPTURE time that a capture is thin — not only at doctor time.

    A JS shell captured as 200 is the failure that reads as a success: same
    sha256, same ledger row, same page at grade "?". `flip doctor` has always
    named it, but doctor runs later, and by then the thin bytes have been cited.
    The moment to look in `sources/raw/` is the moment it lands.
    """
    event = sources.latest_capture_event(root, source_id)
    if not event or sources.capture_fidelity(event) != "thin":
        return
    method = str(event.get("strategy") or "?")
    if str(event.get("status") or "") == "metadata-only":
        head = (f"warning: thin capture — {source_id} holds a registry RECORD, not the "
                f"document ('{method}' reported status metadata-only). It is worth "
                "keeping and it is not the article; do not cite it as though you read it.")
    else:
        head = (f"warning: thin capture — {source_id} holds {event.get('bytes')} bytes via "
                f"'{method}', too little to be the document. A consent wall, a JS shell, or "
                "an error page served as 200 all look exactly like this in custody.")
    above = sources.rungs_above(method)
    lines = [
        head,
        f"  look at {event.get('local_path')} before you cite it (`flip doctor` will keep "
        "naming this until custody holds the document).",
        "  if it is not the document, climb (SPEC §5.1): "
        + (", ".join(above) if above else "nothing above this rung — record it or pass"),
        *sources.lane_inventory(kind or "web", via),
        f"  or record what you could not get: flip add-source {shlex.quote(target)} --record "
        '--note "<rungs tried, what each returned>"',
    ]
    click.echo("\n".join(lines), err=True)


def _warn_if_thin_derivative(source_id: str, row: dict) -> None:
    """Say at EXTRACTION time that a derivative is thin — not only at doctor time.

    The exact reason `_warn_if_thin` exists one layer up, and a sharper case:
    the empty extraction refuses loudly and writes no file, so nobody mistakes
    it for a success. A thin one leaves `sources/text/<id>.txt` on disk with a
    sha256 and a derivation row behind it, looking in every way like the text
    of the document. An image-only scan, a text layer the tool declined to
    trust, and an extractor silently skipping pages are indistinguishable from
    each other and from success, unless someone opens the file.
    """
    if sources.derivative_fidelity(row) != "thin":
        return
    out = row.get("outputs") or [{}]
    words = out[0].get("words", 0)
    pages_n = row.get("pages")
    wpp = row.get("words_per_page")
    lines = [
        f"warning: thin derivative — sources/text/{source_id}.txt holds {words} words "
        f"from a {pages_n}-page document ({wpp} words/page), too little to be its text. "
        "An image-only scan, a text layer the tool declined to trust, or an extractor "
        "silently skipping pages all look exactly like this on disk.",
        f"  read sources/text/{source_id}.txt before you quote it (`flip doctor` will "
        "keep naming this as `thin-derivative`).",
        sources.extraction_guidance(
            source_id, sources.media_family(str(row["inputs"][0]["path"])),
            row.get("via"), row.get("method"),
        ),
    ]
    click.echo("\n".join(lines), err=True)


def _nudge_extract(source_id: str, local: str) -> None:
    """One line, at capture, when the bytes that just landed are a document and
    this machine has a lane that could read them.

    Deliberately a nudge and not an action (SPEC §5.5): `add-source`'s contract
    is custody, extraction is a derivation with its own ledger and its own
    failure modes, and an OCR pass can be a three-minute, gigabyte-and-a-half
    job. Doing that inside a capture would make the cheap verb expensive and
    surprising. Not mentioning it at all is how `sources/text/` stayed empty
    for the whole life of the format.
    """
    family = sources.media_family(local)
    if family not in sources.DOCUMENT_FAMILIES:
        return
    if family not in integrations.extraction_lanes():
        return
    click.echo(
        f"text: this is a {family}; `flip extract {source_id}` derives "
        f"sources/text/{source_id}.txt through your [extractors].{family} lane and "
        "logs how (`flip config show` lists the lanes)."
    )


@main.command("add-source")
@click.argument("target")
@click.option("--kind", default=None,
              help="Source kind (web|social|paper|file|dataset|talk|…); inferred from the "
                   "target when omitted. Non-file kinds run the [fetchers] command "
                   "configured in $FLIP_HOME/config.toml.")
@click.option("--via", default=None,
              help="Named fetcher variant to use, from [fetchers.<kind>] in config.toml "
                   "(e.g. --via browser).")
@click.option("--note", default=None, help="Capture note, recorded in provenance and on the page.")
@click.option("--record", is_flag=True,
              help="Record the source without its bytes (method record-only): the ladder's "
                   "terminus, for a document that is out of reach but has to be citable. "
                   "Requires --note saying what was tried; derives thin fidelity.")
@click.option("--extract", "extract_now", is_flag=True,
              help="Also derive sources/text/<id>.txt through the [extractors] lane for "
                   "the captured file's media family (the same work as `flip extract "
                   "<id>`, inline). Off by default: extraction is a derivation with its "
                   "own ledger and failure modes, and OCR is not a cheap job.")
def add_source(target: str, kind: str | None, via: str | None, note: str | None,
               record: bool, extract_now: bool) -> None:
    """Capture a source: fetch/copy into sources/raw/, hash it, open a page.

    Use the moment you rely on something external — URL, DOI, or local file.
    The references/ page opens at grade "?"; judge it with `flip grade` once
    read — ungraded sources never count toward claim verification.

    When a fetcher comes back empty-handed, that is a finding about the
    document, not a broken config: climb the ladder (SPEC §5.1), or record
    what you could not get with `--record`, or close the search with
    `flip pass`. Improvising a fetch outside flip is the one wrong answer —
    it leaves no custody, no hash, and no row saying what was tried.
    """
    root = require_notebook_root()
    if record and extract_now:
        raise SystemExit(
            "--record holds no bytes of the document, so --extract has nothing to read; "
            "drop one of them — --extract to capture and derive, --record to stop trying"
        )
    if kind == "lookup":
        click.echo(
            "note: --kind lookup is deprecated — use `flip ask`. Cited synthesis is a "
            "lead (grade C), so it now lands in sessions/, not as a source. Move your "
            "[fetchers].lookup command to [research].ask in config.toml.",
            err=True,
        )
        _emit_ask(root, target, via, as_json=False)
        return
    page = sources.add_source(root, target, kind=kind, note=note, via=via, record=record)
    rel = page.path.relative_to(root).as_posix()
    click.echo(f"{page.id} · {page.fm.get('local', '')} · {rel} (grade ?)")
    if record:
        # No "judge it after reading" here: there is nothing to read. A record
        # stays at grade "?" and corroborates nothing, which is the honest
        # state until the document itself is in custody.
        click.echo(
            f"recorded, not captured — the document is not in custody, so {page.id} "
            "corroborates nothing. Say where the chain-walk stopped: flip source "
            f"provenance {page.id} PRIMARY-GATED|PRIMARY-LOST|PRIMARY-EXISTS-PRIVATE "
            '--note "…"'
        )
        return
    _warn_if_thin(root, page.id or "", target, kind, via)
    if extract_now:
        _emit_extraction(root, page.id or "", via=None, force=False, note=note, method=None)
    else:
        _nudge_extract(page.id or "", str(page.fm.get("local") or ""))
    click.echo(f"judge it after reading: flip grade {page.id} "
               f"--independence independent|corroborated|self-reported|derivative "
               f"--basis … [--n … --base-defined|--base-undefined]")


# ---------------------------------------------------------------- extract


def _emit_extraction(root: Path, source_id: str, via: str | None, force: bool,
                     note: str | None, method: str | None) -> None:
    """Run one extraction and report it — shared by `flip extract` and
    `flip add-source --extract` so both say exactly the same things."""
    row = sources.extract_text(
        root, source_id, via=via, force=force, note=note, method=method
    )
    out = (row.get("outputs") or [{}])[0]
    line = f"{source_id} · {out.get('path', '')} · {out.get('words', 0)} words"
    if row.get("pages"):
        line += f" · {row['pages']} pages · {row['words_per_page']} words/page"
    line += f" · {sources.derivative_fidelity(row)} · via {row.get('tool', '?')}"
    if row.get("method"):
        line += f" ({row['method']})"
    click.echo(line)
    if not row.get("method"):
        click.echo(
            f"  no extraction method recorded — a quotation from this file cannot say "
            f"whether it came from the document's own text layer or from an OCR engine "
            f"reading a picture of it. Name it: flip extract {source_id} --method "
            + "|".join(sources.EXTRACTION_METHODS)
        )
    if row.get("supersedes"):
        click.echo(
            f"  supersedes {str(row['supersedes'])[:12]}… — the previous derivative is "
            "gone from disk and still named in derived/_derivations.jsonl"
        )
    _warn_if_thin_derivative(source_id, row)


@main.command()
@click.argument("source_id", metavar="SOURCE_ID")
@click.option("--via", default=None, metavar="LANE",
              help="Named extractor variant from [extractors.<family>] in config.toml "
                   "(e.g. --via ocr). A lane named after an extraction method supplies "
                   "--method for free.")
@click.option("--force", is_flag=True,
              help="Overwrite a sources/text/<id>.txt that flip did not write — i.e. one "
                   "a person edited by hand. Without this, that case is refused.")
@click.option("--note", default=None,
              help="One line recorded in the derivation row (what was odd, why this lane).")
@click.option("--method", default=None, type=click.Choice(sources.EXTRACTION_METHODS),
              help="How the text was recovered (SPEC §5.5). flip never guesses one: "
                   "unset and un-inferable means no method is recorded at all.")
def extract(source_id: str, via: str | None, force: bool, note: str | None,
            method: str | None) -> None:
    """Derive sources/text/<ID>.txt from a captured source's raw bytes.

    Custody holds the bytes; this makes them readable. The command comes from
    the `[extractors]` lane for the raw file's **media family** (`pdf`, `html`,
    `docx`, `audio`) — the input format picks the tool, not the source kind —
    and every run appends one row to `derived/_derivations.jsonl`: inputs and
    outputs with hashes, the tool, the verbatim command, and the extraction
    METHOD.

    Record the method. A quotation recovered by OCR is not the same evidence as
    one lifted from a publisher's own text layer, and the derivation row is the
    only place a later reader can find out which they are holding.

    `sources/raw/` is never touched, and a derivative may be overwritten —
    what makes that safe is the append-only log. A file flip did not write is
    refused without `--force`.
    """
    _emit_extraction(require_notebook_root(), source_id, via, force, note, method)


# ---------------------------------------------------------------- config


@main.group(cls=SuggestGroup)
def config() -> None:
    """Manage the integration config ($FLIP_HOME/config.toml, default ~/.flip)."""


@config.command("init")
@click.option("--force", is_flag=True, help="Overwrite an existing config.toml.")
def config_init(force: bool) -> None:
    """Write a starter config.toml: a bundled web fetcher plus commented examples.

    The `web` lane defaults to `flip-fetch` (shipped with flip, no external tool
    needed), so `flip add-source <url>` works right after this. Social/paper and
    the research/knowledge roles are commented stubs to adapt. Won't overwrite an
    existing config unless --force.
    """
    path, written = integrations.write_starter_config(force=force)
    if not written:
        raise SystemExit(
            f"{path} already exists — edit it, or pass --force to overwrite "
            "(back it up first)"
        )
    click.echo(f"wrote {path}")
    click.echo('next: flip add-source https://example.com  (captures via the bundled flip-fetch)')


@config.command("show")
@click.option("--json", "as_json", is_flag=True, help="Emit the lanes as JSON.")
def config_show(as_json: bool) -> None:
    """List the integration lanes configured on this machine — what flip can run.

    The answer to "what tooling do I actually have here?", which is otherwise
    discoverable only by reading config.toml. Each row is a lane flip will
    route to, and the command behind it is the operator's own — flip wires
    exactly ONE verb of whatever tool fills a role, so when a lane comes back
    empty-handed this is where you find the binary to ask `--help` of.
    """
    path = integrations.config_path()
    lanes = integrations.configured_lanes()
    if as_json:
        click.echo(json.dumps({"config": str(path), "exists": path.is_file(),
                               "lanes": lanes}, ensure_ascii=False, indent=2))
        return
    if not path.is_file():
        raise SystemExit(
            f"{path} does not exist — `flip config init` writes a starter config whose "
            "web lane runs the bundled flip-fetch, so capture works with no external tool"
        )
    if not lanes:
        raise SystemExit(
            f"{path} exists but configures no lanes — add a [fetchers]/[extractors]/"
            "[research]/[knowledge] stanza (`flip config init --force` rewrites the "
            "starter file)"
        )
    click.echo(str(path))
    width = max(len(f"{r['key']}{'/' + r['variant'] if r['variant'] else ''}") for r in lanes)
    role = None
    for row in lanes:
        if row["role"] != role:
            role = row["role"]
            click.echo(f"[{role}]")
        name = row["key"] + (f"/{row['variant']}" if row["variant"] else "")
        needs = f"  (needs: {', '.join(row['needs'])})" if row["needs"] else ""
        via = f"  --via {row['variant']}" if row["variant"] else ""
        click.echo(f"  {name:<{width}}  {row['command']}{needs}{via}")
    click.echo(
        "flip runs these verbatim and reads only the placeholders ({url} {id} {query} "
        "{dest} for capture; {src} {out} {id} for extraction). Each lane is one verb of "
        "whatever fills it — ask the tool itself for the rest of its surface before "
        "working around it."
    )


# ---------------------------------------------------------------- research / knowledge


def _emit_ask(root: Path, query: str, via: str | None, as_json: bool) -> None:
    """Shared renderer for `flip ask` and the deprecated `add-source --kind lookup`."""
    result = query_mod.research_ask(root, query, via=via)
    rel = result.raw_path.relative_to(root).as_posix() if result.raw_path else None
    if as_json:
        click.echo(json.dumps(
            {"query": result.query, "answer": result.answer,
             "citations": result.citations, "raw": rel},
            ensure_ascii=False, indent=2,
        ))
        return
    click.echo(result.answer)
    if result.citations:
        click.echo("\ncitations (leads — capture the ones you'll rely on):")
        for i, c in enumerate(result.citations, 1):
            click.echo(f"{i}. {c.get('title') or c['url']}\n   {c['url']}")
    click.echo(f"\nlead saved to {rel} — this synthesis is grade C, not evidence; "
               "`flip add-source <url>` then `flip grade` the sources you rely on")


@main.command()
@click.argument("query")
@click.option("--via", default=None, help="Named [research] variant to use.")
@click.option("--capture", "capture_n", type=int, default=None, metavar="N",
              help="Capture candidate N (1-based) as a source instead of listing.")
@click.option("--json", "as_json", is_flag=True, help="Emit candidates as JSON.")
def find(query: str, via: str | None, capture_n: int | None, as_json: bool) -> None:
    """Find candidate sources for a question via [research].find — leads, not captures.

    Runs your configured research tool and lists what it surfaces; nothing is
    captured until you pick one (`--capture <n>`, or `flip add-source <url>`).
    """
    root = require_notebook_root()
    result = query_mod.research_find(root, query, via=via)
    if capture_n is not None:
        if not 1 <= capture_n <= len(result.candidates):
            raise SystemExit(
                f"--capture {capture_n} is out of range "
                f"({len(result.candidates)} candidate(s) found)"
            )
        url = result.candidates[capture_n - 1]["url"]
        page = sources.add_source(root, url)
        rel = page.path.relative_to(root).as_posix()
        click.echo(f"captured candidate {capture_n}: {page.id} · {url} · {rel} (grade ?)")
        _warn_if_thin(root, page.id or "", url, None, None)
        return
    if as_json:
        click.echo(json.dumps(
            {"query": result.query, "candidates": result.candidates},
            ensure_ascii=False, indent=2,
        ))
        return
    if not result.candidates:
        click.echo("no candidates returned")
        return
    for i, c in enumerate(result.candidates, 1):
        line = f"{i}. {c.get('title') or c['url']}\n   {c['url']}"
        if c.get("snippet"):
            line += f"\n   {c['snippet']}"
        click.echo(line)
    click.echo('leads only — capture one with `flip find --capture <n> "<query>"` or '
               "`flip add-source <url>`, then grade it")


@main.command()
@click.argument("query")
@click.option("--via", default=None, help="Named [research] variant to use.")
@click.option("--json", "as_json", is_flag=True, help="Emit the answer + citations as JSON.")
def ask(query: str, via: str | None, as_json: bool) -> None:
    """Ask [research].ask for cited synthesis — a grade-C lead, saved to sessions/raw/.

    The synthesis is a lead, not evidence: its raw output is preserved for
    custody and logged, but its citations become sources only when you capture
    and grade them.
    """
    _emit_ask(require_notebook_root(), query, via, as_json)


@main.command()
@click.argument("query")
@click.option("--via", default=None, help="Named [knowledge] variant to use.")
@click.option("--record", is_flag=True,
              help="Also preserve the raw result under sessions/raw/ and log it.")
@click.option("--json", "as_json", is_flag=True, help="Emit hits as JSON.")
def recall(query: str, via: str | None, record: bool, as_json: bool) -> None:
    """Recall what we already hold locally via [knowledge].recall (read-only).

    Answers "do we already know this?" before you go acquire — it reads the
    deployment's local corpus and creates no source.
    """
    root = require_notebook_root()
    result = query_mod.knowledge_recall(root, query, via=via, record=record)
    if as_json:
        click.echo(json.dumps(
            {"query": result.query, "hits": result.hits}, ensure_ascii=False, indent=2
        ))
        return
    if not result.hits:
        click.echo("no local matches")
        return
    for i, h in enumerate(result.hits, 1):
        line = f"{i}. {h.get('title') or h.get('path') or '(untitled)'}"
        if h.get("path") and h.get("title"):
            line += f"\n   {h['path']}"
        if h.get("excerpt"):
            line += f"\n   {h['excerpt']}"
        click.echo(line)


def _explain_grade(source_id: str) -> None:
    """Print why a source derives the letter it does (`flip grade --explain`).

    Reverse-engineering this from the derivation cost one reader an afternoon
    of regrading 134 sources, so it names the moving parts explicitly rather
    than leaving them discoverable only by reading the code.
    """
    root = require_notebook_root()
    row = next((r for r in sources.list_sources(root) if r.get("id") == source_id), None)
    if row is None:
        known = ", ".join(str(r.get("id")) for r in sources.list_sources(root)) or "none yet"
        raise SystemExit(f"unknown source id '{source_id}' in references/ (have: {known})")
    x = sources.explain_grade(row)
    click.echo(f"{source_id} · grade {x['grade']} (derived) — {row.get('title') or ''}".rstrip())
    click.echo(f"  because: {x['reason']}")
    click.echo(f"  to move it: {x['next']}")
    click.echo("  moves the letter:")
    for key in sources.GRADE_INPUTS:
        value = x["inputs"][key]
        gates = " (alone gates B)" if key == "method" else ""
        # booleans render as the flag spelling the user typed, not Python's
        shown = "—" if value is None else (
            str(value).lower() if isinstance(value, bool) else value
        )
        click.echo(f"    {key}: {shown}{gates}")
    doc = ", ".join(
        f"{k}={'—' if x['documentation'][k] is None else x['documentation'][k]}"
        for k in sources.GRADE_DOCUMENTATION
    )
    click.echo(f"  documentation only (never moves the letter): {doc}")


@main.command()
@click.argument("source_id", metavar="SOURCE_ID")
@click.option("--independence", default=None, type=click.Choice(sources.INDEPENDENCE),
              help="The judgment's spine: independent (third party, own collection) · "
                   "corroborated · self-reported (the subject on itself) · "
                   "derivative (republishes another source — a lead, never provenance).")
@click.option("--basis", default=None, type=click.Choice(sources.BASES),
              help="What kind of evidence this is (official-record, platform-data, "
                   "measured, survey, panel, single-operator, synthesis, "
                   "spoken-management-remarks).")
@click.option("--n", default=None, metavar="TEXT",
              help='Sample/coverage AS STATED, a string — e.g. "5 respondents (85-100 of '
                   '110-125)". Strings keep an n from masquerading as the base.')
@click.option("--method", default=None, help="How the evidence was produced, one line.")
@click.option("--vintage", default=None, metavar="YYYY[-MM]",
              help="When the underlying data is from (not when you read it).")
@click.option("--base-defined/--base-undefined", "base_defined", default=None,
              help="Is the measured quantity itself specified? The first question "
                   "to ask of any number. Explicit --base-undefined caps the digest at C.")
@click.option("--freshness", default=None, type=click.Choice(sources.FRESHNESS),
              help="fresh, or dated past the profile threshold.")
@click.option("--notes", default=None, help="Judgment notes (why this reading).")
@click.option("--explain", is_flag=True,
              help="Explain the source's current letter instead of writing: which "
                   "tuple fields moved it, which are documentation, and what a "
                   "higher letter would take. Read-only.")
@click.option("--grade", "legacy_grade", default=None, hidden=True)
def grade(source_id: str, independence: str | None, basis: str | None, n: str | None,
          method: str | None, vintage: str | None, base_defined: bool | None,
          freshness: str | None, notes: str | None, explain: bool,
          legacy_grade: str | None) -> None:
    """Record the support tuple on a source's page (SPEC §5.4).

    Use after actually reading a source; the tuple gates claim verification
    and the letter grade is DERIVED from it, never authored. Only the
    judgment keys change — the rest of the page round-trips.

    `--explain` writes nothing and shows the derivation instead: only
    independence, basis and base_defined move the letter (plus method, which
    alone gates B) — n, vintage and freshness are documentation.
    """
    if explain:
        _explain_grade(source_id)
        return
    if legacy_grade is not None:
        raise SystemExit(
            "grades are derived now, not authored (design D-A): describe the evidence "
            "with --independence/--basis/--n/--method/--vintage/--base-defined and the "
            "letter follows; `flip source list` shows the derived digest"
        )
    if all(v is None for v in (independence, basis, n, method, vintage,
                               base_defined, freshness, notes)):
        raise SystemExit(
            "nothing to record; describe the evidence — at least one of "
            "--independence/--basis/--n/--method/--vintage/--base-defined"
            "/--freshness/--notes"
        )
    page = sources.grade_source(require_notebook_root(), source_id,
                                independence=independence, basis=basis, n=n,
                                method=method, vintage=vintage,
                                base_defined=base_defined,
                                freshness=freshness, notes=notes)
    support = page.fm.get("support") or {}
    bits = [f"{page.id} · grade {page.fm.get('grade', '?')} (derived)",
            str(page.fm.get("independence", "?"))]
    if support.get("basis"):
        bits.append(str(support["basis"]))
    if support.get("base_defined") is not None:
        bits.append(f"base_defined: {str(support['base_defined']).lower()}")
    bits.append(str(page.fm.get("freshness", "")) or "freshness unset")
    click.echo(" · ".join(bits))


@main.group(cls=SuggestGroup)
def source() -> None:
    """Inspect captured sources (references/ pages) without reading files."""


@source.command("list")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the page frontmatter (+ slug, path) as JSON.")
def source_list(as_json: bool) -> None:
    """List sources: id · grade/independence/freshness · title · page path.

    The quick judgment audit: any line still showing grade "?" is captured
    but unjudged — and ungraded sources never count toward verification.

    The letter shown is the DERIVED digest, not the letter stored on the page;
    where the two disagree the stored one is named too. A page whose stored
    letter outlived its support tuple is exactly how a source comes to display
    a confident A while corroborating nothing.
    """
    rows = sources.list_sources(require_notebook_root())
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no sources captured (references/ is absent or empty)")
        return
    for r in rows:
        derived = sources.derive_grade(r)
        stored = str(r.get("grade") or "?")
        letter = derived if derived == stored else f"{derived} (stored {stored})"
        judgment = f"{letter}/{r.get('independence', '?')}/{r.get('freshness', '?')}"
        line = (f"{r.get('id', '?')} · {judgment} · "
                f"{r.get('title') or r.get('local', '')} · {r.get('path', '')}")
        if sources.unmigrated(r):
            line += " · pre-0.8 vocabulary: corroborates nothing until re-judged"
        click.echo(line)


@source.command("pipeline")
@click.argument("source_id", metavar="SOURCE_ID")
@click.argument("pipeline", metavar="live|dormant|orphaned|transferred:<steward>")
@click.option("--evidence", required=True,
              help="One-line receipt for the classification (no enum without evidence).")
def source_pipeline(source_id: str, pipeline: str, evidence: str) -> None:
    """Classify a source's pipeline liveness — did the thing that produced it
    still exist when you last checked? `transferred` and `orphaned` drive
    opposite consumer behavior, so the enum needs its receipt."""
    page = sources.set_pipeline(require_notebook_root(), source_id, pipeline, evidence)
    click.echo(f"{page.id} · pipeline {page.fm['pipeline']} · {page.fm['pipeline_evidence']}")


@source.command("retitle")
@click.argument("source_id", metavar="SOURCE_ID")
@click.argument("title")
def source_retitle(source_id: str, title: str) -> None:
    """Rewrite a source's title (and its `# heading`), quoting it correctly.

    For when a capture lands with a useless name — a fetcher handing back a
    binary payload's first bytes, say. Use this instead of opening the page in
    an editor: flip quotes the YAML, so a title containing a colon can't
    produce frontmatter that breaks every reader of the notebook at once. The
    filename slug is untouched — that's `flip rename`.
    """
    page = sources.retitle_source(require_notebook_root(), source_id, title)
    click.echo(f"{page.id} · {page.fm['title']} · {page.path.name}")


@source.command("recheck")
@click.argument("source_id", metavar="SOURCE_ID")
@click.option("--via", default=None, metavar="FETCHER",
              help="Named fetcher lane to use (defaults to the source's kind).")
def source_recheck(source_id: str, via: str | None) -> None:
    """Re-fetch a source's canonical URL and compare against custody.

    The refresh receipt: `last_checked` says the world was checked, not
    just that the page changed. Custody is never overwritten — unchanged
    clears any drift flag; changed/gone set `drifted:` and doctor warns on
    load-bearing claims resting on the source.
    """
    out = sources.recheck_source(require_notebook_root(), source_id, via=via)
    line = f"{source_id} · {out['result']} · {out['url']}"
    if out["result"] == "changed":
        line += (f"\n  captured {out['baseline'][:12]}… now {out['sha256_now'][:12]}… — "
                 "custody holds the cited bytes; re-add the source if the new version matters")
    elif out["result"] == "gone":
        line += "\n  fetch failed — the coordinate no longer serves; consider pipeline/provenance updates"
    click.echo(line)


@source.command("provenance")
@click.argument("source_id", metavar="SOURCE_ID")
@click.argument("state", type=click.Choice(sources.PROVENANCE_STATES))
@click.option("--note", default=None,
              help="What the chain-walk found (e.g. the closest public derivative).")
def source_provenance(source_id: str, state: str, note: str | None) -> None:
    """Record where the provenance chain-walk behind this source ended.

    PRIMARY-OPEN is legal mid-pass; doctor refuses done/published while a
    load-bearing claim rests on one. PRIMARY-NEVER-PUBLISHED is the normal
    terminal for commercial data — name the closest public derivative in
    --note rather than silently treating it as the primary.
    """
    page = sources.set_provenance_state(require_notebook_root(), source_id, state, note=note)
    click.echo(f"{page.id} · {page.fm['provenance_state']}"
               + (f" · {note}" if note else ""))


# ---------------------------------------------------------------- log ledgers


@main.command()
@click.argument("text")
def log(text: str) -> None:
    """Append one event to the work log (log/log.jsonl); actor auto-detected.

    Use for anything a future reader needs to retrace: fetched X, ran Y,
    hit wall Z. Terse; one event per line. log.md regenerates from it.
    """
    row = ledgers.log_event(require_notebook_root(), text)
    click.echo(f"logged {row['ts']} · {row['actor']}")


@main.command()
@click.option("--question", required=True, help="The fork that needed resolving.")
@click.option("--decision", required=True, help="What was decided.")
@click.option("--why", required=True,
              help="The payload: the what is recoverable from git, the why is not.")
@click.option("--rejected", multiple=True,
              help="Alternative rejected (repeatable).")
def decide(question: str, decision: str, why: str, rejected: tuple[str, ...]) -> None:
    """Record a decision page (decisions/<slug>.md), allocating the next D#.

    Use at every resolved fork so nobody relitigates it: the why is the
    point. Cite the id in prose as [D3]; `flip open D3` finds it again.
    """
    page = ledgers.add_decision(require_notebook_root(), question, decision, why,
                                alternatives_rejected=list(rejected) or None)
    click.echo(f"{page.id} · {page.fm.get('description', '')}")


@main.command("pass")
@click.argument("text")
@click.option("--reason", required=True, help="Why it was rejected — the payload.")
@click.option("--url", default=None, help="Where the rejected thing lives, if anywhere.")
@click.option("--absent-from", "absent_from", default=None,
              type=click.Choice(ledgers.ABSENT_FROM),
              help="Scope an absence assertion: corpus (default claimable) · "
                   "named_surfaces/world (must name --surface(s) checked).")
@click.option("--surface", "surfaces", multiple=True, metavar="SURFACE",
              help="A surface this absence was checked against; repeatable.")
def pass_(text: str, reason: str, url: str | None, absent_from: str | None,
          surfaces: tuple[str, ...]) -> None:
    """Record negative evidence — considered and rejected — in log/passed.jsonl.

    Use when you rule something out, so the next pass (human or agent)
    doesn't rediscover and re-chase it. An absence beyond this corpus must
    say where it looked.
    """
    row = ledgers.add_passed(require_notebook_root(), text, reason, url=url,
                             absent_from=absent_from, surfaces=list(surfaces))
    click.echo(f"passed {row['ts']} · {row['reason']}")


@main.group(cls=SuggestGroup)
def question() -> None:
    """Track questions as pages (questions/<slug>.md, ids Q#).

    Add one whenever something needs an answer before the work can ship;
    `flip show` surfaces the open ones. Answering updates the page in
    place — history stays in git, and the Q# is never reused.
    """


@question.command("add")
@click.argument("text")
@click.option("--resolves-via", "resolves_via", multiple=True, metavar="SURFACE",
              help="A surface that could answer this (repeatable) — an open "
                   "question without a watching surface is a wish, not a plan.")
def question_add(text: str, resolves_via: tuple[str, ...]) -> None:
    """Open a question, allocating the next Q#. Cite it in prose as [Q2]."""
    page = ledgers.add_question(require_notebook_root(), text,
                                resolves_via=list(resolves_via))
    vias = page.fm.get("resolves_via")
    tail = f" · watches: {', '.join(vias)}" if vias else " · unwatched"
    click.echo(f"{page.id} open · {page.fm.get('description', '')}{tail}")


def _require_qid(qid: str) -> str:
    if not re.fullmatch(r"Q\d+", qid):
        raise SystemExit(f"'{qid}' is not a question id (expected Q<number>, e.g. Q2); "
                         "`flip question list` shows them")
    return qid


@question.command("answer")
@click.argument("qid", metavar="ID")
@click.option("--note", default=None,
              help="Where the answer landed; recorded under '## Answer' on the page.")
@click.option("--reopen-when", "reopen_when", multiple=True, metavar="CONDITION",
              help="A written observable condition under which this answer should "
                   "be revisited (repeatable) — resolution says when to stop, "
                   "this says when to un-stop.")
def question_answer(qid: str, note: str | None, reopen_when: tuple[str, ...]) -> None:
    """Mark a question answered: status, answered timestamp, and actor land
    on the page; the ask text stays. Pass --note to record the answer itself,
    --reopen-when to arm the conditions that would reopen it.
    """
    ledgers.answer_question(require_notebook_root(), _require_qid(qid), note=note,
                            reopen_when=list(reopen_when))
    tail = f" · reopens when: {'; '.join(reopen_when)}" if reopen_when else ""
    click.echo(f"{qid} answered{tail}")


@question.command("note")
@click.argument("qid", metavar="ID")
@click.argument("text")
@click.option("--answers", "answers",
              type=click.Choice(ledgers.ANSWER_SCOPES), default=None,
              help="Scope verdict: did this evidence answer the question as "
                   "worded, a narrower question, or an adjacent one? "
                   "Narrower/adjacent keeps the question open with the partial "
                   "answer preserved.")
@click.option("--source", "source_ids", multiple=True, metavar="SOURCE_ID",
              help="Evidence id cited by this note (repeatable; must resolve).")
@click.option("--zero-yield", "zero_yield",
              type=click.Choice(ledgers.ZERO_YIELD_CAUSES), default=None,
              help="This probe came back empty — record WHY: a zero round "
                   "without a cause is indistinguishable from saturation.")
def question_note(qid: str, text: str, answers: str | None,
                  source_ids: tuple[str, ...], zero_yield: str | None) -> None:
    """Land evidence on a question without closing it (append-only).

    Appends a dated '## Evidence' section to the page and logs a
    question-evidence event. The question's status does not change: this is
    how a standing question accretes what the work learns between re-poses,
    including partial (narrower/adjacent) answers and empty probes.
    """
    page = ledgers.note_question(require_notebook_root(), _require_qid(qid), text,
                                 answers=answers, sources=list(source_ids),
                                 zero_yield=zero_yield)
    scope = f" · answers: {answers}" if answers else ""
    zero = f" · zero yield: {zero_yield}" if zero_yield else ""
    click.echo(f"{qid} evidence noted ({page.fm.get('status', 'open')}){scope}{zero}")


@question.command("close")
@click.argument("qid", metavar="ID")
@click.option("--reason", required=True, type=click.Choice(ledgers.CLOSED_REASONS),
              help="How the question ended without an answer.")
@click.option("--note", default=None,
              help="What happened; recorded in the dated '## Closed' section.")
@click.option("--reopen-when", "reopen_when", multiple=True, metavar="CONDITION",
              help="A written observable condition under which to revisit "
                   "(repeatable).")
def question_close(qid: str, reason: str, note: str | None,
                   reopen_when: tuple[str, ...]) -> None:
    """Close a question without an answer — split, yielded to its owner,
    killed by a counter-example, dropped as a dead end, or superseded.

    Answering has its own path (`flip question answer`); this records the
    other honest ends. The page keeps its id and full journey.
    """
    ledgers.close_question(require_notebook_root(), _require_qid(qid), reason,
                           note=note, reopen_when=list(reopen_when))
    click.echo(f"{qid} closed · {reason}")


@question.command("dormant")
@click.argument("qid", metavar="ID")
@click.option("--until", required=True, metavar="YYYY-MM-DD",
              help="Review date: the question resurfaces in `flip show` from "
                   "this date.")
@click.option("--note", default=None,
              help="Why it's parked; recorded in the dated '## Dormant' section.")
def question_dormant(qid: str, until: str, note: str | None) -> None:
    """Park an open question with a review date (dormant is not dead).

    The question leaves the everyday roster but `flip show` surfaces it
    again once the review date passes.
    """
    ledgers.dormant_question(require_notebook_root(), _require_qid(qid), until,
                             note=note)
    click.echo(f"{qid} dormant · review by {until}")


@question.command("reopen")
@click.argument("qid", metavar="ID")
@click.option("--because", required=True,
              help="Which trigger fired, or what changed.")
def question_reopen(qid: str, because: str) -> None:
    """Reopen a settled question (answered, closed, or dormant → open).

    The prior answer and every dated section stay on the page; a dated
    '## Reopened' section records why, and a question-reopen event lands in
    the log.
    """
    ledgers.reopen_question(require_notebook_root(), _require_qid(qid), because)
    click.echo(f"{qid} reopened")


@question.command("repose")
@click.argument("qid", metavar="ID")
@click.argument("text")
@click.option("--sharpened", "sharpened", multiple=True,
              type=click.Choice(ledgers.SHARPENED_AXES),
              help="Which axis this re-pose sharpened (repeatable). Recorded "
                   "on the formulation history entry, never scored.")
@click.option("--note", default=None,
              help="How it sharpened; recorded on the history entry.")
def question_repose(qid: str, text: str, sharpened: tuple[str, ...],
                    note: str | None) -> None:
    """Re-pose a question with a sharper formulation (append-only).

    The new text becomes current; the superseded formulation is preserved in
    the page's `formulations:` history and a dated "Re-posed" body section, and
    a question-repose event lands in the log. The id, slug, and status stay —
    nothing is overwritten, so the full journey survives.
    """
    page = ledgers.repose_question(require_notebook_root(), _require_qid(qid), text,
                                   sharpened=list(sharpened), note=note)
    tail = f" · sharpened: {', '.join(sharpened)}" if sharpened else ""
    click.echo(f"{qid} re-posed · {page.fm.get('description', '')} · "
               f"{len(page.fm.get('formulations') or [])} prior formulation(s) kept{tail}")


@question.command("list")
@click.option("--status", "status",
              type=click.Choice(("open", "answered", "closed", "dormant")),
              default=None, help="Only questions in this status.")
@click.option("--json", "as_json", is_flag=True, help="Emit the rows as JSON.")
def question_list(status: str | None, as_json: bool) -> None:
    """List every question with its current status: id · status · text.

    Open ones also surface in `flip show`; this is the full view (settled
    questions keep their pages — ids are never reused).
    """
    rows = ledgers.list_questions(require_notebook_root(), status=status)
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo(f"no {status} questions" if status
                   else "no questions recorded (questions/ is absent or empty)")
        return
    for r in rows:
        line = f"{r.get('id', '?')} · {r.get('status', 'open')} · {r.get('text', '')}"
        if r.get("status") == "closed" and r.get("closed_reason"):
            line += f" · {r['closed_reason']}"
        if r.get("status") == "dormant" and r.get("review_by"):
            line += f" · review by {r['review_by']}"
        click.echo(line)


# ---------------------------------------------------------------- commissions


@main.group(cls=SuggestGroup)
def commission() -> None:
    """Commission contracts as pages (commissions/<slug>.md, ids K#).

    Bounded follow-up work written as a contract BEFORE dispatch: input
    universe, deliverable, stop condition, does-not-redo boundary. Chains
    that carried these consumed prior outputs without re-discovery; chains
    without them re-searched what they already held. Nothing here dispatches
    anything — the page records the contract and its outcome.
    """


@commission.command("add")
@click.argument("deliverable")
@click.option("--universe", required=True,
              help="The input universe this run works over — what it consumes.")
@click.option("--stop", required=True,
              help="The written condition under which the run stops.")
@click.option("--does-not-redo", "does_not_redo", required=True,
              help="The boundary: what this run must NOT re-search or re-derive.")
@click.option("--for", "for_ref", default=None, metavar="REF",
              help="The question or thread this serves (Q#/TH#; must resolve).")
@click.option("--roi-low", "roi_low", default=None, metavar="TEXT",
              help="Expected lift, LOW bound — quote this as the expectation; "
                   "executed estimates to date held at their low bound.")
@click.option("--roi-high", "roi_high", default=None, metavar="TEXT",
              help="Upside bound (requires --roi-low). Directional, never "
                   "additive across commissions.")
def commission_add(deliverable: str, universe: str, stop: str, does_not_redo: str,
                   for_ref: str | None, roi_low: str | None,
                   roi_high: str | None) -> None:
    """Write a commission contract (status "proposed"), allocating the next K#."""
    page = commissions_mod.add_commission(
        require_notebook_root(), deliverable, universe, stop, does_not_redo,
        for_ref=for_ref, roi_low=roi_low, roi_high=roi_high)
    tail = f" · for {for_ref}" if for_ref else ""
    roi = f" · roi {roi_low}" + (f"–{roi_high}" if roi_high else "") if roi_low else ""
    click.echo(f"{page.id} proposed · {page.fm.get('description', '')}{tail}{roi}")


@commission.command("status")
@click.argument("kid", metavar="ID")
@click.argument("status", type=click.Choice(commissions_mod.STATUSES))
@click.option("--note", default=None, help="What happened; lands in the dated section.")
@click.option("--consumed", default=None,
              help="What prior output the run consumed (returns only) — the "
                   "receipt that keeps a continuation chain auditable.")
def commission_status(kid: str, status: str, note: str | None,
                      consumed: str | None) -> None:
    """Move a commission along proposed → dispatched → returned | declined."""
    page = commissions_mod.set_commission_status(
        require_notebook_root(), kid, status, note=note, consumed=consumed)
    tail = ""
    if status == "returned" and not page.fm.get("consumed"):
        tail = "  (no --consumed receipt — the chain audit will have nothing to check)"
    click.echo(f"{kid} → {status}{tail}")


@commission.command("list")
@click.option("--status", default=None, type=click.Choice(commissions_mod.STATUSES),
              help="Only commissions in this status.")
@click.option("--json", "as_json", is_flag=True, help="Emit the rows as JSON.")
def commission_list(status: str | None, as_json: bool) -> None:
    """List commission contracts: id · status · deliverable · for."""
    rows = commissions_mod.list_commissions(require_notebook_root(), status=status)
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo(f"no {status} commissions" if status
                   else "no commissions recorded (commissions/ is absent or empty)")
        return
    for r in rows:
        line = f"{r['id']} · {r['status']} · {r['deliverable']}"
        if r.get("for"):
            line += f" · for {r['for']}"
        click.echo(line)


# ---------------------------------------------------------------- claims


def _corroboration_label(fm: dict) -> str:
    """What every claim line prints after "corroboration:".

    `n/a (subject)` — never 0 — when the claim cites only what it is ABOUT
    (SPEC §7): there is no count to take, and printing a zero would report
    thin evidence where the honest reading is that the axis does not apply.
    The parenthesis is the reason, which is the half of a missing number that
    is easy to leave out and the only half that gets it looked at.
    """
    if not claims.corroboration_applies(fm):
        return "n/a (subject)"
    return str(fm.get("independent_corroboration", 0))


@main.group(cls=SuggestGroup)
def claim() -> None:
    """Claims as pages (claims/<slug>.md, ids C#): assertions the work relies on.

    Add a claim when the work starts leaning on an assertion; link the
    source ids that back it (its page gets OKF `sources` entries plus
    generated footnote attribution).
    Verification is gated by the notebook profile's corroboration bar —
    `flip doctor` audits load-bearing claims against it.
    """


@claim.command("add")
@click.argument("text")
@click.option("--source", "source_ids", multiple=True, metavar="SOURCE_ID",
              help="A source that WITNESSES what the claim asserts (a references/ page, "
                   "e.g. A3), or a pinned transcript passage (T1§relevance-null); "
                   "repeatable. These are what corroboration counts.")
@click.option("--about", "subject_ids", multiple=True, metavar="SOURCE_ID",
              help="A source the claim is ABOUT rather than evidenced by — the document "
                   "that makes it true or false ('the rebuttal does not mention Persson'). "
                   "Repeatable. It is never counted toward corroboration, because the only "
                   "possible second source is a second READING of the same document; what "
                   "it owes instead is `flip claim test --probe attribution`, which anyone "
                   "can re-run against the same bytes.")
@click.option("--load-bearing", is_flag=True,
              help="The piece falls over if this claim is wrong; doctor audits these.")
@click.option("--notes", default=None, help="Caveats, e.g. 'single vendor study'.")
@click.option("--value", default=None, metavar="TEXT",
              help='The claim\'s number as data, e.g. "4.2" or "~42" or "70-75" — '
                   "renders and exports carry it; prose alone can't.")
@click.option("--unit", default=None, metavar="UNIT",
              help='Unit for --value, e.g. "percent", "USD", "students".')
@click.option("--absent-from", "absent_from",
              type=click.Choice(util.ABSENT_FROM), default=None,
              help="This is an ABSENCE claim — looked and found nothing — and "
                   "this is how far it reaches. Anything beyond 'corpus' must "
                   "name the surfaces searched (--surface): the null's weight "
                   "IS its search coverage.")
@click.option("--surface", "surfaces", multiple=True, metavar="SURFACE",
              help="A surface the absence was checked against (repeatable; "
                   "requires --absent-from).")
@click.option("--derives-from", "derives_from", multiple=True, metavar="CLAIM_ID",
              help="A claim this one RESTS ON (repeatable) — a derivation edge, "
                   "not a citation; doctor walks these so an unsupported "
                   "ancestor surfaces on everything built on it.")
def claim_add(text: str, source_ids: tuple[str, ...], subject_ids: tuple[str, ...],
              load_bearing: bool, notes: str | None, value: str | None,
              unit: str | None, absent_from: str | None,
              surfaces: tuple[str, ...], derives_from: tuple[str, ...]) -> None:
    """Assert a claim (status "asserted"), allocating the next C#."""
    root = require_notebook_root()
    page = claims.add_claim(root, text, list(source_ids),
                            load_bearing=load_bearing, notes=notes,
                            value=value, unit=unit, subjects=list(subject_ids),
                            absent_from=absent_from, surfaces=list(surfaces),
                            derives_from=list(derives_from))
    srcs = ", ".join(claims.source_ids(page.fm)) or "none"
    absence = ""
    if absent_from:
        count = f" ({len(surfaces)} surface{'s' if len(surfaces) != 1 else ''})" \
            if surfaces else ""
        absence = f" · absence: {absent_from}{count}"
    click.echo(f"{page.id} asserted · sources: {srcs} · "
               f"corroboration: {_corroboration_label(page.fm)}{absence}")
    # Dangling cites are legal (§6.1) — doctor counts them — but say so now
    # rather than let a typo'd id ride silently until the next doctor run.
    known = {str(p.fm.get("id")) for p in pages.iter_pages(root, "references")}
    dangling = [s for s in claims.source_ids(page.fm) if s not in known]
    if dangling:
        click.echo(f"note: {', '.join(dangling)} not captured yet — dangling "
                   "citation(s) until `flip add-source` lands them (doctor counts these)")


@claim.command("status")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("status", type=click.Choice(claims.STATUSES))
def claim_status(claim_id: str, status: str) -> None:
    """Move a claim to a new status, recomputing its corroboration count.

    "verified" is refused until the profile's bar is met (independent
    original sources, or a grade-A source where the profile allows it) —
    counting judged sources only.
    """
    page = claims.set_claim_status(require_notebook_root(), claim_id, status)
    click.echo(f"{page.id} → {page.fm.get('status', '?')} · "
               f"corroboration: {_corroboration_label(page.fm)}")
    own = stance_mod.notebook_stance(page.fm)
    if status == "verified" and own and str(own.get("stance")) == "pursuing":
        click.echo(f"note: the notebook's stance on {page.id} is still 'pursuing' — the "
                   "pursuit is discharged now that the claim is verified; record the "
                   f"position it became (`flip claim stance {page.id} holding --because …`)",
                   err=True)


@claim.command("list")
@click.option("--status", default=None, type=click.Choice(claims.STATUSES),
              help="Only claims in this status.")
@click.option("--stance", "stance_value", default=None, type=click.Choice(stance_mod.STANCES),
              help="Only claims the NOTEBOOK takes this stance on (SPEC §7.1).")
@click.option("--exposure", default=None, type=click.Choice(stance_mod.EXPOSURES),
              help="Only claims whose derived exposure is this — e.g. --exposure bent for "
                   "everything no test would have caught an error in, --exposure "
                   "misattributed for claims wrong about what their source says.")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the page frontmatter (+ slug, path, derived exposure) as JSON.")
def claim_list(status: str | None, stance_value: str | None, exposure: str | None,
               as_json: bool) -> None:
    """List claims, optionally filtered by status, stance or exposure.

    The line carries `status` and, where the claim has one, `exposure/stance` —
    three answers to three different questions. `status` says what is known,
    `exposure` says what has been asked of it, `stance` says what the notebook
    does with it. Grouped view: `flip show --claims`.
    """
    rows = claims.list_claims(require_notebook_root(), status=status,
                              stance_value=stance_value, exposure=exposure)
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        filters = [f"{k} '{v}'" for k, v in
                   (("status", status), ("stance", stance_value), ("exposure", exposure))
                   if v]
        click.echo("no claims" + (f" with {' and '.join(filters)}" if filters else " recorded"))
        return
    for r in rows:
        flag = " [load-bearing]" if r.get("load_bearing") else ""
        # source_ids, not the raw entries: `sources` holds OKF v0.2 maps, and
        # str()ing one prints a YAML dict into a list view nobody can scan.
        srcs = ", ".join(claims.source_ids(r)) or "none"
        line = (f"{r.get('id', '?')} · {r.get('status', '?')}{flag} · "
                f"{r.get('description', '')} · sources: {srcs}")
        if r.get("stances") or r.get("tests") or r.get("rivals"):
            line += f" · {r['exposure']}"
            if r.get("stance"):
                line += f"/{r['stance']}"
        click.echo(line)


@claim.group("source", cls=SuggestGroup)
def claim_source() -> None:
    """Link or unlink backing sources on a claim after the fact.

    Both regenerate the claim's footnote attribution and recompute its
    independent_corroboration — the post-hoc fix for a claim asserted before
    its sources were captured. Ungraded sources link but never count toward
    the verification bar, and a source cited with `--about` is never counted
    at all: the claim is about that document, so it cannot also be an
    independent witness to what the document says.
    """


@claim_source.command("add")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("source_ids", nargs=-1, metavar="SOURCE_ID...")
@click.option("--about", "subject_ids", multiple=True, metavar="SOURCE_ID",
              help="Cite this source as what the claim is ABOUT rather than as evidence "
                   "for it — the document that makes the claim true or false. Repeatable, "
                   "and it re-roles a source the claim already cites. A subject never "
                   "counts toward corroboration (no second witness to a document can "
                   "exist); the audit it owes instead is `flip claim test --probe "
                   "attribution`.")
def claim_source_add(claim_id: str, source_ids: tuple[str, ...],
                     subject_ids: tuple[str, ...]) -> None:
    """Link one or more sources to a claim. Unknown ids are refused.

    Bare ids are cited as evidence; `--about <id>` cites the source the claim
    is about. The distinction is what the citation is FOR, and it decides
    which audit the claim owes: a second independent witness, or a rereading
    of the one document that settles it.
    """
    page, added, rerolled, warnings = claims.add_claim_sources(
        require_notebook_root(), claim_id, list(source_ids), subjects=list(subject_ids)
    )
    did = []
    if added:
        did.append(f"linked {', '.join(added)}")
    if rerolled:
        did.append(f"re-roled {', '.join(rerolled)}")
    click.echo(f"{page.id} · {' · '.join(did)} · sources: "
               f"{', '.join(claims.source_ids(page.fm)) or 'none'} · "
               f"corroboration: {_corroboration_label(page.fm)}")
    for sid, reason in warnings:
        if reason == "unmigrated":
            click.echo(f"warning: {sid} carries pre-0.8 independence vocabulary — it "
                       "records custody, not epistemics, so flip can't read it as a "
                       "judgment and it counts toward nothing; re-read the source and "
                       f"re-judge it (`flip grade {sid} --explain` for what moves the "
                       "letter)", err=True)
        else:
            click.echo(f"warning: {sid} is still graded '?' — ungraded sources never count "
                       f"toward the bar; judge it with `flip grade {sid}`", err=True)


@claim_source.command("rm")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("source_id", metavar="SOURCE_ID")
def claim_source_rm(claim_id: str, source_id: str) -> None:
    """Unlink a source id from a claim. Refuses if the claim doesn't cite it."""
    page = claims.remove_claim_source(require_notebook_root(), claim_id, source_id)
    click.echo(f"{page.id} · unlinked {source_id} · sources: "
               f"{', '.join(claims.source_ids(page.fm)) or 'none'} · "
               f"corroboration: {_corroboration_label(page.fm)}")


@claim.command("verify")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.option("--method", required=True, type=click.Choice(claims.VERIFICATION_METHODS),
              help="adversarial (skeptic pass) · independent-sources (records "
                   "corroboration reasoning) · recomputation (re-derive the result).")
@click.option("--against", multiple=True, metavar="REF",
              help="What did the verifying — repeatable, and not only source ids: a "
                   "session id, script path, or derivation record all belong here "
                   "(e.g. --against A7, --against sessions/2026-07-30-recompute.md). "
                   "Required in practice for --method recomputation: doctor warns on a "
                   "recomputation nobody can locate.")
@click.option("--note", default=None, help="What the check found (recorded on the page).")
def claim_verify(claim_id: str, method: str, against: tuple[str, ...],
                 note: str | None) -> None:
    """Record a verification on a claim (append-only frontmatter record).

    An adversarial or recomputation record lets `flip claim status <C#>
    verified` pass even below the corroboration bar; independent-sources only
    documents the corroboration reasoning and never satisfies the gate alone.
    """
    page = claims.verify_claim(require_notebook_root(), claim_id, method,
                               against=list(against), note=note)
    click.echo(f"{page.id} · verified via {method} · "
               f"{len(page.fm.get('verified') or [])} verification(s) on record")
    if method == "independent-sources":
        click.echo("note: independent-sources records the reasoning but does not satisfy "
                   "the verified gate alone — the recomputed source count does", err=True)


@claim.group("derives", cls=SuggestGroup)
def claim_derives() -> None:
    """Derivation edges between claims: what a claim RESTS ON.

    Not a citation — a claim built on other claims declares it, and doctor
    walks the chain so an unsupported ancestor surfaces on every
    load-bearing claim leaning on it (`inherited-unsupported`).
    """


@claim_derives.command("add")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("ancestor_ids", metavar="ANCESTOR_ID", nargs=-1, required=True)
def claim_derives_add(claim_id: str, ancestor_ids: tuple[str, ...]) -> None:
    """Declare CLAIM_ID rests on one or more other claims."""
    page, added = claims.add_claim_derivation(require_notebook_root(), claim_id,
                                              list(ancestor_ids))
    click.echo(f"{claim_id} derives from {', '.join(claims.derivation_ids(page.fm))} "
               f"(+{len(added)})")


@claim_derives.command("rm")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("ancestor_id", metavar="ANCESTOR_ID")
def claim_derives_rm(claim_id: str, ancestor_id: str) -> None:
    """Drop a derivation edge from CLAIM_ID."""
    page = claims.remove_claim_derivation(require_notebook_root(), claim_id, ancestor_id)
    rests = ", ".join(claims.derivation_ids(page.fm)) or "nothing"
    click.echo(f"{claim_id} derives from {rests}")


@claim.command("stance")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("stance_value", metavar="STANCE", type=click.Choice(stance_mod.STANCES))
@click.option("--because", required=True,
              help="Why this position, in one or two lines. Always required — a stance "
                   "word on its own is an enum without evidence.")
@click.option("--falsifier", default=None,
              help="The observation this position predicts that would be LEAST likely to "
                   "come out that way if the position were wrong (Peirce, CP 2.89). "
                   "REQUIRED for pursuing and rejecting: a hypothesis is admissible only "
                   "insofar as it is capable of experimental verification (CP 5.197).")
@click.option("--holder", default=stance_mod.NOTEBOOK_HOLDER, show_default=True,
              help="Who takes this position. Defaults to the reserved holder 'notebook'; "
                   "name someone else to record a belief the notebook does not share.")
@click.option("--source", "source_ids", multiple=True, metavar="REF",
              help="Evidence that the holder holds it — repeatable. Only meaningful for a "
                   "foreign holder; doctor warns on one with nothing cited.")
def claim_stance(claim_id: str, stance_value: str, because: str, falsifier: str | None,
                 holder: str, source_ids: tuple[str, ...]) -> None:
    """Record what is DONE with a claim, as opposed to what is known about it.

    The attitude axis (SPEC §7.1), orthogonal to `status` and to `exposure` on
    purpose:

    \b
      pursuing    worked from on explanatory promise, ahead of the evidence
      holding     the notebook's position; it would defend this
      abstaining  a position considered and deliberately not taken
      rejecting   taken to be false, and kept because someone holds it

    Append-only: a new stance is added, never edited over, so the record of
    what the notebook used to think survives. `--holder` is how a widely-held
    belief the notebook rejects gets kept as data — the notebook's own
    `rejecting` and someone else's `holding` sit on the same page without
    either overwriting the other.
    """
    page, unsourced = claims.set_stance(
        require_notebook_root(), claim_id, stance_value, because,
        holder=holder, falsifier=falsifier, sources=list(source_ids),
    )
    exposure = stance_mod.derive_exposure(page.fm)
    click.echo(f"{page.id} · {stance_value} (held by {holder}) · exposure: {exposure} · "
               f"{len(stance_mod.stance_records(page.fm))} stance(s) on record")
    bent = stance_mod.bent_reason(page.fm)
    if bent and holder == stance_mod.NOTEBOOK_HOLDER and stance_value in ("pursuing", "holding"):
        click.echo(f"note: {page.id} reads 'bent' — {bent}. Taking a position does not "
                   "change what the record is worth: the falsifier you just wrote is the "
                   f"promise, `flip claim test {page.id} …` is the receipt", err=True)
    for name in unsourced:
        click.echo(f"warning: nothing cited for '{name}' holding this — that someone "
                   "believes something is an assertion about them, and it needs evidence "
                   "like any other. Cite it with --source, or assert the prevalence as "
                   "its own claim and cite that", err=True)


@claim.command("test")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.option("--probe", required=True, type=click.Choice(stance_mod.TEST_PROBES),
              help="Which class of error you went looking for: attribution (does the "
                   "source contain this?) · substance (is it true of the world?) · "
                   "scope (does it hold outside the conditions its evidence covers?). "
                   "Three, because each one has a different repair.")
@click.option("--error", required=True,
              help="The specific way of being wrong this test looked for. Required, and a "
                   "severity input: a severe test is one the claim would probably have "
                   "failed 'if false in a specified manner' (Mayo, SIST p.65).")
@click.option("--result", required=True, type=click.Choice(stance_mod.TEST_RESULTS),
              help="survived · failed · inconclusive · untestable (the claim as posed "
                   "admits no test).")
@click.option("--would-detect", "would_detect", default=None,
              help="How the error would have shown up had it been there — the 'if it is "
                   "present' half of the capability condition (SIST p.16).")
@click.option("--if-absent", "if_absent", default=None,
              help="What this probe would have shown INSTEAD, had the error not been "
                   "there — the 'and only if' half (SIST p.16). A probe that fires either "
                   "way discriminates nothing, however carefully it was run.")
@click.option("--against", multiple=True, metavar="REF",
              help="What did the testing — repeatable, and not only source ids: a session "
                   "id, a script path, or a dataset all belong here.")
@click.option("--note", default=None, help="What the test found, in the tester's words.")
def claim_test(claim_id: str, probe: str, error: str, result: str,
               would_detect: str | None, if_absent: str | None,
               against: tuple[str, ...], note: str | None) -> None:
    """Record a test run against a claim — including one that found the error.

    The evidential axis (SPEC §7.1). `flip claim verify` records that
    something was CONFIRMED and is OKF v0.2's key; a test that found the error
    is not a confirmation, so it lives in flip's own append-only `tests:` list
    and can say so plainly.

    What the record buys is the difference between "the paper does not say
    this" and "the world is not like this" and "nobody has looked" — three
    situations flip used to render as one non-verified state, with three
    different next actions. `flip claim exposure <C#>` shows what the record
    adds up to and why.

    A test is SEVERE when four things are on the record: the error it looked
    for, how that error would have shown up, what it would have shown had the
    error been absent, and what did the testing. Anything less is bent — bad
    evidence, no test — and that is one verdict, not a rung on a ladder.
    """
    page = claims.record_test(require_notebook_root(), claim_id, probe, error, result,
                              would_detect=would_detect, if_absent=if_absent,
                              against=list(against), note=note)
    record = stance_mod.test_records(page.fm)[-1]
    severity = stance_mod.test_severity(record)
    click.echo(f"{page.id} · {probe} test {result} ({severity}) · exposure: "
               f"{stance_mod.derive_exposure(page.fm)}")
    gaps = stance_mod.severity_gaps(record)
    if severity == "bent" and result in ("survived", "failed") and gaps:
        flags = ", ".join("--" + g.replace("_", "-") for g in gaps)
        click.echo(f"note: this test is bent — {flags} not recorded, so flip cannot tell "
                   "whether it would have caught the error, or whether it would have said "
                   "anything different if there had been no error to catch. A test that "
                   "could have missed it, or that fires either way, neither confirms nor "
                   "refutes", err=True)


@claim.command("exposure")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.option("--json", "as_json", is_flag=True, help="Emit the derivation as JSON.")
def claim_exposure(claim_id: str, as_json: bool) -> None:
    """Explain what a claim's test record adds up to, and why. Read-only.

    The twin of `flip grade --explain`, and for the same reason: exposure is
    DERIVED from the `tests:` list and never stored, so a derivation nobody
    can see is a verdict wearing a computation's clothes. Prints each test
    with its severity and why it landed there, the rule that fired, and the
    shortest honest path to a stronger exposure.
    """
    root = require_notebook_root()
    page = pages.find_by_id(root, claim_id)
    if page is None or str(page.fm.get("type", "")) != "Claim":
        known = ", ".join(str(r.get("id")) for r in claims.list_claims(root)) or "none yet"
        raise SystemExit(
            f"no claim '{claim_id}' in claims/ (known: {known}); add it with `flip claim add`"
        )
    x = stance_mod.explain_exposure(page.fm)
    if as_json:
        click.echo(json.dumps(x, ensure_ascii=False, indent=2))
        return
    click.echo(f"{claim_id} · exposure {x['exposure']} (derived, never stored) · "
               f"status {page.fm.get('status', '?')}")
    click.echo(f"  because: {x['reason']}")
    if x["tests"]:
        click.echo("  tests on record:")
        for t in x["tests"]:
            head = f"    {t['probe']} · {t['result']} · {t['severity']}"
            click.echo(f"{head} — {t['why']}")
            if t["error"]:
                click.echo(f"      looked for: {t['error']}")
            if t["against"]:
                click.echo(f"      against: {', '.join(t['against'])}")
    else:
        click.echo("  tests on record: none")
    own = x["stance"]
    if own:
        line = f"  notebook stance: {own.get('stance')} — {own.get('because', '')}"
        click.echo(line)
        if own.get("falsifier"):
            click.echo(f"    would be moved by: {own['falsifier']}")
    else:
        click.echo("  notebook stance: none recorded (nobody has decided, which is not "
                   "the same as abstaining)")
    for other in x["holders"]:
        cites = ", ".join(str(s) for s in pages.as_list(other.get("sources"))) or "nothing cited"
        click.echo(f"  held by {other.get('holder')}: {other.get('stance')} — "
                   f"{other.get('because', '')} [{cites}]")
    if x["rivals"]:
        click.echo("  rivals (claims answering the same question):")
        for rival in x["rivals"]:
            rid = str(rival.get("claim"))
            other_page = pages.find_by_id(root, rid)
            other_exposure = (
                stance_mod.derive_exposure(other_page.fm) if other_page is not None
                else "no such claim"
            )
            click.echo(f"    {rid} · {other_exposure} — {rival.get('because', '')}")
    elif x["exposure"] in stance_mod.REFUTING_EXPOSURES:
        click.echo("  rivals: none declared — nothing on record could have won this")
    if x["superseded_by"]:
        click.echo(f"  superseded by: {x['superseded_by']}")
    click.echo(f"  next: {x['next']}")


@claim.command("rival")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("other_id", metavar="RIVAL_ID")
@click.option("--because", required=True,
              help="The question both claims answer, in your own words. Required: flip "
                   "cannot infer it, and two claims can share every source and answer "
                   "different questions.")
def claim_rival(claim_id: str, other_id: str, because: str) -> None:
    """Declare two claims rivals — they answer the same question.

    The unit of comparison (SPEC §7.1). Lakatos, p.69: "a degenerating
    problemshift is no more a sufficient reason to eliminate a research
    programme than some old-fashioned 'refutation' or a Kuhnian 'crisis'…
    such an objective reason is provided by a rival research programme which
    explains the previous success of its rival and supersedes it by a further
    display of heuristic power." Letting go is comparative: you let go when
    something better exists, not when a claim has been embarrassing for long
    enough. Nothing in flip fires on a timer.

    Written to both pages, because a comparison only one side can see is not
    a comparison. What flip does with it: `flip claim exposure` shows how the
    rivals compare on the evidence, doctor names a pursued claim that is
    losing to one, and doctor names a load-bearing pursued claim that has
    never declared any.
    """
    page, other = claims.declare_rivals(require_notebook_root(), claim_id, other_id, because)
    left = stance_mod.derive_exposure(page.fm)
    right = stance_mod.derive_exposure(other.fm)
    click.echo(f"{page.id} ({left}) ⇄ {other.id} ({right}) · rivals on: {because}")
    if left == right == "bent":
        click.echo("note: neither claim has a severe test on record, so there is nothing "
                   "to compare them on yet. A rivalry between two untested positions is a "
                   "preference; test one of them and it becomes a result", err=True)


@claim.command("supersede")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.option("--by", "successor_id", required=True, metavar="CLAIM_ID",
              help="The claim that replaces this one.")
@click.option("--because", required=True,
              help="What both claims answer, and why the successor wins. This sentence is "
                   "the content of the move; the status change is bookkeeping.")
def claim_supersede(claim_id: str, successor_id: str, because: str) -> None:
    """Concede a claim to the one that replaced it.

    The only route to `status: superseded`, and the reason is Lakatos's
    elimination criterion (p.69): eliminating a position is comparative, so a
    bare status change — "this one stopped working out" — is the move he says
    is not available. Writes `superseded_by`, registers the two claims as
    rivals, and sets the status, in one go.

    The claim keeps its page and its id forever, as every let-go claim does.
    What changes is that the next reader arrives at a forwarding address
    instead of a tombstone.
    """
    page, note = claims.supersede_claim(
        require_notebook_root(), claim_id, successor_id, because)
    click.echo(f"{page.id} → superseded by {successor_id} · {because}")
    if note:
        click.echo(note, err=True)


# ---------------------------------------------------------------- sessions


@main.group(cls=SuggestGroup)
def session() -> None:
    """Session pages (sessions/<UTC stamp>-<slug>.md): one per working episode.

    Start one before an LLM run or research sweep; end it with a summary so
    the reasoning chain survives as evidence (SPEC §8).
    """


@session.command("start")
@click.argument("slug")
@click.option("--model", default=None, help="Model driving the episode, e.g. 'claude-fable-5'.")
@click.option("--tools", multiple=True, help="Tool available in the episode (repeatable).")
def session_start(slug: str, model: str | None, tools: tuple[str, ...]) -> None:
    """Open sessions/<UTC stamp>-<slug>.md with frontmatter and stubs.

    Prints the file path — fill in Goal/Prompt/Key outputs as you work.
    """
    path = sessions.start_session(require_notebook_root(), slug, model=model,
                                  tools=list(tools) or None)
    click.echo(str(path))


@session.command("end")
@click.argument("slug_or_path", metavar="SLUG_OR_PATH")
@click.option("--summary", required=True,
              help="What the session accomplished — the cold-pickup line.")
def session_end(slug_or_path: str, summary: str) -> None:
    """Close a session: `ended` lands in its frontmatter, the summary in its body.

    Pass the path printed by `session start`, or just the slug (newest
    matching session wins).
    """
    path = sessions.end_session(require_notebook_root(), slug_or_path, summary)
    click.echo(f"ended {path}")


@session.command("transcript")
@click.argument("slug_or_path", metavar="SLUG_OR_PATH")
@click.option("--file", "file", required=True, type=click.Path(exists=True, dir_okay=False),
              help="The conversation, written to a markdown or text file.")
@click.option("--title", default=None, help="Human title for the transcript page.")
@click.option("--participant", "participants", multiple=True,
              help="Who was in the conversation (repeatable), e.g. 'human:marc'.")
@click.option("--model", default=None, help="Model on the other side, e.g. 'claude-opus-5'.")
@click.option("--note", default=None, help="Capture note, recorded in provenance and on the page.")
def session_transcript(slug_or_path: str, file: str, title: str | None,
                       participants: tuple[str, ...], model: str | None,
                       note: str | None) -> None:
    """Keep this session's conversation verbatim, as a citable source.

    Claims and graded sources are the residue of thinking, not the thinking:
    a transcript is where the position actually got built. Captured under
    normal custody (immutable bytes, sha256, provenance) with a T# id, so
    `flip transcript excerpt` can pin the exchange a claim rests on.
    """
    root = require_notebook_root()
    page = transcripts_mod.capture_transcript(
        root, file, title=title, participants=list(participants) or None,
        model=model, note=note,
    )
    source_id, local = page.fm["id"], str(page.fm.get("local") or "")
    session_path = sessions.attach_transcript(
        root, slug_or_path, source_id, local, page.path.stem
    )
    click.echo(f"{local}  ({page.fm.get('lines')} lines)")
    click.echo(f"captured as {source_id}  {page.path}")
    click.echo(f"linked from {session_path}")
    click.echo(f"pin a passage: flip transcript excerpt {source_id} --lines A-B --label <label>")


# ---------------------------------------------------------------- transcripts


@main.group(cls=SuggestGroup)
def transcript() -> None:
    """Transcripts: conversations kept verbatim and cited by the passage.

    A notebook that keeps only claims and sources keeps the conclusions and
    loses the reasoning. Capture with `flip session transcript`, then pin the
    exchanges that matter — a claim citing `T1§relevance-null` carries the
    words it came from (SPEC §8).
    """


def _parse_lines(spec: str) -> tuple[int, int]:
    m = re.match(r"^\s*(\d+)\s*[-–:]\s*(\d+)\s*$", spec or "")
    if not m:
        raise SystemExit(f"invalid --lines {spec!r}: expected a range like 88-104")
    return int(m.group(1)), int(m.group(2))


@transcript.command("excerpt")
@click.argument("source_id", metavar="ID")
@click.option("--lines", "lines", required=True, metavar="A-B",
              help="Line range in the captured transcript, 1-indexed, inclusive.")
@click.option("--label", required=True,
              help="Slug naming the passage; becomes the ref suffix and page anchor.")
@click.option("--note", default=None, help="One line on why this passage is worth pinning.")
def transcript_excerpt(source_id: str, lines: str, label: str, note: str | None) -> None:
    """Pin lines A-B of a transcript under LABEL, and print the ref to cite.

    The quote is read out of the immutable capture and hashed — never taken
    from you — so a pinned passage is always the words it says it is.
    """
    start, end = _parse_lines(lines)
    record = transcripts_mod.add_excerpt(
        require_notebook_root(), source_id, label, start, end, note=note
    )
    ref = format_excerpt_ref(source_id, label)
    click.echo(ref)
    click.echo(f"  lines {start}-{end}, {record['words']} words, sha256 {record['sha256'][:12]}")
    click.echo(f"  cite it: flip claim add \"…\" --source {ref}")
    # The transcript case is where citation roles bite hardest: a claim about
    # what was SAID has one witness by construction and can never have two, so
    # the operator is told here — at the moment they get the ref — rather than
    # discovering it from a corroboration count they cannot move (SPEC §7).
    click.echo(f"  …or --about {ref} if the claim is about what was SAID here — a "
               "conversation is the only witness to itself, so that citation is never "
               "counted and owes `flip claim test --probe attribution` instead")


@transcript.command("list")
@click.argument("source_id", metavar="ID")
@click.option("--json", "as_json", is_flag=True, help="Emit the pinned passages as JSON.")
def transcript_list(source_id: str, as_json: bool) -> None:
    """Every passage pinned on a transcript, in the order they were pinned."""
    records = transcripts_mod.excerpts(require_notebook_root(), source_id)
    if as_json:
        click.echo(json.dumps(records, ensure_ascii=False, indent=2))
        return
    if not records:
        click.echo(f"{source_id} pins no passages yet — see `flip transcript excerpt --help`")
        return
    for record in records:
        span = record.get("lines") or []
        where = f"{span[0]}-{span[1]}" if len(span) == 2 else "?"
        line = f"{format_excerpt_ref(source_id, str(record.get('label')))}  lines {where}"
        if record.get("note"):
            line += f"  — {record['note']}"
        click.echo(line)


@transcript.command("unpin")
@click.argument("source_id", metavar="ID")
@click.argument("label")
def transcript_unpin(source_id: str, label: str) -> None:
    """Drop a pinned passage. Refuses while a claim still cites it."""
    transcripts_mod.remove_excerpt(require_notebook_root(), source_id, label)
    click.echo(f"unpinned {format_excerpt_ref(source_id, label)}")


# ---------------------------------------------------------------- views / navigation


@main.command()
@click.option("--claims", "claims_flag", is_flag=True,
              help="All claims grouped by status.")
@click.option("--stale", "stale_flag", is_flag=True,
              help="What went cold: dated sources, open questions, stuck claims.")
@click.option("--forecasts", "forecasts_flag", is_flag=True,
              help="Open forecasts (due first) and the calibration record.")
@click.option("--json", "as_json", is_flag=True, help="Emit the view as JSON.")
def show(claims_flag: bool, stale_flag: bool, forecasts_flag: bool, as_json: bool) -> None:
    """Show a computed view of the notebook; default is the hot view.

    The hot view is the resume-here screen: open questions, claims needing
    work, recent log, latest session. Views are computed from the pages and
    ledgers, never stored (SPEC §10).
    """
    if sum([claims_flag, stale_flag, forecasts_flag]) > 1:
        raise SystemExit("pass at most one of --claims/--stale/--forecasts")
    root = require_notebook_root()
    fn = (views.claims_view if claims_flag
          else views.stale_view if stale_flag
          else views.forecasts_view if forecasts_flag
          else views.hot_view)
    out = fn(root, as_data=as_json)
    click.echo(json.dumps(out, ensure_ascii=False, indent=2) if as_json else out)


@main.command("open")
@click.argument("ref", metavar="REF")
def open_(ref: str) -> None:
    """Resolve a reference (A3, C7 … or recipes:A3) to its entity page path.

    Ids are immutable frontmatter; filenames are human slugs (SPEC §9), so
    this is how a bare [A3] cite becomes a file. Qualified refs like
    recipes:A3 resolve through the enclosing workspace table (SPEC §18).
    Prints the absolute path — compose it: `$EDITOR $(flip open A3)`.
    """
    click.echo(str(resolve_mod.resolve_ref(ref).path))


@main.command("resolve")
@click.argument("ref", metavar="REF")
@click.option("--json", "as_json", is_flag=True,
              help="Emit ref, id, handle, path, notebook root/slug, uid, title as JSON.")
def resolve_cmd(ref: str, as_json: bool) -> None:
    """Resolve a reference to its entity page, with provenance.

    Bare ids (A3) resolve within the containing notebook; qualified refs
    (recipes:A3) resolve through the nearest workspace table; unknown handles
    and ids are errors, never guesses (SPEC §9). This is the primitive
    plugins and agents shell out to — plain output is just the path.
    """
    r = resolve_mod.resolve_ref(ref)
    if as_json:
        click.echo(json.dumps(
            {"ref": r.ref, "id": r.entity_id, "handle": r.handle,
             "path": str(r.path), "notebook_root": str(r.notebook_root),
             "notebook_slug": r.notebook_slug, "uid": r.uid, "title": r.title},
            ensure_ascii=False, indent=2,
        ))
        return
    click.echo(str(r.path))


@main.command()
@click.argument("entity_id", metavar="ID")
@click.argument("new_slug", metavar="NEW_SLUG")
def rename(entity_id: str, new_slug: str) -> None:
    """Rename an entity page to NEW_SLUG, rewriting links notebook-wide.

    The only sanctioned rename (SPEC §9): the id and aliases never change,
    so [A3]-style cites keep resolving; every markdown link and supports
    path pointing at the old filename is rewritten, and the generated
    listings refresh.
    """
    root = require_notebook_root()
    old_path, new_path, changed = rename_mod.rename_entity(root, entity_id, new_slug)
    click.echo(f"{entity_id}: {old_path.relative_to(root).as_posix()} → "
               f"{new_path.relative_to(root).as_posix()}")
    if changed:
        click.echo(f"rewrote links in {changed} file(s)")


def _collapse_findings(findings: list, show: int = 3) -> list[str]:
    """Render findings, collapsing any code that repeats past `show`.

    A single cause can produce hundreds of identical-shaped lines — 134 sources
    on pre-0.8 vocabulary once printed 268 of them — and a wall of repeats reads
    as "deeply unsound" when it is one fix. The examples still print, the tail
    is counted, and `--json` keeps every finding for anything scripted.
    """
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.code] = counts.get(f.code, 0) + 1
    lines, shown = [], {}
    for f in findings:
        seen = shown.get(f.code, 0)
        if counts[f.code] > show and seen >= show:
            shown[f.code] = seen + 1
            continue
        shown[f.code] = seen + 1
        lines.append(f"{f.level} {f.code} {f.path} — {f.message}")
        if counts[f.code] > show and seen + 1 == show:
            lines.append(
                f"{f.level} {f.code} … and {counts[f.code] - show} more with the same "
                "code (--json for all)"
            )
    return lines


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Emit findings as JSON.")
@click.option("--workspace", "workspace_flag", is_flag=True,
              help="Lint the enclosing workspace instead: the handle table, "
                   "notebook coverage, uid lineage, and cross-notebook ambiguity.")
@click.option("--fix", is_flag=True,
              help="Workspace mode only: bind unregistered notebooks, backfill "
                   "uids, and regenerate qualified aliases.")
def doctor(as_json: bool, workspace_flag: bool, fix: bool) -> None:
    """Lint the notebook against the spec and its profile; exit 1 on errors.

    Checks manifest sanity, OKF conformance (frontmatter + type on every
    page), id/alias integrity, dangling citations, profile minimums (WARN
    while status is active/dormant, ERROR once done/published/archived),
    orphan custody, stale freshness, and claims below the verification bar.
    Run before a handoff or publish; fix ERRORs, weigh WARNs.

    With --workspace (or from a workspace root outside any notebook), lints
    the shared space instead (SPEC §18): duplicate uids, unbound notebooks,
    ids and slugs ambiguous across notebooks.
    """
    nb_root = find_notebook_root_pinned()
    if workspace_flag or (nb_root is None and find_workspace_root() is not None):
        ws_root = workspace_mod.require_workspace_root()
        findings = doctor_mod.run_workspace_doctor(ws_root, fix=fix)
    else:
        if fix:
            raise SystemExit("--fix applies to workspace mode only (flip 0.9); "
                             "run `flip doctor --workspace --fix`")
        findings = doctor_mod.run_doctor(require_notebook_root())
    if as_json:
        # Each finding carries `expected: true|false` — the same real-vs-
        # appears-with-use distinction the text output segregates (E3).
        click.echo(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    elif not findings:
        click.echo("ok: no findings")
    else:
        real = [f for f in findings if not f.expected]
        expected = [f for f in findings if f.expected]
        for line in _collapse_findings(real):
            click.echo(line)
        if not real:
            click.echo("ok: no findings yet")
        if expected:
            if real:
                click.echo("")
            click.echo(
                "expected until use (these appear with the work, not problems yet — "
                "don't re-run doctor for reassurance):"
            )
            for line in _collapse_findings(expected):
                click.echo(f"  {line}")
    if any(f.level == "ERROR" for f in findings):
        raise SystemExit(1)


# ---------------------------------------------------------------- obsidian


@main.command("obsidian")
@click.option("--no-plugin", is_flag=True,
              help="Write the vault link config only; skip installing the flip plugin.")
def obsidian_cmd(no_plugin: bool) -> None:
    """Prepare the notebook (or beat) to open cleanly as an Obsidian vault.

    Merge-writes .obsidian/app.json so links Obsidian authors match the
    relative markdown links flip writes, installs the packaged flip plugin
    (doctor findings, hot view, status bar, open-by-id) into
    .obsidian/plugins/flip-notebook/, and enables it. Existing Obsidian
    settings survive; a second run changes nothing. Walkthrough:
    docs/obsidian.md.
    """
    root = find_notebook_root_pinned() or beat_mod.find_beat_root()
    if root is None:
        raise SystemExit(
            "not inside a flip notebook or beat (no index.md with flip/flip_beat "
            "frontmatter found here or above); run `flip new <slug>` or "
            "`flip beat new <slug>` first"
        )
    actions = obsidian_mod.prepare_vault(root, with_plugin=not no_plugin)
    if actions:
        for action in actions:
            click.echo(action)
    else:
        click.echo("already prepared — nothing to change")
    click.echo(f"next: open {root} in Obsidian ('Open folder as vault')")
    if not no_plugin:
        click.echo("      first time: Settings → Community plugins → turn off Restricted "
                   "mode, then enable 'flip'")
        click.echo("      if `flip` isn't on Obsidian's PATH, set the plugin's "
                   "'flip path' setting (see `which flip`)")
    click.echo("note: .obsidian/ is editor-local state — add it to the repo's "
               "gitignore if this notebook is committed")


# ---------------------------------------------------------------- workspace


@main.group(cls=SuggestGroup)
def ws() -> None:
    """Workspaces: many notebooks sharing one vault or repo (SPEC §18).

    A workspace root carries .flip/workspace.toml — the local table binding
    short handles to notebook paths, so qualified refs like recipes:A3 stay
    unambiguous. Handles are yours (like git remote names): the notebook's
    slug is only a suggestion, and the binding never ships with the bundle.
    Start with `flip ws init` at the vault/repo root; `flip doctor
    --workspace` audits the shared space.
    """


@ws.command("init")
def ws_init_cmd() -> None:
    """Declare the current directory a workspace root and bind what's here.

    Scans below for notebooks, proposes each one's slug as its handle
    (collisions get -2, -3 … — rename with `flip ws rename`), writes
    .flip/workspace.toml, and adds qualified aliases (recipes:A3) to entity
    pages so Obsidian autocomplete can disambiguate.
    """
    ws_obj = workspace_mod.ws_init(Path.cwd().resolve())
    for handle in sorted(ws_obj.notebooks):
        click.echo(f"{handle} → {ws_obj.notebooks[handle]}")
    click.echo(f"workspace initialized: {len(ws_obj.notebooks)} notebook(s) bound "
               f"→ {workspace_mod.WORKSPACE_FILE}")


@ws.command("list")
@click.option("--json", "as_json", is_flag=True,
              help="Emit handle, path, slug, uid, title, status rows as JSON.")
def ws_list(as_json: bool) -> None:
    """List bound notebooks: handle · slug · uid · path (status flags problems)."""
    rows = workspace_mod.ws_rows(workspace_mod.require_workspace_root())
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no notebooks bound (bind one: `flip ws add <path>`)")
        return
    for r in rows:
        line = f"{r['handle']} · {r.get('slug', '?')} · {r.get('uid') or '(no uid)'} · {r['path']}"
        if r.get("status") != "ok":
            line += f" [{r['status']}]"
        click.echo(line)


@ws.command("show")
@click.option("--open", "open_flag", is_flag=True,
              help="Only the open questions across bound notebooks (with re-pose counts).")
@click.option("--claims", "claims_flag", is_flag=True,
              help="Only the load-bearing claims still needing work across bound notebooks.")
@click.option("--json", "as_json", is_flag=True, help="Emit the roster as JSON.")
def ws_show_cmd(open_flag: bool, claims_flag: bool, as_json: bool) -> None:
    """Merged roster across bound notebooks: open questions (with re-pose
    counts), load-bearing claims needing work, and each notebook's
    kind/status/updated-age.

    A computed view over existing data — no new ledger (`flip ws list` stays
    the plain binding table). `--open`/`--claims` narrow to one lane.
    """
    if open_flag and claims_flag:
        raise SystemExit("pass at most one of --open/--claims")
    out = views.ws_show(
        workspace_mod.require_workspace_root(),
        open_only=open_flag, claims_only=claims_flag, as_data=as_json,
    )
    click.echo(json.dumps(out, ensure_ascii=False, indent=2) if as_json else out)


@ws.command("add")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--as", "handle", default=None, metavar="HANDLE",
              help="Handle to bind [default: the notebook's slug].")
def ws_add_cmd(path: Path, handle: str | None) -> None:
    """Bind a notebook already on disk to a handle in this workspace."""
    bound, rel = workspace_mod.ws_add(
        workspace_mod.require_workspace_root(), path.resolve(), handle
    )
    click.echo(f"bound {bound} → {rel}")


@ws.command("rename")
@click.argument("old")
@click.argument("new")
def ws_rename_cmd(old: str, new: str) -> None:
    """Rebind a handle, rewriting qualified refs (old:A3 → new:A3) workspace-wide.

    The same move as `git remote rename`: the notebook itself is untouched
    except its qualified aliases; prose citations, wikilinks, and frontmatter
    referencing the old handle are rewritten mechanically (captured bytes
    under sources/, derived/, and renders/ are never edited).
    """
    ws_root = workspace_mod.require_workspace_root()
    ref_files, alias_pages = workspace_mod.ws_rename(ws_root, old, new)
    click.echo(
        f"renamed {old} → {new}; rewrote refs in {ref_files} file(s), "
        f"aliases in {alias_pages} page(s)"
    )


@ws.command("rm")
@click.argument("handle")
def ws_rm_cmd(handle: str) -> None:
    """Unbind a handle (files stay on disk; only the binding and its
    qualified aliases are removed)."""
    workspace_mod.ws_rm(workspace_mod.require_workspace_root(), handle)
    click.echo(f"unbound {handle} (files kept — remove the directory yourself if intended)")


@main.command("import")
@click.argument("src", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--as", "handle", default=None, metavar="HANDLE",
              help="Handle to bind the import under [default: the bundle's slug].")
@click.option("--into", default=None, type=click.Path(path_type=Path),
              help="Directory to copy the bundle into [default: <workspace>/<handle>].")
@click.option("--update", "update_handle", default=None, metavar="HANDLE",
              help="Refresh an existing import from a newer copy of the same "
                   "notebook (uids must match) instead of adding a new one.")
def import_cmd(src: Path, handle: str | None, into: Path | None,
               update_handle: str | None) -> None:
    """Import a shared notebook (directory, OKF export, or BagIt bag).

    Copies the bundle into the enclosing workspace, binds it to a handle you
    own, and records provenance (origin, uid). Entity ids are never rekeyed —
    citations inside the bundle stay valid, and your own notes reference it
    as handle:id (SPEC §17-§18). --update is replace-if-uid-matches; merging
    diverged copies is out of scope.
    """
    ws_root = workspace_mod.require_workspace_root()
    if update_handle is not None:
        if handle is not None or into is not None:
            raise SystemExit("--update takes only SRC; --as/--into apply to new imports")
        summary = importer_mod.update_bundle(ws_root, update_handle, src.resolve())
        click.echo(f"updated {update_handle} from {src} (uid {summary['uid']})")
    else:
        summary = importer_mod.import_bundle(
            ws_root, src.resolve(), handle=handle,
            into=into.resolve() if into is not None else None,
        )
        click.echo(f"imported '{summary['slug']}' as {summary['handle']} → "
                   f"{summary['path']} (uid {summary['uid']})")
    errors, warns = summary.get("doctor_errors", 0), summary.get("doctor_warns", 0)
    if errors or warns:
        click.echo(f"doctor: {errors} error(s), {warns} warning(s) — "
                   f"cd {summary['path']} && flip doctor")


# ---------------------------------------------------------------- registry / export


@main.command()
@click.option("--root", "roots", multiple=True,
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Directory to scan for notebooks (repeatable) [default: cwd].")
def index(roots: tuple[Path, ...]) -> None:
    """Rebuild the per-user registry: scan roots, rewrite $FLIP_HOME/index.jsonl.

    One line per notebook (path, slug, kind, status, updated) — dashboards
    and task systems consume this file; flip never reads it back itself.
    """
    rows = registry.build_index([r.resolve() for r in roots] or [Path.cwd()])
    good = [r for r in rows if "error" not in r]
    for r in good:
        if r.get("workspace"):
            click.echo(f"workspace · {r['path']} · {len(r.get('notebooks', {}))} notebook(s)")
        else:
            click.echo(f"{r['slug']} · {r['kind']} · {r['status']} · {r['path']}")
    skipped = len(rows) - len(good)
    tail = f" ({skipped} skipped, see stderr)" if skipped else ""
    ws_count = sum(1 for r in good if r.get("workspace"))
    ws_part = f" and {ws_count} workspace(s)" if ws_count else ""
    click.echo(f"indexed {len(good) - ws_count} notebook(s){ws_part}{tail} → "
               f"{registry.flip_home() / registry.INDEX}")


@main.command()
def migrate() -> None:
    """Upgrade a notebook in place to the current profile version.

    v0.3 notebooks (notebook.toml + JSONL entity ledgers): the manifest moves
    into the root index.md frontmatter and every source/claim/decision/
    question/session becomes an entity page, preserving ids and fields.
    v0.4 notebooks: the manifest gains a uid and links.beat moves to the
    canonical ':' separator (stored '#' refs are still rewritten, though
    '#' reads were removed in 0.10).
    Resumable if interrupted; run `flip doctor` afterwards.
    """
    cwd = Path.cwd().resolve()
    root = next(
        (c for c in (cwd, *cwd.parents) if (c / migrate_mod.NOTEBOOK_TOML).is_file()), None
    )
    if root is None:
        # No v0.3 root above us: let migrate explain (already-v0.4 vs not a notebook).
        root = find_notebook_root_pinned() or cwd
    counts = migrate_mod.migrate(root)
    summary = ", ".join(
        f"{n} {name.replace('_', ' ')}"
        for name, n in counts.items()
        if isinstance(n, int) and (n or name != "already_migrated")
    )
    click.echo(f"migrated {root} · {summary}")
    click.echo("entity pages: references/ claims/ decisions/ questions/ sessions/ — "
               "run `flip doctor` to audit the result")


@main.group(cls=SuggestGroup)
def export() -> None:
    """Interop exports (SPEC §17) — projections; the notebook stays canonical."""


@export.command("bag")
@click.argument("dest", type=click.Path(path_type=Path))
def export_bag(dest: Path) -> None:
    """Write a BagIt 1.0 bag of the notebook at DEST for cold archival.

    data/ holds the notebook tree; manifest-sha256.txt carries per-file
    fixity. DEST must not exist yet.
    """
    path = export_mod.export_bag(require_notebook_root(), dest)
    click.echo(f"bag written to {path}")


@export.command("csl")
@click.option("--output", default=None, type=click.Path(path_type=Path),
              help="Write the CSL JSON here instead of stdout.")
def export_csl(output: Path | None) -> None:
    """Emit CSL JSON from the references/ pages for citation managers (Zotero etc.)."""
    items = export_mod.export_csl(require_notebook_root())
    text = json.dumps(items, ensure_ascii=False, indent=2)
    if output is None:
        click.echo(text)
    else:
        output.write_text(text + "\n", encoding="utf-8")
        click.echo(f"wrote {len(items)} CSL item(s) to {output}")


@export.command("okf")
@click.argument("dest", type=click.Path(path_type=Path))
@click.option("--include-private", is_flag=True,
              help="Export despite a non-public visibility policy, with the full source trail.")
@click.option("--announce", default=None, type=click.Path(path_type=Path),
              help="AGENTS.md file to point at the bundle via a FLIP marker block.")
def export_okf(dest: Path, include_private: bool, announce: Path | None) -> None:
    """Copy the notebook to DEST as an outside-facing OKF bundle (policy filter).

    The notebook already IS an OKF bundle; this honors `visibility` (refuses
    unless public or --include-private) and `source_trail_public` (custody
    detail ships, or reference pages reduce to judgment stubs). The bundle is
    a render — re-export rather than editing it. Notes: docs/wiki-alignment.md.
    """
    path = export_mod.export_okf(
        require_notebook_root(), dest, include_private=include_private, announce=announce
    )
    click.echo(f"OKF bundle written to {path}")


@export.command("json")
@click.option("--out", default=None,
              help="Write the JSON here (path), or '-' for stdout [default: stdout].")
@click.option("--include-private", is_flag=True,
              help="Emit despite a non-public visibility policy, with the full source trail.")
@click.option("--render-version", type=click.Choice(["1", "2"]), default="1",
              help="flip-render contract: 1 (stable default) or 2 (adds support "
                   "tuples, pipeline, provenance states, claim value/unit).")
def export_json_cmd(out: str | None, include_private: bool, render_version: str) -> None:
    """Emit the flip-render/1 (or /2) JSON projection for renderers and site generators.

    One stable, versioned, deterministic view of the notebook (identity,
    sources, claims incl. verifications, questions incl. formulations,
    decisions, session summaries, log tail). Policy-filtered like `export okf`:
    refuses unless visibility is public or --include-private, and strips
    source-trail custody (URLs, capture times, fixity, the work log) to
    judgment stubs when source_trail_public is false.
    """
    root = require_notebook_root()
    data = export_mod.export_json(root, include_private=include_private,
                                  render_version=int(render_version))
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if out in (None, "-"):
        click.echo(text)
    else:
        dest = Path(out).expanduser().resolve()
        root_resolved = root.resolve()
        if dest.is_relative_to(root_resolved) and not dest.is_relative_to(
            root_resolved / "renders"
        ):
            raise SystemExit(
                f"refusing to write inside the notebook ({out}): a render "
                "projection is a derived artifact, not evidence — use "
                "renders/<target>/ or a path outside the bundle (SPEC §11)"
            )
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            raise SystemExit(f"cannot write {out}: {exc}") from exc
        contract = (export_mod.RENDER_CONTRACT_2 if render_version == "2"
                    else export_mod.RENDER_CONTRACT)
        click.echo(f"wrote {contract} projection to {out}")


# ---------------------------------------------------------------- profiles


@main.command("profiles")
def profiles_cmd() -> None:
    """List available notebook profiles (kinds) for `flip new --kind`.

    Shows the profiles shipped with flip plus any notebook-local overrides
    under .flip/profiles/ when run inside a notebook.
    """
    root = find_notebook_root_pinned()
    shipped = profiles_mod.list_profiles()
    local_dir = root / ".flip" / "profiles" if root else None
    local = (sorted(p.name.removesuffix(".toml") for p in local_dir.glob("*.toml"))
             if local_dir is not None and local_dir.is_dir() else [])
    for pid in shipped:
        prof = profiles_mod.load_profile(pid, root)
        marker = " (local override)" if pid in local else ""
        click.echo(f"{pid}{marker} — {prof.description}")
    for pid in (p for p in local if p not in shipped):
        prof = profiles_mod.load_profile(pid, root)
        click.echo(f"{pid} (local) — {prof.description}")


# ---------------------------------------------------------------- beat


@main.group(name="beat", cls=SuggestGroup)
def beat() -> None:
    """Beats: the standing-mission layer above notebooks (SPEC §14).

    A beat groups many notebooks under one mission ("school funding in this
    county") and holds the cross-notebook memory: threads/ (units of
    attention, ids TH#), coverage.jsonl (outcomes, including deliberate
    drops), and child notebooks under notebooks/. Start with `flip beat new
    <slug>`; every other beat command works from anywhere inside the beat —
    including from inside a child notebook (the walk climbs past the
    notebook root). `flip beat show` is the ranked triage view.
    """


@beat.command("new")
@click.argument("slug")
@click.option("--mission", default="", help="One line a stranger could act on; "
              "lands in the manifest and beat.md.")
@click.option("--dest", default=None, type=click.Path(path_type=Path),
              help="Directory to create the beat in [default: ./<slug>].")
def beat_new(slug: str, mission: str, dest: Path | None) -> None:
    """Create a beat: index.md manifest + beat.md prompts, nothing else.

    threads/, notebooks/, log/, and coverage.jsonl appear lazily as commands
    need them. Then cd in and open the first thread.
    """
    dest = dest if dest is not None else Path.cwd() / slug
    path = beat_mod.create_beat(dest, slug, mission=mission)
    click.echo(f"created beat '{slug}' at {path}")
    click.echo(f'next: cd {path} && flip beat thread add "<title>" --kind arc|vein')


@beat.group("thread", cls=SuggestGroup)
def beat_thread() -> None:
    """Threads: the beat's unit of attention (threads/<slug>.md, ids TH#).

    Two kinds: arc (a self-initiated investigation pulled over time) and
    vein (a recurring story-type monitored reactively). Score them 0–1 on
    payoff/access/urgency/connection/uniqueness — `flip beat show` ranks
    open/active threads by the weighted sum (missing scores read as 0.5).
    """


@beat_thread.command("add")
@click.argument("title")
@click.option("--kind", required=True, type=click.Choice(beat_mod.THREAD_KINDS),
              help="arc: self-initiated investigation · vein: recurring story-type.")
@click.option("--note", default=None,
              help="Opening rationale for the thread body [default: the title].")
@click.option("--score", "score_pairs", multiple=True, metavar="KEY=VALUE",
              help="Triage score 0–1 (payoff|access|urgency|connection|uniqueness), "
                   "e.g. --score payoff=0.8; repeatable. Unscored keys rank as 0.5.")
def beat_thread_add(title: str, kind: str, note: str | None,
                    score_pairs: tuple[str, ...]) -> None:
    """Open a thread, allocating the next TH#. Cite it in prose as [TH3]."""
    page = beat_mod.add_thread(beat_mod.require_beat_root(), title, kind, note=note,
                               scores=beat_mod.parse_score_pairs(score_pairs))
    click.echo(f"{page.id} · {page.fm.get('kind', '?')} · open · {page.fm.get('title', '')}")


@beat_thread.command("update")
@click.argument("thread_id", metavar="THREAD_ID")
@click.option("--status", default=None,
              type=click.Choice([s for s in beat_mod.THREAD_STATUSES if s != "dropped"]),
              help="New status (dropping goes through `thread drop` — it needs a reason).")
@click.option("--note", default=None,
              help="Progress note, appended to the thread body under today's date.")
@click.option("--score", "score_pairs", multiple=True, metavar="KEY=VALUE",
              help="Re-judge a triage score 0–1, e.g. --score access=0.2; repeatable. "
                   "Other scores keep their values.")
@click.option("--next-review", default=None, metavar="DATE",
              help="YYYY-MM-DD to resurface a dormant thread; `flip beat show` "
                   "flags dormant threads past this date.")
def beat_thread_update(thread_id: str, status: str | None, note: str | None,
                       score_pairs: tuple[str, ...], next_review: str | None) -> None:
    """Update a thread in place: status, scores, next review, a dated note.

    Round-trip rule: only the keys you pass change; foreign frontmatter and
    the running rationale in the body survive.
    """
    page = beat_mod.update_thread(
        beat_mod.require_beat_root(), thread_id, status=status, note=note,
        scores=beat_mod.parse_score_pairs(score_pairs), next_review=next_review,
    )
    line = f"{page.id} · {page.fm.get('kind', '?')} · {page.fm.get('status', '?')}"
    if page.fm.get("next_review"):
        line += f" · next review {page.fm['next_review']}"
    click.echo(line)


@beat_thread.command("drop")
@click.argument("thread_id", metavar="THREAD_ID")
@click.option("--reason", required=True,
              help="Why the thread died — the payload; it lands on the page and "
                   "in coverage.jsonl so nobody re-scouts the dead angle.")
def beat_thread_drop(thread_id: str, reason: str) -> None:
    """Drop a thread: negative coverage is first-class (SPEC §14)."""
    page = beat_mod.drop_thread(beat_mod.require_beat_root(), thread_id, reason)
    click.echo(f"{page.id} dropped · {page.fm.get('dropped_reason', '')}")


@beat.command("graduate")
@click.argument("thread_id", metavar="THREAD_ID")
@click.argument("notebook_slug", metavar="NOTEBOOK_SLUG")
@click.option("--kind", default="scout", show_default=True,
              help="Notebook profile for the new child (see `flip profiles`).")
@click.option("--title", default="", help="Notebook title; the slug is used when omitted.")
def beat_graduate(thread_id: str, notebook_slug: str, kind: str, title: str) -> None:
    """Graduate a thread into a child notebook under notebooks/<slug>/.

    The beat's core act: the thread goes active with `notebook: <slug>`, the
    notebook manifest links back (links.beat: "<beat>#<TH#>"), and a coverage
    event records the outcome. Then cd in and work it like any notebook.
    """
    path = beat_mod.graduate(beat_mod.require_beat_root(), thread_id, notebook_slug,
                             kind=kind, title=title)
    click.echo(f"{thread_id} → {kind} notebook '{notebook_slug}' at {path}")
    click.echo(f'next: cd {path} && flip log "started" — see `flip --help` for the toolkit')


@beat.command("show")
@click.option("--json", "as_json", is_flag=True, help="Emit the view as JSON.")
def beat_show(as_json: bool) -> None:
    """Show the beat triage view: ranked threads, dormant due, notebooks, log.

    Open/active threads are ranked by the weighted score sum (weights from
    the beat manifest, defaults .30/.25/.20/.15/.10); a missing score reads
    as 0.5. Computed on the fly — ranking never mutates pages (SPEC §14).
    """
    out = beat_mod.beat_show(beat_mod.require_beat_root(), as_data=as_json)
    click.echo(json.dumps(out, ensure_ascii=False, indent=2) if as_json else out)


@beat.command("log")
@click.argument("text")
def beat_log(text: str) -> None:
    """Append one event to the beat work log (log/log.jsonl); actor auto-detected.

    Beat-level memory: sweeps, tips, coverage decisions that belong to the
    mission rather than to any one notebook. log.md regenerates from it.
    """
    row = beat_mod.log_event(beat_mod.require_beat_root(), text)
    click.echo(f"logged {row['ts']} · {row['actor']}")


# ---------------------------------------------------------------- kind


from . import kinds as kinds_mod  # noqa: E402 — appended at file end by design


@main.group(cls=SuggestGroup)
def kind() -> None:
    """Outcome kinds (design-outcome-kinds.md): what you're making, not how.

    A kind names a desired output ("a lit review," "a decision packet") and
    brings a contract — the requirements a finished notebook of that shape
    must satisfy — plus optional workflow phases and a versioning mode.
    Kinds load from built-ins, $FLIP_HOME/kinds/, and <notebook>/.flip/kinds/
    (later wins); today's `flip new --kind` profiles show up here too, as
    rigor-shaped kinds with empty contracts. Start with `flip kind list`.
    """


@kind.command("list")
@click.option("--json", "as_json", is_flag=True,
              help="Emit id/origin/version/summary rows as JSON.")
def kind_list(as_json: bool) -> None:
    """List every visible kind: built-in, user, notebook-local, and profiles.

    Later sources win on id collision (built-in -> $FLIP_HOME/kinds/ ->
    <notebook>/.flip/kinds/); shipped profiles (scout, ledger, …) appear too,
    as kinds with an empty contract.
    """
    root = find_notebook_root_pinned()
    rows = kinds_mod.list_kinds(root)
    if as_json:
        click.echo(json.dumps(
            [
                {"id": k.id, "origin": k.origin, "version": k.version,
                 "summary": k.summary, "aka": k.aka}
                for k in rows
            ],
            ensure_ascii=False, indent=2,
        ))
        return
    if not rows:
        click.echo("no kinds found")
        return
    width = max(len(k.id) for k in rows)
    for k in rows:
        one_line = k.summary.strip().split("\n", 1)[0] if k.summary else "(no summary)"
        click.echo(f"{k.id:<{width}}  {k.origin:<9}  {one_line}")
        if k.aka:
            click.echo(f"{'':<{width}}  {'':<9}  aka: {', '.join(k.aka)}")


@kind.command("show")
@click.argument("kind_id", metavar="ID")
@click.option("--json", "as_json", is_flag=True, help="Emit the kind's parsed shape as JSON.")
def kind_show(kind_id: str, as_json: bool) -> None:
    """Show a kind's contract and workflow — the doctor-checkable shape.

    Unknown ids are refused with the list of known ones (`flip kind list`).
    """
    root = find_notebook_root_pinned()
    k = kinds_mod.load_kind(kind_id, root)
    if as_json:
        click.echo(json.dumps(
            {
                "id": k.id, "version": k.version, "origin": k.origin, "summary": k.summary,
                "defaults": k.defaults,
                "contract": [asdict(r) for r in k.contract],
                "workflow": k.workflow, "versioning": k.versioning,
                "requires": k.requires,
            },
            ensure_ascii=False, indent=2,
        ))
        return
    click.echo(f"{k.id} · {k.origin} · v{k.version or '?'}")
    if k.summary:
        click.echo(k.summary.strip())
    if k.source_path:
        click.echo(f"source: {k.source_path}")
    if not k.contract:
        click.echo("\nno contract requirements (a rigor-shaped kind, or not yet written).")
    else:
        click.echo("\ncontract:")
        for r in k.contract:
            tag = " [prospective]" if r.prospective else ""
            click.echo(f"  - {r.id} (min {r.min}){tag}: {r.what}")
            click.echo(f"      assembled by: {r.assembled_by}")
    if k.workflow:
        click.echo("\nworkflow:")
        for phase in k.workflow:
            name = phase.get("id") or phase.get("name") or "?"
            produces = phase.get("produces")
            line = f"  - {name}"
            if produces:
                line += f" -> produces: {produces}"
            click.echo(line)
    if k.versioning:
        click.echo(f"\nversioning: mode={k.versioning.get('mode', '?')}")
    if k.requires:
        click.echo("\nrequires (slots a declared discipline must own; "
                   "informational until the manifest declares disciplines):")
        for req in k.requires:
            slot = req.get("slot", "?")
            default = req.get("default")
            line = f"  - slot '{slot}'"
            if default:
                line += f" (default: {default})"
            click.echo(line)


@kind.command("adopt")
@click.argument("kind_id", metavar="ID")
def kind_adopt(kind_id: str) -> None:
    """Adopt a kind onto this notebook: set manifest kind, log a
    crystallization event, and print the gap manifest.

    Late adoption is not a foul: the gap manifest says exactly what's
    missing and whether it can still be added honestly (recoverable), added
    but not contemporaneously (reconstructible-with-loss), or gone for good
    because it needed to be frozen before the work started
    (unrecoverable-by-construction). Refuses if the kind id is unknown.
    """
    root = require_notebook_root()
    k, rows = kinds_mod.adopt_kind(root, kind_id)
    click.echo(f"kind -> {k.id} (crystallization event logged to log/log.jsonl)")
    if not rows:
        click.echo("no contract requirements — nothing to gap-check.")
        return
    click.echo("\ngap manifest:")
    for row in rows:
        status = "met" if row.tier == "met" else f"{row.have}/{row.min} — {row.tier}"
        click.echo(f"  - {row.requirement_id}: {status}")
        if row.tier != "met":
            click.echo(f"      {row.what} (assembled by {row.assembled_by})")


@kind.command("new")
@click.argument("kind_id", metavar="ID")
@click.option("--force", is_flag=True, help="Overwrite an existing scaffold at that path.")
def kind_new(kind_id: str, force: bool) -> None:
    """Scaffold $FLIP_HOME/kinds/<id>.toml from a commented template.

    The template is the documentation: every key is explained in place with
    a safe default. Edit it, then `flip kind show <id>` to check the result.
    """
    path = kinds_mod.scaffold_kind(kind_id, force=force)
    click.echo(str(path))
    click.echo(f"edit it, then `flip kind show {kind_id}`")


# ---------------------------------------------------------------- discipline


from . import disciplines as disciplines_mod  # noqa: E402 — appended at file end by design


@main.group(cls=SuggestGroup)
def discipline() -> None:
    """Disciplines (design-composition-0.14.md): the standard the work is held to.

    A discipline names a policy standard — the slots it owns, the gates it
    applies (enforced gates block; attested gates record third-party
    verification), and its advisory checks. Kinds say what you're making;
    disciplines say the standard it's held to. Declare pins in the manifest
    (`disciplines: [lineage@1, forecasting@1]`) and `flip doctor` resolves,
    composes, and labels. Start with `flip discipline list`.
    """


@discipline.command("list")
@click.option("--json", "as_json", is_flag=True,
              help="Emit id/version/kind/origin/summary/aka rows as JSON.")
def discipline_list(as_json: bool) -> None:
    """List every visible discipline: built-in, user, and notebook-local.

    Later sources win on id collision (built-in -> $FLIP_HOME/disciplines/
    -> <notebook>/.flip/disciplines/).
    """
    root = find_notebook_root_pinned()
    rows = disciplines_mod.list_disciplines(root)
    if as_json:
        click.echo(json.dumps(
            [
                {"id": d.id, "version": d.version, "kind": d.kind,
                 "origin": d.origin, "summary": d.summary, "aka": d.aka}
                for d in rows
            ],
            ensure_ascii=False, indent=2,
        ))
        return
    if not rows:
        click.echo("no disciplines found")
        return
    width = max(len(f"{d.id}@{d.version}") for d in rows)
    for d in rows:
        one_line = d.summary.strip().split("\n", 1)[0] if d.summary else "(no summary)"
        pin = f"{d.id}@{d.version}"
        click.echo(f"{pin:<{width}}  {d.kind:<12}  {d.origin:<9}  {one_line}")
        if d.aka:
            click.echo(f"{'':<{width}}  {'':<12}  {'':<9}  aka: {', '.join(d.aka)}")


def _check_display(check) -> str:
    """One line for a gate/check target: a code, or the predicate spelled out."""
    if isinstance(check, str):
        return f"check {check}"
    requires = check.get("requires", "?")
    line = f"{check.get('class', '?')}.{check.get('field', '?')} {requires}"
    if requires == "one_of":
        line += f" [{', '.join(str(v) for v in check.get('one_of') or [])}]"
    return line


@discipline.command("show")
@click.argument("disc_id", metavar="ID")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the discipline's parsed shape as JSON.")
def discipline_show(disc_id: str, as_json: bool) -> None:
    """Show a discipline's slots, gates, and checks — the composable shape.

    Unknown ids are refused with the list of known ones (`flip discipline
    list`).
    """
    root = find_notebook_root_pinned()
    d = disciplines_mod.load_discipline(disc_id, root)
    if as_json:
        click.echo(json.dumps(
            {
                "id": d.id, "version": d.version, "kind": d.kind, "origin": d.origin,
                "summary": d.summary, "aka": d.aka, "governs": d.governs,
                "slots": [asdict(s) for s in d.slots],
                "gates": [asdict(g) for g in d.gates],
                "checks": d.checks, "vocabulary": d.vocabulary,
                "depends_on": d.depends_on, "conflicts": d.conflicts,
                "corrections": d.corrections, "extends": d.extends,
            },
            ensure_ascii=False, indent=2,
        ))
        return
    click.echo(f"{d.id}@{d.version} · {d.kind} · {d.origin}")
    if d.summary:
        click.echo(d.summary.strip())
    if d.source_path:
        click.echo(f"source: {d.source_path}")
    if d.governs:
        click.echo(f"governs: {', '.join(d.governs)}")
    if d.slots:
        click.echo("\nslots (the unit of ownership in composition):")
        for s in d.slots:
            click.echo(f"  - {s.id}" + ("" if s.owns else " (owns: false)"))
    if d.gates:
        click.echo("\ngates (enforced block when this discipline owns the slot; "
                   "attested record, never block):")
        for g in d.gates:
            click.echo(f"  - {g.id} @ {g.slot} · {g.kind} · {_check_display(g.check)}")
    if d.checks:
        click.echo("\nchecks (advisory rubric — labeled, never blocking):")
        for entry in d.checks:
            if "check" in entry:
                click.echo(f"  - check {entry['check']}")
            else:
                name = entry.get("id")
                prefix = f"{name} · " if name else ""
                click.echo(f"  - {prefix}{_check_display(entry)}")
    if d.vocabulary:
        click.echo("\nvocabulary:")
        for term in sorted(d.vocabulary):
            click.echo(f"  - {term}: {d.vocabulary[term]}")
    if d.depends_on:
        click.echo(f"\ndepends on (absent partner is a doctor WARN, never a "
                   f"conflict): {', '.join(d.depends_on)}")
    if d.conflicts:
        click.echo("\nconflicts (the manifest resolves; never silently merged):")
        for c in d.conflicts:
            click.echo(f"  - with {c.get('with', '?')} on slot '{c.get('slot', '?')}'")
    if d.corrections:
        click.echo("\ncorrections policy (carried with the discipline; not yet "
                   "enforced): " + ", ".join(f"{k}={v}" for k, v in d.corrections.items()))
    problems = disciplines_mod.validate_discipline(d)
    if problems:
        click.echo("\nproblems (doctor reports these as bad-discipline):")
        for p in problems:
            click.echo(f"  - {p}")


@discipline.command("new")
@click.argument("disc_id", metavar="ID")
@click.option("--force", is_flag=True, help="Overwrite an existing scaffold at that path.")
def discipline_new(disc_id: str, force: bool) -> None:
    """Scaffold $FLIP_HOME/disciplines/<id>.toml from a commented template.

    The template is the documentation: every key is explained in place,
    including the versioning rule (authored disciplines start at 0.1; 1.x is
    reserved for enforcement flip itself guarantees). Edit it, then
    `flip discipline show <id>` to check the result.
    """
    path = disciplines_mod.scaffold_discipline(disc_id, force=force)
    click.echo(str(path))
    click.echo(f"edit it, then `flip discipline show {disc_id}`")


# ---------------------------------------------------------------- forecast


from . import forecast as forecast_mod  # noqa: E402 — appended near the kind group by design


@main.group(cls=SuggestGroup)
def forecast() -> None:
    """Forecasts as pages (forecasts/<slug>.md, ids FC#): dated, scoreable bets.

    The forward half of the two-object rule (SPEC §7): claims are verified
    and never carry probabilities; forecasts ship early at low confidence,
    update in the open (`forecast update`), and get scored on their dates
    (`forecast resolve` — every resolution lands in log/resolutions.jsonl).
    `flip show --forecasts` is the board + running record; `forecast due`
    is the sweep list for any runner.
    """


@forecast.command("add")
@click.argument("question")
@click.option("--resolves-by", "resolves_by", default=None, metavar="YYYY-MM-DD",
              help="The resolution date — mandatory; no undated forecasts.")
@click.option("--resolves-via", "resolves_via", multiple=True, metavar="SURFACE",
              help="A surface that resolves this (repeatable) — what the desk "
                   "will actually look at on the date.")
@click.option("--annul-if", "annul_if", default=None,
              help="Mandatory: the condition under which the question stops "
                   "being askable (resolves void, scores nothing).")
@click.option("--probability", default=None, metavar="0..1",
              help="The estimate, a float in [0, 1].")
@click.option("--confidence", default=None, metavar="0..1",
              help="How much the estimate rests on, in [0, 1] — never merged "
                   "with probability.")
@click.option("--criteria", "resolution_criteria", default=None,
              help="Resolution criteria prose, edge cases pre-answered.")
@click.option("--ladder", "ladder", multiple=True, metavar="STEP",
              help="Resolution source ladder entry, best first (repeatable) — "
                   "the ranked fallback when the primary surface fails.")
@click.option("--resolver", default=None,
              help="Who or what reads the surface and calls it.")
@click.option("--base-rate", "base_rate", default=None, metavar="TEXT",
              help="The outside view AS STATED, a string with its own "
                   "numerator/denominator — never a bare number.")
@click.option("--predictability", default=None,
              type=click.Choice(forecast_mod.PREDICTABILITY),
              help="How forecastable this domain is at all.")
@click.option("--bears-on", "bears_on", multiple=True, metavar="TYPE:REF",
              help="Typed edge to what this bet informs (claim:<ref>, "
                   "cluster:<ref>, question:<ref>); repeatable.")
@click.option("--generated-by", "generated_by", default=None,
              help="What emitted this forecast (a generator name, or a person).")
@click.option("--horizon", default=None,
              help="Planning horizon the bet informs (not the resolution date).")
def forecast_add(question: str, resolves_by: str | None, resolves_via: tuple[str, ...],
                 annul_if: str | None, probability: str | None, confidence: str | None,
                 resolution_criteria: str | None, ladder: tuple[str, ...],
                 resolver: str | None, base_rate: str | None, predictability: str | None,
                 bears_on: tuple[str, ...], generated_by: str | None,
                 horizon: str | None) -> None:
    """Open a forecast (status "open"), allocating the next FC#."""
    page = forecast_mod.add_forecast(
        require_notebook_root(), question, resolves_by, list(resolves_via), annul_if,
        probability, confidence, resolution_criteria=resolution_criteria,
        resolution_source_ladder=list(ladder), resolver=resolver, base_rate=base_rate,
        predictability=predictability, bears_on=list(bears_on),
        generated_by=generated_by, horizon=horizon,
    )
    vias = ", ".join(page.fm.get("resolves_via") or []) or "no surface named"
    click.echo(f"{page.id} open · p={page.fm['probability']} c={page.fm['confidence']} · "
               f"resolves {page.fm['resolves_by']} via {vias}")


@forecast.command("update")
@click.argument("fid", metavar="FORECAST_ID")
@click.option("--probability", default=None, metavar="0..1",
              help="New probability in [0, 1].")
@click.option("--confidence", default=None, metavar="0..1",
              help="New confidence in [0, 1].")
@click.option("--note", default=None, help="Why the estimate moved.")
def forecast_update(fid: str, probability: str | None, confidence: str | None,
                    note: str | None) -> None:
    """Move a forecast's current estimate; the old one stays in `updates:`.

    Append-only: every update lands as a dated record, so the whole path
    from opening estimate to resolution survives on the page.
    """
    page = forecast_mod.update_forecast(require_notebook_root(), fid,
                                        probability=probability,
                                        confidence=confidence, note=note)
    click.echo(f"{page.id} · p={page.fm.get('probability')} c={page.fm.get('confidence')} · "
               f"{len(page.fm.get('updates') or [])} update(s) on record")


@forecast.command("resolve")
@click.argument("fid", metavar="FORECAST_ID")
@click.argument("outcome", type=click.Choice(["yes", "no", "void"]))
@click.option("--note", default=None,
              help="What the surface showed — recorded as the resolution evidence.")
def forecast_resolve(fid: str, outcome: str, note: str | None) -> None:
    """Resolve a forecast on its surface: yes | no | void. Final.

    Flips the status, appends the closing update, logs a forecast-resolve
    event, and writes the scoring row (prior · posterior · shift) to
    log/resolutions.jsonl — the record `flip show --forecasts` reads back.
    """
    page = forecast_mod.resolve_forecast(require_notebook_root(), fid, outcome, note=note)
    click.echo(f"{page.id} → {page.fm.get('status')} · scoring row appended to "
               f"log/resolutions.jsonl")


@forecast.command("decline")
@click.argument("text")
@click.option("--reason", required=True,
              help="Why this generated question was declined — the payload.")
@click.option("--fold-into", "fold_into", default=None, metavar="FORECAST_ID",
              help="The existing forecast that absorbed the useful part "
                   "(e.g. as an annul_if clause).")
def forecast_decline(text: str, reason: str, fold_into: str | None) -> None:
    """Record a declined generated question in log/declined-forecasts.jsonl.

    The fold: declined generations are negative coverage — a good share are
    load-bearing elsewhere; --fold-into records where the part went.
    """
    row = forecast_mod.decline_forecast(require_notebook_root(), text, reason,
                                        fold_into=fold_into)
    tail = f" · folded into {row['fold_into']}" if row.get("fold_into") else ""
    click.echo(f"declined {row['ts']} · {row['reason']}{tail}")


@forecast.command("due")
@click.option("--within", default=30, show_default=True, metavar="DAYS",
              help="Include open forecasts resolving within this many days.")
@click.option("--json", "as_json", is_flag=True, help="Emit the rows as JSON.")
def forecast_due(within: int, as_json: bool) -> None:
    """List open forecasts past or near their resolves_by date, soonest first.

    The sweep list: flip records, runners run — any agent runtime gets the
    resolution loop from this listing without flip owning cadence.
    """
    rows = forecast_mod.due_forecasts(require_notebook_root(), within_days=within)
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo(f"no open forecasts due within {within} day(s)")
        return
    for r in rows:
        days = r.get("days_left")
        when = f"overdue {-days}d" if isinstance(days, int) and days < 0 else f"in {days}d"
        click.echo(f"{r.get('id', '?')} · {r.get('resolves_by', '?')} ({when}) · "
                   f"p={r.get('probability', '?')}/c={r.get('confidence', '?')} · "
                   f"{r.get('description', '')}")


@forecast.command("list")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the page frontmatter (+ slug, path) as JSON.")
def forecast_list(as_json: bool) -> None:
    """List every forecast (and cluster): id · status · resolves_by · p/c · question."""
    rows = forecast_mod.list_forecasts(require_notebook_root())
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no forecasts recorded (forecasts/ is absent or empty)")
        return
    for r in rows:
        if r.get("type") == "Cluster":
            click.echo(f"{r.get('id', '?')} · {r.get('status', 'open')} · cluster · "
                       f"proxies: {', '.join(str(p) for p in r.get('proxies') or []) or 'none'} · "
                       f"{r.get('description', '')}")
            continue
        click.echo(f"{r.get('id', '?')} · {r.get('status', '?')} · "
                   f"{r.get('resolves_by', '?')} · "
                   f"p={r.get('probability', '?')}/c={r.get('confidence', '?')} · "
                   f"{r.get('description', '')}")


if __name__ == "__main__":  # pragma: no cover
    main()
