"""The flip CLI — one subcommand per module surface (SPEC §14).

Thin wiring only: every command resolves the enclosing notebook with
util.require_notebook_root() (so commands work from any subdirectory of a
notebook), calls exactly one library function, and prints a terse result.
All failure modes are SystemExit one-liners raised by the library. Read
commands take --json so agents can consume output without scraping.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from . import (
    claims,
    doctor as doctor_mod,
    export as export_mod,
    ledgers,
    profiles as profiles_mod,
    registry,
    scaffold,
    sessions,
    sources,
    views,
)
from .util import find_notebook_root, require_notebook_root


@click.group(name="flip")
@click.version_option(package_name="flip-notebook")
def main() -> None:
    """Reporter's notebooks: plain-file research corpora for humans and agents.

    A notebook is one directory — notebook.toml + notebook.md plus JSONL
    ledgers for sources, claims, questions, decisions, and the work log.
    Start one with `flip new <slug> --kind <profile>`; run every other
    command from anywhere inside it (flip walks up to find the root).
    `flip show` is the hot view, `flip doctor` the lint. Read commands
    accept --json for machine consumption.
    """


# ---------------------------------------------------------------- new


@main.command()
@click.argument("slug")
@click.option("--kind", default="ledger", show_default=True,
              help="Profile id (see `flip profiles`): sets required files, "
                   "notebook.md sections, and the claim-verification bar.")
@click.option("--title", default="", help="Human title; slug is used when omitted.")
@click.option("--visibility", default=None,
              type=click.Choice(["private", "internal", "client-confidential", "public"]),
              help="Override the profile's default [policy] visibility.")
@click.option("--dest", default=None, type=click.Path(path_type=Path),
              help="Directory to create the notebook in [default: ./<slug>].")
def new(slug: str, kind: str, title: str, visibility: str | None, dest: Path | None) -> None:
    """Create a notebook: manifest + notebook.md section stubs, nothing else.

    Use once per piece of research; directories (sources/, log/, analysis/)
    appear lazily as commands need them. Then cd in and start logging.
    """
    dest = dest if dest is not None else Path.cwd() / slug
    path = scaffold.create_notebook(dest, slug, kind, title=title, visibility=visibility)
    click.echo(f"created {kind} notebook '{slug}' at {path}")
    click.echo(f'next: cd {path} && flip log "started" — see `flip --help` for the toolkit')


# ---------------------------------------------------------------- sources


@main.command("add-source")
@click.argument("target")
@click.option("--kind", default=None,
              help="Source kind (web|paper|file|dataset|talk|…); inferred from the "
                   "target when omitted. Non-file kinds run the [fetchers] command "
                   "configured in $FLIP_HOME/config.toml.")
@click.option("--note", default=None, help="Capture note, recorded in provenance and ledger.")
def add_source(target: str, kind: str | None, note: str | None) -> None:
    """Capture a source: fetch/copy into sources/raw/, hash it, open a ledger row.

    Use the moment you rely on something external — URL, DOI, or local file.
    The row opens at grade "?"; judge it with `flip grade` once read.
    """
    row = sources.add_source(require_notebook_root(), target, kind=kind, note=note)
    click.echo(f"{row['id']} · {row['kind']} · {row['local']} (grade ?)")
    click.echo(f"judge it: flip grade {row['id']} --grade A|B|C "
               f"--independence original|republisher|derivative|self-interested")


@main.command()
@click.argument("source_id", metavar="SOURCE_ID")
@click.option("--grade", default=None, type=click.Choice(sources.GRADES),
              help="Reliability: A authoritative primary · B official/independent · "
                   "C vendor/synthesis · ? unjudged.")
@click.option("--independence", default=None, type=click.Choice(sources.INDEPENDENCE),
              help="Is this the original, or downstream of one?")
@click.option("--freshness", default=None, type=click.Choice(sources.FRESHNESS),
              help="fresh, or dated past the profile threshold.")
@click.option("--notes", default=None, help="Judgment notes (why this grade).")
def grade(source_id: str, grade: str | None, independence: str | None,
          freshness: str | None, notes: str | None) -> None:
    """Record source-quality judgments on a captured source (SPEC §5.4).

    Use after actually reading a source; grading gates claim verification.
    At least one option is required.
    """
    if grade is None and independence is None and freshness is None and notes is None:
        raise SystemExit(
            "nothing to record; pass at least one of --grade/--independence/--freshness/--notes"
        )
    row = sources.grade_source(require_notebook_root(), source_id, grade=grade,
                               independence=independence, freshness=freshness, notes=notes)
    click.echo(f"{row['id']} · grade {row.get('grade', '?')} · "
               f"{row.get('independence', '?')} · {row.get('freshness', '?')}")


@main.group()
def source() -> None:
    """Inspect the source ledger (sources/ledger.jsonl) without reading JSONL."""


@source.command("list")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw ledger rows as JSON.")
def source_list(as_json: bool) -> None:
    """List captured sources: id · kind · grade/independence/freshness · title-or-local.

    The quick judgment audit: any line still showing grade "?" is captured
    but unjudged — and ungraded sources never count toward verification.
    """
    rows = sources.list_sources(require_notebook_root())
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no sources captured (sources/ledger.jsonl is absent or empty)")
        return
    for r in rows:
        judgment = (f"{r.get('grade', '?')}/{r.get('independence', '?')}"
                    f"/{r.get('freshness', '?')}")
        click.echo(f"{r.get('id', '?')} · {r.get('kind', '?')} · {judgment} · "
                   f"{r.get('title') or r.get('local', '')}")


# ---------------------------------------------------------------- log ledgers


@main.command()
@click.argument("text")
def log(text: str) -> None:
    """Append one event to the work log (log/log.jsonl); actor auto-detected.

    Use for anything a future reader needs to retrace: fetched X, ran Y,
    hit wall Z. Terse; one event per line.
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
    """Record a decision in log/decisions.jsonl, allocating the next D#.

    Use at every resolved fork so nobody relitigates it: the why is the
    point. Cite the id in prose as [D3].
    """
    row = ledgers.add_decision(require_notebook_root(), question, decision, why,
                               alternatives_rejected=list(rejected) or None)
    click.echo(f"{row['id']} · {row['decision']}")


@main.command("pass")
@click.argument("text")
@click.option("--reason", required=True, help="Why it was rejected — the payload.")
@click.option("--url", default=None, help="Where the rejected thing lives, if anywhere.")
def pass_(text: str, reason: str, url: str | None) -> None:
    """Record negative evidence — considered and rejected — in log/passed.jsonl.

    Use when you rule something out, so the next pass (human or agent)
    doesn't rediscover and re-chase it.
    """
    row = ledgers.add_passed(require_notebook_root(), text, reason, url=url)
    click.echo(f"passed {row['ts']} · {row['reason']}")


@main.group()
def question() -> None:
    """Track open questions (Q#) in log/questions.jsonl.

    Add one whenever something needs an answer before the work can ship;
    `flip show` surfaces the open ones. Answering appends — history stays.
    """


@question.command("add")
@click.argument("text")
def question_add(text: str) -> None:
    """Open a question, allocating the next Q#. Cite it in prose as [Q2]."""
    row = ledgers.add_question(require_notebook_root(), text)
    click.echo(f"{row['id']} open · {row['text']}")


@question.command("answer")
@click.argument("qid", metavar="ID")
def question_answer(qid: str) -> None:
    """Mark a question answered (append-only; the ask stays in the ledger).

    Record where the answer landed with `flip log` or in notebook.md.
    """
    ledgers.answer_question(require_notebook_root(), qid)
    click.echo(f"{qid} answered")


@question.command("list")
@click.option("--json", "as_json", is_flag=True, help="Emit the rows as JSON.")
def question_list(as_json: bool) -> None:
    """List every question with its current status: id · open/answered · text.

    Open ones also surface in `flip show`; this is the full history view
    (answered questions stay listed — the ledger never forgets).
    """
    rows = ledgers.list_questions(require_notebook_root())
    if as_json:
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        click.echo("no questions recorded (log/questions.jsonl is absent or empty)")
        return
    for r in rows:
        click.echo(f"{r.get('id', '?')} · {r.get('status', 'open')} · {r.get('text', '')}")


# ---------------------------------------------------------------- claims


@main.group()
def claim() -> None:
    """The claim ledger (analysis/claims.jsonl): assertions the work relies on.

    Add a claim when the work starts leaning on an assertion; link the
    sources that back it. Verification is gated by the notebook profile's
    corroboration bar — `flip doctor` audits load-bearing claims against it.
    """


@claim.command("add")
@click.argument("text")
@click.option("--source", "source_ids", multiple=True, metavar="SOURCE_ID",
              help="Backing source id from sources/ledger.jsonl (repeatable).")
@click.option("--load-bearing", is_flag=True,
              help="The piece falls over if this claim is wrong; doctor audits these.")
@click.option("--notes", default=None, help="Caveats, e.g. 'single vendor study'.")
def claim_add(text: str, source_ids: tuple[str, ...], load_bearing: bool,
              notes: str | None) -> None:
    """Assert a claim (status "asserted"), allocating the next C#."""
    row = claims.add_claim(require_notebook_root(), text, list(source_ids),
                           load_bearing=load_bearing, notes=notes)
    srcs = ", ".join(row["sources"]) or "none"
    click.echo(f"{row['id']} asserted · sources: {srcs} · "
               f"corroboration: {row['independent_corroboration']}")


@claim.command("status")
@click.argument("claim_id", metavar="CLAIM_ID")
@click.argument("status", type=click.Choice(claims.STATUSES))
def claim_status(claim_id: str, status: str) -> None:
    """Move a claim to a new status, recomputing its corroboration count.

    "verified" is refused until the profile's bar is met (independent
    original sources, or a grade-A source where the profile allows it).
    """
    row = claims.set_claim_status(require_notebook_root(), claim_id, status)
    click.echo(f"{row['id']} → {row['status']} · "
               f"corroboration: {row['independent_corroboration']}")


@claim.command("list")
@click.option("--status", default=None, type=click.Choice(claims.STATUSES),
              help="Only claims in this status.")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw rows as JSON.")
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
                   f"{r.get('text', '')} · sources: {srcs}")


# ---------------------------------------------------------------- sessions


@main.group()
def session() -> None:
    """Session records (log/sessions/): one file per working episode.

    Start one before an LLM run or research sweep; end it with a summary so
    the reasoning chain survives as evidence (SPEC §8).
    """


@session.command("start")
@click.argument("slug")
@click.option("--model", default=None, help="Model driving the episode, e.g. 'claude-fable-5'.")
@click.option("--tools", multiple=True, help="Tool available in the episode (repeatable).")
def session_start(slug: str, model: str | None, tools: tuple[str, ...]) -> None:
    """Open log/sessions/<UTC stamp>-<slug>.md with frontmatter and stubs.

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
    """Close a session: append ended-timestamp + summary to its file.

    Pass the path printed by `session start`, or just the slug (newest
    matching session wins).
    """
    path = sessions.end_session(require_notebook_root(), slug_or_path, summary)
    click.echo(f"ended {path}")


# ---------------------------------------------------------------- views


@main.command()
@click.option("--claims", "claims_flag", is_flag=True,
              help="All claims grouped by status.")
@click.option("--stale", "stale_flag", is_flag=True,
              help="What went cold: dated sources, open questions, stuck claims.")
@click.option("--json", "as_json", is_flag=True, help="Emit the view as JSON.")
def show(claims_flag: bool, stale_flag: bool, as_json: bool) -> None:
    """Show a computed view of the notebook; default is the hot view.

    The hot view is the resume-here screen: open questions, claims needing
    work, recent log, latest session. Views are computed from the ledgers,
    never stored (SPEC §10).
    """
    if claims_flag and stale_flag:
        raise SystemExit("pass at most one of --claims/--stale")
    root = require_notebook_root()
    fn = views.claims_view if claims_flag else views.stale_view if stale_flag else views.hot_view
    out = fn(root, as_data=as_json)
    click.echo(json.dumps(out, ensure_ascii=False, indent=2) if as_json else out)


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Emit findings as JSON.")
def doctor(as_json: bool) -> None:
    """Lint the notebook against the spec and its profile; exit 1 on errors.

    Checks manifest sanity, profile minimums (WARN while status is
    active/dormant, ERROR once done/published/archived), orphan/unhashed
    sources, stale freshness, claim enums, and load-bearing claims below the
    verification bar. Run before a handoff or publish; fix ERRORs, weigh
    WARNs.
    """
    findings = doctor_mod.run_doctor(require_notebook_root())
    if as_json:
        click.echo(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    elif not findings:
        click.echo("ok: no findings")
    else:
        for f in findings:
            click.echo(f"{f.level} {f.code} {f.path} — {f.message}")
    if any(f.level == "ERROR" for f in findings):
        raise SystemExit(1)


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
        click.echo(f"{r['slug']} · {r['kind']} · {r['status']} · {r['path']}")
    skipped = len(rows) - len(good)
    tail = f" ({skipped} skipped, see stderr)" if skipped else ""
    click.echo(f"indexed {len(good)} notebook(s){tail} → {registry.flip_home() / registry.INDEX}")


@main.group()
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
    """Emit CSL JSON from the source ledger for citation managers (Zotero etc.)."""
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
    """Project the notebook as an OKF v0.1 knowledge bundle at DEST.

    Sources become references/ concepts with custody frontmatter, claims cite
    them, decisions get concept pages, and the work log renders as log.md.
    The bundle is a generated render — re-export rather than editing it.
    Design notes: docs/wiki-alignment.md.
    """
    path = export_mod.export_okf(
        require_notebook_root(), dest, include_private=include_private, announce=announce
    )
    click.echo(f"OKF bundle written to {path}")


# ---------------------------------------------------------------- profiles


@main.command("profiles")
def profiles_cmd() -> None:
    """List available notebook profiles (kinds) for `flip new --kind`.

    Shows the profiles shipped with flip plus any notebook-local overrides
    under .flip/profiles/ when run inside a notebook.
    """
    root = find_notebook_root()
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


if __name__ == "__main__":  # pragma: no cover
    main()
