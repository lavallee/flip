#!/usr/bin/env python3
"""Install the built wheel in isolation and exercise the public first-run path."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def run(command: list[str | Path], *, cwd: Path | None = None, env: dict | None = None) -> str:
    rendered = [str(part) for part in command]
    result = subprocess.run(
        rendered,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        detail = result.stdout.rstrip()
        raise SystemExit(
            f"release smoke failed ({result.returncode}): {' '.join(rendered)}"
            + (f"\n{detail}" if detail else "")
        )
    return result.stdout


def executable(venv_dir: Path, name: str) -> Path:
    scripts = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    candidate = scripts / (f"{name}.exe" if os.name == "nt" else name)
    if not candidate.is_file():
        raise SystemExit(f"installed wheel did not provide {name}: expected {candidate}")
    return candidate


def select_wheel(argument: str | None) -> Path:
    if argument:
        wheel = Path(argument).resolve()
        if not wheel.is_file():
            raise SystemExit(f"wheel does not exist: {wheel}")
        return wheel
    wheels = sorted((Path.cwd() / "dist").glob("flip_notebook-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(
            "expected exactly one dist/flip_notebook-*.whl; clean dist or pass a wheel path"
        )
    return wheels[0].resolve()


def check_resources(python: Path) -> None:
    code = r"""
from importlib.resources import files

root = files("flip")
required = [
    "profiles/pursuit.toml",
    "profiles/research-review.toml",
    "kinds_builtin/lit-review.toml",
    "disciplines_builtin/lineage.toml",
    "workflows_builtin/weekly-watch.toml",
    "skills/notebook-create/SKILL.md",
    "skills/notebook-source/SKILL.md",
    "skills/notebook-source/references/plugins.md",
    "skills/notebook-workflow-author/SKILL.md",
    "skills/notebook-plugin-author/SKILL.md",
    "obsidian_plugin/manifest.json",
    "obsidian_plugin/main.js",
    "spindle-package.toml",
]
missing = [path for path in required if not root.joinpath(*path.split("/")).is_file()]
if missing:
    raise SystemExit("wheel is missing package resources: " + ", ".join(missing))
"""
    run([python, "-c", code])


def smoke(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="flip-release-smoke-") as temp:
        base = Path(temp)
        venv_dir = base / "venv"
        # Programmatic EnvBuilder defaults to copying the interpreter on Unix.
        # A uv-managed Python is relocatable through its original path but not
        # as a copied binary (its compiled fallback prefix is /install), so the
        # copy cannot even import encodings. `python -m venv` uses symlinks on
        # Unix; mirror that platform default here. Windows requires copies.
        venv.EnvBuilder(
            with_pip=True,
            clear=True,
            symlinks=os.name != "nt",
        ).create(venv_dir)
        python = executable(venv_dir, "python")
        run([python, "-m", "pip", "install", "--disable-pip-version-check", wheel])

        flip = executable(venv_dir, "flip")
        flip_fetch = executable(venv_dir, "flip-fetch")
        version = run([flip, "--version"]).strip()
        run([flip_fetch, "--help"])
        check_resources(python)

        work = base / "work"
        work.mkdir()
        fixture = work / "districts.csv"
        fixture.write_text("district,enrollment\nNorth,100\n", encoding="utf-8")
        notebook = work / "enrollment-check"
        env = os.environ.copy()
        env["FLIP_HOME"] = str(base / "flip-home")
        env["FLIP_ACTOR"] = "agent:release-smoke"

        run([flip, "config", "init"], cwd=work, env=env)
        created = run(
            [
                flip,
                "new",
                "enrollment-check",
                "--kind",
                "pursuit",
                "--title",
                "What enrollment does the fixture report?",
                "--dest",
                notebook,
            ],
            cwd=work,
            env=env,
        )
        if "actor: agent:release-smoke" not in created:
            raise SystemExit(f"first-write attribution was not reported correctly:\n{created}")

        run([flip, "workflow", "use", "question-pursuit@1"], cwd=notebook, env=env)
        run([flip, "next", "--json", "--explain"], cwd=notebook, env=env)

        run([
            flip, "session", "start", "first-pass", "--tools", "local-files",
            "--phase", "orient", "--item", "Q1",
        ], cwd=notebook, env=env)
        run([flip, "log", "started: release smoke"], cwd=notebook, env=env)
        run([flip, "add-source", fixture, "--note", "release smoke fixture"], cwd=notebook, env=env)
        run(
            [
                flip,
                "grade",
                "F1",
                "--independence",
                "independent",
                "--basis",
                "measured",
                "--base-defined",
                "--method",
                "direct row inspection",
                "--freshness",
                "fresh",
            ],
            cwd=notebook,
            env=env,
        )
        run(
            [
                flip,
                "claim",
                "add",
                "The fixture reports enrollment of 100",
                "--source",
                "F1",
                "--load-bearing",
            ],
            cwd=notebook,
            env=env,
        )
        run([flip, "claim", "status", "C1", "verified"], cwd=notebook, env=env)
        run(
            [
                flip, "session", "end", "first-pass", "--summary", "wheel workflow passed",
                "--output", "C1", "--check", "doctor",
            ],
            cwd=notebook,
            env=env,
        )
        run([flip, "resolve", "F1", "--json"], cwd=notebook, env=env)
        run([flip, "show", "--claims"], cwd=notebook, env=env)
        run([flip, "doctor"], cwd=notebook, env=env)

        print(f"release smoke passed: {wheel.name} ({version})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", nargs="?", help="wheel path (default: sole dist/ wheel)")
    args = parser.parse_args()
    smoke(select_wheel(args.wheel))


if __name__ == "__main__":
    main()
