import json
import subprocess
from pathlib import Path

import pytest

from cad.verify.steps import STEPS

ROOT = Path(__file__).resolve().parents[2]
TYPE_ERROR = 'x: int = "a"\n'


def type_errors_in(project: Path) -> set[str]:
    errors: set[str] = set()
    for step in STEPS:
        if not step.name.startswith("basedpyright"):
            continue
        done = subprocess.run(
            [*step.argv, "--outputjson"],
            capture_output=True,
            text=True,
            check=False,
            cwd=project,
        )
        report = json.loads(done.stdout)
        errors |= {
            Path(diagnostic["file"]).relative_to(project.resolve()).as_posix()
            for diagnostic in report["generalDiagnostics"]
            if diagnostic["severity"] == "error"
        }
    return errors


def make_project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text((ROOT / "pyproject.toml").read_text())
    (path / ".claude").mkdir()
    config = ".claude/pyrightconfig.json"
    (path / config).write_text((ROOT / config).read_text())
    (path / ".venv").symlink_to(ROOT / ".venv")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path)


@pytest.mark.parametrize(
    "relative",
    [
        "conftest.py",
        "scripts/build.py",
        "src/cad/app.py",
        ".claude/skills/verify/scripts/claude_session.py",
    ],
)
def test_type_errors_fail_anywhere_in_the_project(project: Path, relative: str) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TYPE_ERROR)
    assert type_errors_in(project) == {relative}


@pytest.mark.parametrize(
    "relative",
    [
        "proto/kernel.py",
        ".cache/tool.py",
        "__pycache__/mod.py",
        ".git/hooks/hook.py",
        ".ruff_cache/tool.py",
        ".pytest_cache/tool.py",
        ".mypy_cache/tool.py",
        ".claude/worktrees/other/src/cad/app.py",
    ],
)
def test_type_errors_are_ignored_in_excluded_directories(project: Path, relative: str) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TYPE_ERROR)
    assert type_errors_in(project) == set()


def test_type_errors_fail_in_a_worktree_nested_under_another_checkout(tmp_path: Path) -> None:
    outer = make_project(tmp_path / "repo")
    worktree = make_project(outer / ".claude" / "worktrees" / "agent")
    path = worktree / "src" / "cad" / "app.py"
    path.parent.mkdir(parents=True)
    path.write_text(TYPE_ERROR)
    assert type_errors_in(worktree) == {"src/cad/app.py"}
