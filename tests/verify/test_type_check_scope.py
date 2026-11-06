import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TYPE_ERROR = 'x: int = "a"\n'


def type_errors_in(project: Path) -> set[str]:
    done = subprocess.run(
        [sys.executable, "-m", "basedpyright", "--outputjson"],
        capture_output=True,
        text=True,
        check=False,
        cwd=project,
    )
    report = json.loads(done.stdout)
    return {
        Path(diagnostic["file"]).relative_to(project.resolve()).as_posix()
        for diagnostic in report["generalDiagnostics"]
        if diagnostic["severity"] == "error"
    }


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text((ROOT / "pyproject.toml").read_text())
    (tmp_path / ".venv").symlink_to(ROOT / ".venv")
    return tmp_path


@pytest.mark.parametrize("relative", ["conftest.py", "scripts/build.py", "src/cad/app.py"])
def test_type_errors_fail_anywhere_in_the_project(project: Path, relative: str) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TYPE_ERROR)
    assert type_errors_in(project) == {relative}


@pytest.mark.parametrize("relative", ["proto/kernel.py", ".cache/tool.py", "__pycache__/mod.py"])
def test_type_errors_are_ignored_in_excluded_directories(project: Path, relative: str) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TYPE_ERROR)
    assert type_errors_in(project) == set()
