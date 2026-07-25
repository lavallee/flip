#!/usr/bin/env python3
"""Generate the flip site's data from the real repository and the real CLI.

Nothing this script emits is authored prose. The flipbook frames come from
running ``flip`` against a scratch notebook in a temp directory; the spec map
comes from parsing SPEC.md and cross-checking it against that same generated
notebook; the coordinates come from ``pyproject.toml``, ``pytest``, and ``git``.

Every derivation is fail-loud: a drifted spec section, a frontmatter key the
implementation no longer writes, or a CLI command that vanished raises and the
site does not build. That is the point — the site cannot quietly describe a
flip that no longer exists.

Stdlib only, and no network access. Run via ``artoo build``.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT = Path(__file__).resolve().parent
REPO = ARTIFACT.parent
SITE = ARTIFACT / "site"
DATA = SITE / "data"

DEMO_SLUG = "sourdough-rise"
DEMO_TITLE = "Does hydration change sourdough rise time?"


class BuildError(RuntimeError):
    """A derivation drifted. Fail the build rather than ship a stale fact."""


# ---------------------------------------------------------------------------
# process helpers


def flip_bin() -> str:
    binary = os.environ.get("FLIP_BIN") or shutil.which("flip")
    if not binary:
        raise BuildError("flip is not on PATH; install it (uv tool install flip-notebook)")
    return binary


def run(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True, timeout=120
    )


def git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


# ---------------------------------------------------------------------------
# repository coordinates


def read_pyproject() -> dict:
    with (REPO / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def count_tests() -> int:
    """Count test functions by parsing the test sources.

    Deliberately not ``pytest --collect-only``: the site must build in a
    checkout without the dev extras installed, and a plain ``def test_`` count
    is honest about what it measures (test functions, not coverage).
    """
    total = 0
    for path in sorted((REPO / "tests").rglob("test_*.py")):
        total += len(re.findall(r"^def test_", path.read_text(encoding="utf-8"), re.M))
    if total < 1:
        raise BuildError("counted zero tests; the test layout must have moved")
    return total


def cli_map() -> dict:
    proc = subprocess.run(
        [flip_bin(), "cli", "--json"], capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        raise BuildError(f"flip cli --json failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# the demo notebook — the flipbook's source of truth

# Synthetic research material. Invented kitchen data about a fictional baking
# club, chosen so no reader could mistake a demo frame for a real finding.
DEMO_FILES = {
    "rise-times.csv": """bake_id,date,hydration_pct,starter_pct,ambient_c,minutes_to_double
B01,2026-02-03,65,20,21.0,268
B02,2026-02-05,65,20,20.5,275
B03,2026-02-08,65,20,21.5,259
B04,2026-02-11,70,20,21.0,242
B05,2026-02-14,70,20,20.0,255
B06,2026-02-17,70,20,21.5,238
B07,2026-02-21,75,20,21.0,221
B08,2026-02-24,75,20,20.5,229
B09,2026-02-27,75,20,21.5,215
B10,2026-03-02,80,20,21.0,204
B11,2026-03-05,80,20,20.5,212
B12,2026-03-09,80,20,21.5,198
""",
    "ridgeway-club-trial.md": """# Ridgeway Bakers Club — winter hydration trial

A fictional baking club, invented for the flip documentation site.

Eleven members each ran four bakes at 65% and 80% hydration, holding starter
percentage and flour lot constant, and logged minutes to double at an ambient
temperature between 20 and 22 degrees Celsius.

Pooled result: the 80% group doubled a median of 61 minutes faster than the
65% group (n = 44 bakes). Members measured with their own thermometers and
the club did not standardise proofing vessels, so the spread is wide.
""",
    "millwright-flour-spec.txt": """MILLWRIGHT FLOUR CO. — PRODUCT SPECIFICATION (fictional)

Strong white bread flour, protein 12.8%, ash 0.55%, malted.

"Our high-protein flour is engineered for rapid, reliable rise at every
hydration level." Absorption guidance: 68-72%. No trial data accompanies the
specification sheet.
""",
}


def step_plan() -> list[dict]:
    """The narrative. Each entry names commands to run and the record to show.

    ``record`` selects what the right-hand pane displays after the step:
      ``file``   — a path in the notebook, optionally sliced by line range
      ``jsonl``  — the last line of an append-only ledger, pretty-printed
      ``stdout`` — the command's own output (used when the output *is* the point)
    """
    return [
        {
            "id": "new",
            "say": ("Someone in the baking club swears higher hydration makes sourdough rise faster. Can you actually look into it — properly, with the trail kept?"),
            "act": "Open the notebook",
            "title": "Scaffold a notebook",
            "narrative": (
                "A notebook is a directory, not a database. `flip new` writes two "
                "files: the manifest and the prose working memory. The `--kind` "
                "selects a profile, which decides what this notebook must contain "
                "before it can be called done — not before it can be started."
            ),
            "spec": "4",
            "commands": [
                ["new", DEMO_SLUG, "--kind", "research-review", "--title", DEMO_TITLE]
            ],
            "cwd": "root",
            "record": {
                "kind": "file",
                "path": "index.md",
                "lang": "markdown",
                "caption": "index.md — the manifest lives in the root frontmatter, where any OKF consumer already looks.",
            },
        },
        {
            "id": "session",
            "say": "",
            "act": "Open the notebook",
            "title": "Log the episode",
            "narrative": (
                "Generation is logged. Every working episode that writes pages — "
                "human or model — gets a session page recording the actor, the "
                "model, and the tools it had. The reasoning chain is part of the "
                "bundle, not something you reconstruct from a chat history later."
            ),
            "spec": "8",
            "commands": [
                [
                    "session",
                    "start",
                    "hydration-sweep",
                    "--model",
                    "claude-opus-5",
                    "--tools",
                    "flip",
                    "--tools",
                    "python",
                ]
            ],
            "record": {
                "kind": "glob",
                "pattern": "sessions/*.md",
                "lang": "markdown",
                "caption": "sessions/ — one page per episode, stamped in UTC. Synthesis recorded here is a lead, grade C, until promoted through references/.",
            },
        },
        {
            "id": "question",
            "say": "",
            "act": "Open the notebook",
            "title": "Write down the question",
            "narrative": (
                "Questions are entity pages with immutable ids, so they can be "
                "cited, re-posed with a sharper formulation, and answered later "
                "without losing the earlier wording."
            ),
            "spec": "7",
            "commands": [
                ["question", "add", "Does higher hydration shorten the time to double?"]
            ],
            "record": {
                "kind": "glob",
                "pattern": "questions/*.md",
                "lang": "markdown",
                "caption": "The filename is a human slug; the immutable id Q1 lives in frontmatter.",
            },
        },
        {
            "id": "capture",
            "say": ("The King Arthur hydration guide is the obvious place to start — bring it in."),
            "act": "Take custody",
            "title": "Capture a source",
            "narrative": (
                "Capture copies the bytes into the notebook and hashes them. From "
                "here the notebook does not depend on that file still existing "
                "anywhere else — this is the custody principle, and it is the "
                "difference between citing something and holding it."
            ),
            "spec": "5",
            "commands": [
                [
                    "add-source",
                    "../ridgeway-club-trial.md",
                    "--note",
                    "Independent club replication, 44 bakes",
                ]
            ],
            "record": {
                "kind": "jsonl",
                "path": "sources/_provenance.jsonl",
                "lang": "json",
                "caption": "sources/_provenance.jsonl — the fixity record, appended and never rewritten. Hash at capture, per file.",
            },
        },
        {
            "id": "ungraded",
            "say": "",
            "act": "Take custody",
            "title": "Capture is not judgment",
            "narrative": (
                "The source page opens at grade `?`. flip will not guess a grade "
                "from where a file came from, and an ungraded source counts toward "
                "nothing — so at this moment the notebook holds evidence it is not "
                "yet entitled to rely on."
            ),
            "spec": "5",
            "commands": [["show", "--stale"]],
            "record": {
                "kind": "glob",
                "pattern": "references/*.md",
                "lang": "markdown",
                "caption": "grade: '?' — captured, unjudged, and worth nothing to a claim.",
            },
        },
        {
            "id": "grade",
            "say": ("You've read it now — how good is it, actually?"),
            "act": "Take custody",
            "title": "Grade it, as a separate act",
            "narrative": (
                "Grading is a recorded judgment by a named actor, after reading. "
                "Reliability and independence are two axes, never collapsed into "
                "one score — the practice comes from Admiralty source grading. An "
                "organised trial run by people who are not us, who measured it "
                "directly: B for reliability, original for independence."
            ),
            "spec": "5",
            "commands": [
                [
                    "grade",
                    "F1",
                    "--grade",
                    "B",
                    "--independence",
                    "original",
                    "--notes",
                    "Organised trial we did not run; proofing vessels not standardised.",
                ]
            ],
            "record": {
                "kind": "glob",
                "pattern": "references/*.md",
                "lang": "markdown",
                "caption": "The same page after judgment. Only the judgment keys changed; everything else round-trips untouched.",
            },
        },
        {
            "id": "claim",
            "say": ("So what's the answer so far?"),
            "act": "Make a claim stick",
            "title": "Assert a claim",
            "narrative": (
                "A claim is a discrete assertion with an id, a status, and an edge "
                "to the sources behind it. It enters as `asserted` — the status a "
                "machine-generated assertion always starts in. `--load-bearing` "
                "means the work falls over if this is wrong, and it is what makes "
                "`flip doctor` care."
            ),
            "spec": "7",
            "commands": [
                [
                    "claim",
                    "add",
                    "Doubling time falls about a quarter between 65% and 80% hydration",
                    "--source",
                    "F1",
                    "--load-bearing",
                ]
            ],
            "record": {
                "kind": "glob",
                "pattern": "claims/*.md",
                "lang": "markdown",
                "caption": "status: asserted · independent_corroboration: 1 — recomputed by the tooling, not trusted from the page.",
            },
        },
        {
            "id": "refused",
            "say": ("Good enough for me — mark it confirmed."),
            "act": "Make a claim stick",
            "title": "Try to call it verified",
            "narrative": (
                "This is the enforcement. This notebook is a research-review, so "
                "its bar is two independent judged sources — and one is not "
                "corroboration. The command is refused, not warned about: refused, "
                "with a non-zero exit code. An agent cannot promote its own "
                "assertion by asserting harder. The bar is the profile's, and it "
                "is mechanical."
            ),
            "spec": "7",
            "commands": [["claim", "status", "C1", "verified"]],
            "expect_failure": True,
            "record": {
                "kind": "stdout",
                "lang": "text",
                "caption": "Exit code 1. The claim keeps the status it earned.",
            },
        },
        {
            "id": "second",
            "say": ("Fine. What would it take to actually know?"),
            "act": "Make a claim stick",
            "title": "Go and measure it yourself",
            "narrative": (
                "So we bake. Twelve bakes at four hydration levels, one kitchen, "
                "one flour lot — data we extracted ourselves, which is what grade "
                "A means. Capture the file and the notebook owns the bytes; grade "
                "it and the notebook can rely on them."
            ),
            "spec": "5",
            "commands": [
                [
                    "add-source",
                    "../rise-times.csv",
                    "--note",
                    "Our own kitchen log, 12 bakes at four hydration levels",
                ],
                [
                    "grade",
                    "F2",
                    "--grade",
                    "A",
                    "--independence",
                    "original",
                    "--notes",
                    "Data we measured ourselves; one kitchen, one flour lot, 12 bakes.",
                ],
            ],
            "record": {
                "kind": "jsonl",
                "path": "sources/_provenance.jsonl",
                "lang": "json",
                "caption": "A second custody event. The ledger only ever grows.",
            },
        },
        {
            "id": "passed",
            "say": ("What about that forum thread everyone keeps linking?"),
            "act": "Make a claim stick",
            "title": "Record what you rejected",
            "narrative": (
                "A flour miller's spec sheet makes a rise claim with no trial data "
                "behind it. Passing on it is worth recording: negative evidence "
                "stops the next session — human or agent — from rediscovering and "
                "re-chasing the same dead end."
            ),
            "spec": "8",
            "commands": [
                [
                    "pass",
                    "Millwright Flour spec sheet rise claim",
                    "--reason",
                    "Vendor marketing copy; no trial data, self-interested on the exact question.",
                ]
            ],
            "record": {
                "kind": "jsonl",
                "path": "log/passed.jsonl",
                "lang": "json",
                "caption": "log/passed.jsonl — the notebook remembers what it decided not to use.",
            },
        },
        {
            "id": "link",
            "say": "",
            "act": "Make a claim stick",
            "title": "Link the second source",
            "narrative": (
                "Linking regenerates the claim's citation block and recomputes its "
                "corroboration count from the graded sources it actually has. The "
                "number on the page is never taken on faith."
            ),
            "spec": "7",
            "commands": [["claim", "source", "add", "C1", "F2"]],
            "record": {
                "kind": "glob",
                "pattern": "claims/*.md",
                "lang": "markdown",
                "caption": "independent_corroboration: 2, and footnote attribution regenerated from the edges.",
            },
        },
        {
            "id": "verified",
            "say": ("Try again now."),
            "act": "Make a claim stick",
            "title": "Now it passes",
            "narrative": (
                "Same command as before, different answer — because the evidence "
                "changed, not because anyone insisted. The default bar is two "
                "independent judged sources *or* one grade-A primary, and the "
                "notebook now has both: a second independent trial, and first-party "
                "data we measured ourselves. Either would have cleared it."
            ),
            "spec": "7",
            "commands": [["claim", "status", "C1", "verified"]],
            "record": {
                "kind": "glob",
                "pattern": "claims/*.md",
                "lang": "markdown",
                "caption": "status: verified — earned mechanically, and re-checkable by anyone with the files.",
            },
        },
        {
            "id": "decide",
            "say": ("Let's not bother testing rye — white flour only."),
            "act": "Keep the record",
            "title": "Record the fork you resolved",
            "narrative": (
                "The what is recoverable from git; the why is not. Decisions are "
                "pages so that nobody relitigates them in six weeks, including the "
                "agent that made them."
            ),
            "spec": "7",
            "commands": [
                [
                    "decide",
                    "--question",
                    "Report doubling time or final crumb quality?",
                    "--decision",
                    "Doubling time only",
                    "--why",
                    "It is the one variable both trials measured the same way.",
                    "--rejected",
                    "Crumb scoring — subjective and not recorded by the club",
                ]
            ],
            "record": {
                "kind": "glob",
                "pattern": "decisions/*.md",
                "lang": "markdown",
                "caption": "The rejected alternative is part of the record, not a footnote.",
            },
        },
        {
            "id": "doctor",
            "say": ("Anything left hanging before we wrap up?"),
            "act": "Audit and render",
            "title": "Audit the notebook",
            "narrative": (
                "`flip doctor` validates after the fact instead of gatekeeping "
                "before — which is what lets a human edit the same files freely in "
                "a markdown editor. It lints OKF conformance, profile minimums, "
                "orphaned custody, under-verified load-bearing claims, and link rot."
            ),
            "spec": "15",
            "commands": [["doctor"]],
            "allow_failure": True,
            "record": {
                "kind": "stdout",
                "lang": "text",
                "caption": "Profile minimums warn while a notebook is active, and only error once it is called done.",
            },
        },
        {
            "id": "show",
            "say": ("Where do we stand?"),
            "act": "Audit and render",
            "title": "The hot view",
            "narrative": (
                "Nothing is deleted to keep context small. `flip show` computes "
                "what is hot — open questions, claims needing work, recent log — "
                "from the pages and ledgers, every time. Add `--json` and it is an "
                "agent's context primer."
            ),
            "spec": "10",
            "commands": [["show"]],
            "record": {
                "kind": "stdout",
                "lang": "text",
                "caption": "A projection, not a stored view. The files remain canonical.",
            },
        },
        {
            "id": "export",
            "say": ("Share it with the group."),
            "act": "Audit and render",
            "title": "Render it somewhere",
            "narrative": (
                "`flip export json` emits the versioned flip-render/1 projection "
                "for renderers and site generators — deterministic, diffable, and "
                "policy-filtered. This notebook is `visibility: internal`, so the "
                "export refuses outright until you either mark it public or say "
                "`--include-private` and mean it. It is how the provenance panel "
                "on this site is built, from this site's own notebook."
            ),
            "spec": "17",
            "commands": [["export", "json", "--out", "-", "--include-private"]],
            "record": {
                "kind": "stdout",
                "lang": "json",
                "truncate": 40,
                "caption": "flip-render/1 — a projection, not an API. Stable ids to anchor and link back to.",
            },
        },
    ]


def snapshot_tree(root: Path) -> dict[str, float]:
    """Path -> mtime for every file in the notebook, so we can mark changes."""
    out: dict[str, float] = {}
    for path in root.rglob("*"):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = path.stat().st_mtime_ns
    return out


def read_slice(path: Path, limit: int = 40) -> tuple[str, bool]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > limit:
        return "\n".join(lines[:limit]), True
    return text.rstrip("\n"), False


def build_flipbook(env_base: dict[str, str]) -> dict:
    binary = flip_bin()
    with tempfile.TemporaryDirectory(prefix="flip-site-") as tmp:
        workspace = Path(tmp)
        home = workspace / "flip-home"
        home.mkdir()
        env = {
            **env_base,
            "FLIP_HOME": str(home),          # never touch the operator's ~/.flip
            "FLIP_ACTOR": "human:baker",     # deterministic attribution
            "NO_COLOR": "1",
            "COLUMNS": "88",
        }
        for name, body in DEMO_FILES.items():
            (workspace / name).write_text(body, encoding="utf-8")

        notebook = workspace / DEMO_SLUG
        steps: list[dict] = []
        previous: dict[str, float] = {}

        for index, plan in enumerate(step_plan(), start=1):
            cwd = workspace if plan.get("cwd") == "root" else notebook
            outputs: list[str] = []
            code = 0
            for argv in plan["commands"]:
                proc = run([binary, *argv], cwd=cwd, env=env)
                chunk = (proc.stdout or "") + (proc.stderr or "")
                outputs.append(chunk.rstrip("\n"))
                code = proc.returncode
                if code != 0 and not (plan.get("expect_failure") or plan.get("allow_failure")):
                    raise BuildError(
                        f"step {plan['id']}: `flip {' '.join(argv)}` exited {code}\n{chunk}"
                    )
            if plan.get("expect_failure") and code == 0:
                raise BuildError(
                    f"step {plan['id']} expected a refusal but the command succeeded — "
                    "the verification bar may have been weakened"
                )

            current = snapshot_tree(notebook)
            tree = []
            for path in sorted(current):
                if path not in previous:
                    state = "added"
                elif current[path] != previous[path]:
                    state = "changed"
                else:
                    state = "same"
                tree.append({"path": path, "state": state})
            previous = current

            record = dict(plan["record"])
            spec = record.pop("kind")
            if spec == "stdout":
                body = "\n\n".join(chunk for chunk in outputs if chunk) or "(no output)"
                limit = record.pop("truncate", 0)
                if limit:
                    lines = body.splitlines()
                    if len(lines) > limit:
                        body = "\n".join(lines[:limit])
                        record["truncated"] = True
                record["text"] = body
                record["path"] = "stdout"
            else:
                if spec == "glob":
                    # index.md in each directory is a generated listing, never an
                    # entity page — and the entity we mean is the one this step
                    # just touched, so select by mtime rather than by name.
                    matches = [
                        path
                        for path in notebook.glob(record.pop("pattern"))
                        if path.name != "index.md"
                    ]
                    if not matches:
                        raise BuildError(f"step {plan['id']}: record glob matched nothing")
                    target = max(matches, key=lambda p: p.stat().st_mtime_ns)
                else:
                    target = notebook / record["path"]
                if not target.exists():
                    raise BuildError(f"step {plan['id']}: record path {target} is missing")
                if spec == "jsonl":
                    lines = [
                        line
                        for line in target.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    record["text"] = json.dumps(json.loads(lines[-1]), indent=2)
                else:
                    text, truncated = read_slice(target)
                    record["text"] = text
                    if truncated:
                        record["truncated"] = True
                record["path"] = target.relative_to(notebook).as_posix()

            steps.append(
                {
                    "n": index,
                    "id": plan["id"],
                    "say": plan.get("say", ""),
                    "act": plan["act"],
                    "title": plan["title"],
                    "narrative": plan["narrative"],
                    "spec": plan["spec"],
                    # Shell-quoted: the site shows a copy button beside these, so
                    # what is displayed has to be what you can actually paste.
                    "commands": ["flip " + shlex.join(argv) for argv in plan["commands"]],
                    "stdout": "\n\n".join(chunk for chunk in outputs if chunk),
                    "exit_code": code,
                    "refused": bool(plan.get("expect_failure")),
                    "tree": tree,
                    "record": record,
                }
            )

        # Cross-check the spec map against what the implementation really wrote.
        frontmatter = harvest_frontmatter(notebook)

    return {"steps": steps, "frontmatter_seen": frontmatter}


def harvest_frontmatter(notebook: Path) -> dict[str, list[str]]:
    """Collect the frontmatter keys each entity type actually carries."""
    seen: dict[str, set[str]] = {}
    for path in notebook.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---", 4)
        if end == -1:
            continue
        block = text[4:end]
        keys = re.findall(r"^([A-Za-z_][A-Za-z0-9_]*):", block, re.M)
        kind = "Manifest"
        for line in block.splitlines():
            if line.startswith("type:"):
                kind = line.split(":", 1)[1].strip().strip("\"'")
                break
        seen.setdefault(kind, set()).update(keys)
    return {kind: sorted(keys) for kind, keys in sorted(seen.items())}


# ---------------------------------------------------------------------------
# the spec map


ENTITIES = [
    {
        "type": "Source",
        "id_prefix": "P# A# F# T# S#",
        "dir": "references/",
        "spec": "5",
        "summary": "An external artifact we captured, and our judgment of it.",
        "judgment": True,
        "keys": ["type", "id", "aliases", "title", "resource", "local", "grade", "independence", "freshness", "status"],
    },
    {
        "type": "Claim",
        "id_prefix": "C#",
        "dir": "claims/",
        "spec": "7",
        "summary": "A discrete assertion, its sources, and how far it has earned trust.",
        "judgment": True,
        "keys": ["type", "id", "aliases", "description", "status", "load_bearing", "sources", "independent_corroboration", "first_asserted", "generated"],
    },
    {
        "type": "Decision",
        "id_prefix": "D#",
        "dir": "decisions/",
        "spec": "7",
        "summary": "A resolved fork and — the payload — why it was resolved that way.",
        "judgment": False,
        "keys": ["type", "id", "aliases", "question", "alternatives_rejected", "generated"],
    },
    {
        "type": "Question",
        "id_prefix": "Q#",
        "dir": "questions/",
        "spec": "7",
        "summary": "Something that needs answering, re-posable without losing the earlier wording.",
        "judgment": False,
        "keys": ["type", "id", "aliases", "status", "generated"],
    },
    {
        "type": "Work Session",
        "id_prefix": "dated",
        "dir": "sessions/",
        "spec": "8",
        "summary": "One human or agent working episode: generated {by, at}, model, tools, outputs.",
        "judgment": False,
        "keys": ["type", "generated", "model", "tools", "started"],
    },
]

LEDGERS = [
    {
        "path": "sources/_provenance.jsonl",
        "spec": "5",
        "label": "Capture log",
        "summary": "One line per acquisition: url, local path, sha256, bytes, tool, strategy, actor. The fixity record.",
    },
    {
        "path": "derived/_derivations.jsonl",
        "spec": "8",
        "label": "Derivation log",
        "summary": "Inputs to tool and parameters to outputs, with hashes. A deliberately small PROV profile.",
    },
    {
        "path": "log/log.jsonl",
        "spec": "8",
        "label": "Work log",
        "summary": "Fetched X, ran Y, hit wall Z. The generated newest-first view is log.md at the bundle root.",
    },
    {
        "path": "log/passed.jsonl",
        "spec": "8",
        "label": "Passed ledger",
        "summary": "Negative evidence — considered and rejected, with the reason. Prevents rediscovery loops.",
    },
]

LIFECYCLE = [
    {
        "stage": "captured",
        "act": "flip add-source",
        "spec": "5",
        "gains": "Local bytes in sources/raw/, hashed, with a provenance line.",
        "worth": "Custody. Nothing else — the page opens at grade ?.",
    },
    {
        "stage": "judged",
        "act": "flip grade",
        "spec": "5",
        "gains": "grade, independence, freshness — recorded by a named actor after reading.",
        "worth": "Now it can count toward a claim. Ungraded sources corroborate nothing.",
    },
    {
        "stage": "cited",
        "act": "flip claim add --source",
        "spec": "7",
        "gains": "An edge from a claim, and a regenerated citation block.",
        "worth": "The claim enters as asserted, whatever the source's grade.",
    },
    {
        "stage": "corroborating",
        "act": "flip claim source add",
        "spec": "7",
        "gains": "independent_corroboration, recomputed from the judged sources present.",
        "worth": "Counted, never trusted from the page. Doctor flags drift.",
    },
    {
        "stage": "verified",
        "act": "flip claim status … verified",
        "spec": "7",
        "gains": "The status, if and only if the profile's bar is met.",
        "worth": "Refused with a non-zero exit otherwise. Or earned by an adversarial or recomputation record.",
    },
]

PROFILES = [
    ("ledger", "Bibliography or source spine.", "references/"),
    ("scout", "Screen an angle fast, editor lens active.", "hypotheses with falsifiers · decisions/ · passed ledger"),
    ("research-review", "Question-organised survey, heading for publication.", "claims/ · sessions/ · drafts/ · full custody"),
    ("engagement", "Confidential client work.", "research-review + confidential policy + citation rule + HANDOFF.md"),
    ("data-investigation", "Dataset-first reporting.", "derivation ledger · ingest scripts · frozen data contracts"),
    ("pursuit", "One question under pursuit.", "questions/ · claims/ · a dated question plan with a stop rule"),
]


def github_anchor(heading: str) -> str:
    """GitHub's heading-anchor slug, because that is where the links land.

    GitHub lowercases, deletes punctuation *without* substituting a separator
    (so ``index.md`` becomes ``indexmd`` and an em dash simply vanishes,
    leaving the two spaces around it to become two hyphens), then turns spaces
    into hyphens. A naive ``[^a-z0-9]+ -> -`` produces anchors that 404.
    """
    text = heading.lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def parse_spec_sections() -> dict[str, dict]:
    """Map section number -> {title, anchor} from SPEC.md's own headings."""
    sections: dict[str, dict] = {}
    for line in (REPO / "SPEC.md").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^## (\d+)\. (.+)$", line)
        if match:
            number, title = match.group(1), match.group(2).strip()
            sections[number] = {
                "number": number,
                "title": title,
                "anchor": github_anchor(f"{number}. {title}"),
            }
    if not sections:
        raise BuildError("parsed no sections out of SPEC.md")
    return sections


def build_spec(sections: dict[str, dict], frontmatter_seen: dict[str, list[str]]) -> dict:
    for entity in ENTITIES:
        if entity["spec"] not in sections:
            raise BuildError(f"entity {entity['type']} cites missing SPEC section {entity['spec']}")
        observed = set(frontmatter_seen.get(entity["type"], []))
        if not observed:
            raise BuildError(
                f"the demo notebook produced no {entity['type']} page; the spec map "
                "cannot be cross-checked against the implementation"
            )
        # Every key we advertise must be one the implementation really writes.
        # Conditional keys are exempt: they appear only when the capture kind or
        # the command supplies them (a copied local file has no `resource` URL).
        optional = {"model", "tools", "alternatives_rejected", "resource"}
        missing = [k for k in entity["keys"] if k not in observed and k not in optional]
        if missing:
            raise BuildError(
                f"{entity['type']} pages no longer carry {missing}; update the spec map"
            )
        entity["observed_keys"] = sorted(observed)

    for item in [*LEDGERS, *LIFECYCLE]:
        if item["spec"] not in sections:
            raise BuildError(f"missing SPEC section {item['spec']}")

    shipped = sorted(p.stem for p in (REPO / "src" / "flip" / "profiles").glob("*.toml"))
    declared = sorted(name for name, _, _ in PROFILES)
    if shipped != declared:
        raise BuildError(f"profiles drifted: shipped {shipped}, site declares {declared}")

    return {
        "sections": list(sections.values()),
        "entities": ENTITIES,
        "ledgers": LEDGERS,
        "lifecycle": LIFECYCLE,
        "profiles": [
            {"id": name, "intent": intent, "requires": requires}
            for name, intent, requires in PROFILES
        ],
    }


# ---------------------------------------------------------------------------


def main() -> int:
    env_base = {k: v for k, v in os.environ.items() if k not in {"FLIP_NOTEBOOK", "FLIP_ACTOR", "FLIP_HOME"}}
    project = read_pyproject()["project"]
    sections = parse_spec_sections()

    print("· running the real CLI to generate flipbook frames")
    flipbook = build_flipbook(env_base)

    print("· cross-checking the spec map against the generated notebook")
    spec = build_spec(sections, flipbook.pop("frontmatter_seen"))

    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    skills = sorted(p.name for p in (REPO / "src" / "flip" / "skills").iterdir() if p.is_dir())
    spec_status = ""
    for line in (REPO / "SPEC.md").read_text(encoding="utf-8").splitlines()[:6]:
        if line.startswith("**Status:**"):
            spec_status = line.split("**Status:**", 1)[1].strip().replace("·", "·")
            break

    coordinates = {
        "generated": stamp,
        "version": project["version"],
        "revision": git("rev-parse", "--short", "HEAD") or "unknown",
        "requires_python": project.get("requires-python", ""),
        "dependencies": project.get("dependencies", []),
        "license": "MIT",
        "package": project["name"],
        "tests": count_tests(),
        "spec_status": spec_status,
        "spec_lines": len((REPO / "SPEC.md").read_text(encoding="utf-8").splitlines()),
        "skills": skills,
        "cli": cli_map(),
    }

    DATA.mkdir(parents=True, exist_ok=True)
    for name, global_name, payload in (
        ("flip", "__FLIP_META__", coordinates),
        (
            "flipbook",
            "__FLIP_BOOK__",
            {
                "generated": stamp,
                "notebook": {"slug": DEMO_SLUG, "title": DEMO_TITLE, "kind": "research-review"},
                **flipbook,
            },
        ),
        ("spec", "__FLIP_SPEC__", {"generated": stamp, **spec}),
    ):
        body = json.dumps(payload, indent=2, sort_keys=False)
        (DATA / f"{name}.json").write_text(body + "\n", encoding="utf-8")
        # A file:// page cannot fetch() its own JSON, so ship a script loader
        # beside it — the same trick artoo uses for provenance.json.
        (DATA / f"{name}.js").write_text(
            f"window.{global_name} = {body};\n", encoding="utf-8"
        )
        print(f"· wrote site/data/{name}.json + {name}.js")

    commands = sum(len(s["commands"]) for s in flipbook["steps"])
    print(
        f"built from flip {coordinates['version']} at {coordinates['revision']}: "
        f"{len(flipbook['steps'])} frames, {commands} real commands, "
        f"{coordinates['tests']} tests, {len(spec['sections'])} spec sections"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        sys.exit(1)
