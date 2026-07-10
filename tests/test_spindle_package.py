"""The spindle-package data file must mirror pyproject's [tool.spindle.package].

The data file exists because wheels don't carry pyproject.toml: spindle
discovers PyPI-installed packages through <module>/spindle-package.toml.
Drift between the two would ship a wheel advertising the wrong skills.
"""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _spindle_table(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))["tool"]["spindle"]["package"]


def test_data_file_mirrors_pyproject():
    py = _spindle_table(REPO / "pyproject.toml")
    data = _spindle_table(REPO / "src" / "flip" / "spindle-package.toml")
    assert data == py


def test_version_matches_project_version():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    data = _spindle_table(REPO / "src" / "flip" / "spindle-package.toml")
    assert data["version"] == project["project"]["version"]


def test_declared_skills_exist_on_disk():
    data = _spindle_table(REPO / "src" / "flip" / "spindle-package.toml")
    for skill in data["skills"]:
        assert (REPO / "src" / "flip" / "skills" / skill / "SKILL.md").is_file(), skill
