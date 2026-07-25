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
from dataclasses import asdict
from pathlib import Path

import click

from . import (
    beat as beat_mod,
    claims,
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
    views,
    workspace as workspace_mod,
)
from .util import (
    find_notebook_root_pinned,
    find_workspace_root,
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
def add_source(target: str, kind: str | None, via: str | None, note: str | None) -> None:
    """Capture a source: fetch/copy into sources/raw/, hash it, open a page.

    Use the moment you rely on something external — URL, DOI, or local file.
    The references/ page opens at grade "?"; judge it with `flip grade` once
    read — ungraded sources never count toward claim verification.
    """
    root = require_notebook_root()
    if kind == "lookup":
        click.echo(
            "note: --kind lookup is deprecated — use `flip ask`. Cited synthesis is a "
            "lead (grade C), so it now lands in sessions/, not as a source. Move your "
            "[fetchers].lookup command to [research].ask in config.toml.",
            err=True,
        )
        _emit_ask(root, target, via, as_json=False)
        return
    page = sources.add_source(root, target, kind=kind, note=note, via=via)
    rel = page.path.relative_to(root).as_posix()
    click.echo(f"{page.id} · {page.fm.get('local', '')} · {rel} (grade ?)")
    click.echo(f"judge it after reading: flip grade {page.id} "
               f"--independence independent|corroborated|self-reported|derivative "
               f"--basis … [--n … --base-defined|--base-undefined]")


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
@click.option("--grade", "legacy_grade", default=None, hidden=True)
def grade(source_id: str, independence: str | None, basis: str | None, n: str | None,
          method: str | None, vintage: str | None, base_defined: bool | None,
          freshness: str | None, notes: str | None, legacy_grade: str | None) -> None:
    """Record the support tuple on a source's page (SPEC §5.4).

    Use after actually reading a source; the tuple gates claim verification
    and the letter grade is DERIVED from it, never authored. Only the
    judgment keys change — the rest of the page round-trips.
    """
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
    """
    rows = sources.list_sources(require_notebook_root())
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no sources captured (references/ is absent or empty)")
        return
    for r in rows:
        judgment = (f"{r.get('grade', '?')}/{r.get('independence', '?')}"
                    f"/{r.get('freshness', '?')}")
        click.echo(f"{r.get('id', '?')} · {judgment} · "
                   f"{r.get('title') or r.get('local', '')} · {r.get('path', '')}")


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


@question.command("answer")
@click.argument("qid", metavar="ID")
@click.option("--note", default=None,
              help="Where the answer landed; recorded under '## Answer' on the page.")
def question_answer(qid: str, note: str | None) -> None:
    """Mark a question answered: status, answered timestamp, and actor land
    on the page; the ask text stays. Pass --note to record the answer itself.
    """
    if not re.fullmatch(r"Q\d+", qid):
        raise SystemExit(f"'{qid}' is not a question id (expected Q<number>, e.g. Q2); "
                         "`flip question list` shows them")
    ledgers.answer_question(require_notebook_root(), qid, note=note)
    click.echo(f"{qid} answered")


@question.command("repose")
@click.argument("qid", metavar="ID")
@click.argument("text")
def question_repose(qid: str, text: str) -> None:
    """Re-pose a question with a sharper formulation (append-only).

    The new text becomes current; the superseded formulation is preserved in
    the page's `formulations:` history and a dated "Re-posed" body section, and
    a question-repose event lands in the log. The id, slug, and status stay —
    nothing is overwritten, so the full journey survives.
    """
    if not re.fullmatch(r"Q\d+", qid):
        raise SystemExit(f"'{qid}' is not a question id (expected Q<number>, e.g. Q2); "
                         "`flip question list` shows them")
    page = ledgers.repose_question(require_notebook_root(), qid, text)
    click.echo(f"{qid} re-posed · {page.fm.get('description', '')} · "
               f"{len(page.fm.get('formulations') or [])} prior formulation(s) kept")


@question.command("list")
@click.option("--json", "as_json", is_flag=True, help="Emit the rows as JSON.")
def question_list(as_json: bool) -> None:
    """List every question with its current status: id · open/answered · text.

    Open ones also surface in `flip show`; this is the full view (answered
    questions keep their pages — ids are never reused).
    """
    rows = ledgers.list_questions(require_notebook_root())
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no questions recorded (questions/ is absent or empty)")
        return
    for r in rows:
        click.echo(f"{r.get('id', '?')} · {r.get('status', 'open')} · {r.get('text', '')}")


# ---------------------------------------------------------------- claims


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
              help="Backing source id (a references/ page, e.g. A3); repeatable.")
@click.option("--load-bearing", is_flag=True,
              help="The piece falls over if this claim is wrong; doctor audits these.")
@click.option("--notes", default=None, help="Caveats, e.g. 'single vendor study'.")
@click.option("--value", default=None, metavar="TEXT",
              help='The claim\'s number as data, e.g. "4.2" or "~42" or "70-75" — '
                   "renders and exports carry it; prose alone can't.")
@click.option("--unit", default=None, metavar="UNIT",
              help='Unit for --value, e.g. "percent", "USD", "students".')
def claim_add(text: str, source_ids: tuple[str, ...], load_bearing: bool,
              notes: str | None, value: str | None, unit: str | None) -> None:
    """Assert a claim (status "asserted"), allocating the next C#."""
    root = require_notebook_root()
    page = claims.add_claim(root, text, list(source_ids),
                            load_bearing=load_bearing, notes=notes,
                            value=value, unit=unit)
    srcs = ", ".join(claims.source_ids(page.fm)) or "none"
    click.echo(f"{page.id} asserted · sources: {srcs} · "
               f"corroboration: {page.fm.get('independent_corroboration', 0)}")
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
               f"corroboration: {page.fm.get('independent_corroboration', 0)}")


@claim.command("list")
@click.option("--status", default=None, type=click.Choice(claims.STATUSES),
              help="Only claims in this status.")
@click.option("--json", "as_json", is_flag=True,
              help="Emit the page frontmatter (+ slug, path) as JSON.")
def claim_list(status: str | None, as_json: bool) -> None:
    """List claims, optionally filtered by status (grouped view: `flip show --claims`)."""
    rows = claims.list_claims(require_notebook_root(), status=status)
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no claims" + (f" with status '{status}'" if status else " recorded"))
        return
    for r in rows:
        flag = " [load-bearing]" if r.get("load_bearing") else ""
        srcs = ", ".join(str(s) for s in r.get("sources", [])) or "none"
        click.echo(f"{r.get('id', '?')} · {r.get('status', '?')}{flag} · "
                   f"{r.get('description', '')} · sources: {srcs}")


@claim.group("source", cls=SuggestGroup)
def claim_source() -> None:
    """Link or unlink backing sources on a claim after the fact.

    Both regenerate the claim's footnote attribution and recompute its
    independent_corroboration — the post-hoc fix for a claim asserted before
    its sources were captured. Ungraded sources link but never count toward
    the verification bar.
    """


@claim_source.command("add")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("source_ids", nargs=-1, required=True, metavar="SOURCE_ID...")
def claim_source_add(claim_id: str, source_ids: tuple[str, ...]) -> None:
    """Link one or more source ids to a claim. Unknown ids are refused."""
    page, added, warnings = claims.add_claim_sources(
        require_notebook_root(), claim_id, list(source_ids)
    )
    click.echo(f"{page.id} · linked {', '.join(added)} · sources: "
               f"{', '.join(claims.source_ids(page.fm)) or 'none'} · "
               f"corroboration: {page.fm.get('independent_corroboration', 0)}")
    for sid in warnings:
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
               f"corroboration: {page.fm.get('independent_corroboration', 0)}")


@claim.command("verify")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.option("--method", required=True, type=click.Choice(claims.VERIFICATION_METHODS),
              help="adversarial (skeptic pass) · independent-sources (records "
                   "corroboration reasoning) · recomputation (re-derive the result).")
@click.option("--against", multiple=True, metavar="REF",
              help="Evidence/ref consulted during the check (repeatable), e.g. --against A7.")
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


# ---------------------------------------------------------------- views / navigation


@main.command()
@click.option("--claims", "claims_flag", is_flag=True,
              help="All claims grouped by status.")
@click.option("--stale", "stale_flag", is_flag=True,
              help="What went cold: dated sources, open questions, stuck claims.")
@click.option("--json", "as_json", is_flag=True, help="Emit the view as JSON.")
def show(claims_flag: bool, stale_flag: bool, as_json: bool) -> None:
    """Show a computed view of the notebook; default is the hot view.

    The hot view is the resume-here screen: open questions, claims needing
    work, recent log, latest session. Views are computed from the pages and
    ledgers, never stored (SPEC §10).
    """
    if claims_flag and stale_flag:
        raise SystemExit("pass at most one of --claims/--stale")
    root = require_notebook_root()
    fn = views.claims_view if claims_flag else views.stale_view if stale_flag else views.hot_view
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
        for f in real:
            click.echo(f"{f.level} {f.code} {f.path} — {f.message}")
        if not real:
            click.echo("ok: no findings yet")
        if expected:
            if real:
                click.echo("")
            click.echo(
                "expected until use (these appear with the work, not problems yet — "
                "don't re-run doctor for reassurance):"
            )
            for f in expected:
                click.echo(f"  {f.level} {f.code} {f.path} — {f.message}")
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


if __name__ == "__main__":  # pragma: no cover
    main()
