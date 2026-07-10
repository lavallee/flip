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

import json
import re
from dataclasses import asdict
from pathlib import Path

import click

from . import (
    beat as beat_mod,
    claims,
    doctor as doctor_mod,
    export as export_mod,
    ledgers,
    migrate as migrate_mod,
    obsidian as obsidian_mod,
    pages,
    profiles as profiles_mod,
    registry,
    rename as rename_mod,
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

    A notebook is one directory and a conformant OKF knowledge bundle: the
    manifest lives in the root index.md frontmatter, notebook.md is the
    working memory, and every source, claim, decision, question, and session
    is one markdown page with YAML frontmatter (references/, claims/,
    decisions/, questions/, sessions/) — ids like A3/C7 resolve via
    `flip open`. Event history is append-only JSONL under log/ and sources/.
    Start with `flip new <slug> --kind <profile>`; run every other command
    from anywhere inside the notebook (flip walks up to find the root).
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
              help="Override the profile's default visibility policy.")
@click.option("--dest", default=None, type=click.Path(path_type=Path),
              help="Directory to create the notebook in [default: ./<slug>].")
def new(slug: str, kind: str, title: str, visibility: str | None, dest: Path | None) -> None:
    """Create a notebook: index.md manifest + notebook.md stubs, nothing else.

    Use once per piece of research; entity directories (references/, claims/,
    log/, …) appear lazily as commands need them. Then cd in and start logging.
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
@click.option("--note", default=None, help="Capture note, recorded in provenance and on the page.")
def add_source(target: str, kind: str | None, note: str | None) -> None:
    """Capture a source: fetch/copy into sources/raw/, hash it, open a page.

    Use the moment you rely on something external — URL, DOI, or local file.
    The references/ page opens at grade "?"; judge it with `flip grade` once
    read — ungraded sources never count toward claim verification.
    """
    root = require_notebook_root()
    page = sources.add_source(root, target, kind=kind, note=note)
    rel = page.path.relative_to(root).as_posix()
    click.echo(f"{page.id} · {page.fm.get('local', '')} · {rel} (grade ?)")
    click.echo(f"judge it: flip grade {page.id} --grade A|B|C "
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
    """Record source-quality judgments on a source's page (SPEC §5.4).

    Use after actually reading a source; grading gates claim verification.
    Only the judgment keys change — the rest of the page round-trips.
    At least one option is required.
    """
    if grade is None and independence is None and freshness is None and notes is None:
        raise SystemExit(
            "nothing to record; pass at least one of --grade/--independence/--freshness/--notes"
        )
    page = sources.grade_source(require_notebook_root(), source_id, grade=grade,
                                independence=independence, freshness=freshness, notes=notes)
    click.echo(f"{page.id} · grade {page.fm.get('grade', '?')} · "
               f"{page.fm.get('independence', '?')} · {page.fm.get('freshness', '?')}")


@main.group()
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
def pass_(text: str, reason: str, url: str | None) -> None:
    """Record negative evidence — considered and rejected — in log/passed.jsonl.

    Use when you rule something out, so the next pass (human or agent)
    doesn't rediscover and re-chase it.
    """
    row = ledgers.add_passed(require_notebook_root(), text, reason, url=url)
    click.echo(f"passed {row['ts']} · {row['reason']}")


@main.group()
def question() -> None:
    """Track questions as pages (questions/<slug>.md, ids Q#).

    Add one whenever something needs an answer before the work can ship;
    `flip show` surfaces the open ones. Answering updates the page in
    place — history stays in git, and the Q# is never reused.
    """


@question.command("add")
@click.argument("text")
def question_add(text: str) -> None:
    """Open a question, allocating the next Q#. Cite it in prose as [Q2]."""
    page = ledgers.add_question(require_notebook_root(), text)
    click.echo(f"{page.id} open · {page.fm.get('description', '')}")


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


@main.group()
def claim() -> None:
    """Claims as pages (claims/<slug>.md, ids C#): assertions the work relies on.

    Add a claim when the work starts leaning on an assertion; link the
    source ids that back it (its page gets a generated # Citations block).
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
def claim_add(text: str, source_ids: tuple[str, ...], load_bearing: bool,
              notes: str | None) -> None:
    """Assert a claim (status "asserted"), allocating the next C#."""
    page = claims.add_claim(require_notebook_root(), text, list(source_ids),
                            load_bearing=load_bearing, notes=notes)
    srcs = ", ".join(page.fm.get("sources") or []) or "none"
    click.echo(f"{page.id} asserted · sources: {srcs} · "
               f"corroboration: {page.fm.get('independent_corroboration', 0)}")


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


# ---------------------------------------------------------------- sessions


@main.group()
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
@click.argument("entity_id", metavar="ID")
def open_(entity_id: str) -> None:
    """Resolve a compact id (A3, C7, D2, Q4…) to its entity page path.

    Ids are immutable frontmatter; filenames are human slugs (SPEC §9), so
    this is how a bare [A3] cite becomes a file. Prints the absolute path —
    compose it: `$EDITOR $(flip open A3)`.
    """
    root = require_notebook_root()
    page = pages.find_by_id(root, entity_id)
    if page is None:
        known = sorted(
            {p.id for d in pages.SCAN_DIRS for p in pages.iter_pages(root, d) if p.id},
            key=lambda s: (s.rstrip("0123456789"), len(s), s),
        )
        hint = f"known ids: {', '.join(known)}" if known else "no entity pages yet"
        raise SystemExit(f"no page with id '{entity_id}' ({hint})")
    click.echo(str(page.path))


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
def doctor(as_json: bool) -> None:
    """Lint the notebook against the spec and its profile; exit 1 on errors.

    Checks manifest sanity, OKF conformance (frontmatter + type on every
    page), id/alias integrity, dangling citations, profile minimums (WARN
    while status is active/dormant, ERROR once done/published/archived),
    orphan custody, stale freshness, and claims below the verification bar.
    Run before a handoff or publish; fix ERRORs, weigh WARNs.
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
    root = find_notebook_root() or beat_mod.find_beat_root()
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


@main.command()
def migrate() -> None:
    """Convert a v0.3 notebook (notebook.toml + JSONL entity ledgers) to v0.4.

    In place: the manifest moves into the root index.md frontmatter and every
    source/claim/decision/question/session becomes an entity page, preserving
    ids and fields. Event ledgers (log/, provenance) and sources/raw/ stay as
    they are. Resumable if interrupted; run `flip doctor` afterwards.
    """
    cwd = Path.cwd().resolve()
    root = next(
        (c for c in (cwd, *cwd.parents) if (c / migrate_mod.NOTEBOOK_TOML).is_file()), None
    )
    if root is None:
        # No v0.3 root above us: let migrate explain (already-v0.4 vs not a notebook).
        root = find_notebook_root() or cwd
    counts = migrate_mod.migrate(root)
    summary = ", ".join(
        f"{n} {name.replace('_', ' ')}"
        for name, n in counts.items()
        if n or name != "already_migrated"  # mention skips only when they happened
    )
    click.echo(f"migrated {root} to v0.4 · {summary}")
    click.echo("entity pages: references/ claims/ decisions/ questions/ sessions/ — "
               "run `flip doctor` to audit the result")


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


# ---------------------------------------------------------------- beat


@main.group(name="beat")
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


@beat.group("thread")
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


if __name__ == "__main__":  # pragma: no cover
    main()
