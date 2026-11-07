import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cad.checks import report
from cad.checks.report import SPECS
from cad.sandbox import stage

SRC = Path(stage.__file__).parents[2]

VERSIONS = (
    "import json, sys; sys.path.insert(0, sys.argv[1]); "
    "from cad.checks.report import SPECS; "
    "assert SPECS and __import__('cad').__file__.startswith(sys.argv[1]); "
    "print(json.dumps({spec.id: spec.version for spec in SPECS}))"
)

LOADED = (
    "import json, sys; import cad.scorecard.score, cad.checks.container.runner; "
    "print(json.dumps([m.__file__ for n, m in sys.modules.items() "
    "if n.split('.')[0] == 'cad' and m.__file__]))"
)


def run_python(program: str, *args: str) -> str:
    done = subprocess.run(
        (sys.executable, "-c", program, *args), capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def copied_tree(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    shutil.copytree(SRC / "cad", root / "cad", ignore=shutil.ignore_patterns("__pycache__"))
    return root


@pytest.mark.parametrize(
    "edited",
    [
        "cad/checks/report.py",
        "cad/checks/result.py",
        "cad/sandbox/stage.py",
        "cad/sandbox/host.py",
        "cad/sandbox/container.py",
        "cad/tables/materials.py",
        "cad/checks/container/kernel.py",
        "cad/__init__.py",
    ],
)
def test_editing_code_a_scorecard_depends_on_changes_every_check_version(
    tmp_path: Path, edited: str
) -> None:
    root = copied_tree(tmp_path)
    with (root / edited).open("a") as file:
        file.write("\n# edited\n")
    after = json.loads(run_python(VERSIONS, str(root)))
    unchanged = [spec.id for spec in SPECS if after[spec.id] == spec.version]
    assert unchanged == [], f"{edited} changed, but these checks kept their version: {unchanged}"


def test_every_module_scoring_loads_feeds_the_check_versions() -> None:
    loaded = {Path(path).relative_to(SRC).as_posix() for path in json.loads(run_python(LOADED))}
    assert loaded - set(report.DEPENDENCIES.files) == set()


def test_an_installed_cad_package_does_not_shadow_the_staged_checks(tmp_path: Path) -> None:
    staged = stage.materialize(stage.SOURCES, tmp_path / "stage")
    installed = tmp_path / "site" / "cad" / "checks" / "container"
    installed.mkdir(parents=True)
    for package in (installed, installed.parent, installed.parent.parent):
        (package / "__init__.py").write_text("")
    (installed / "suite.py").write_text("raise SystemExit('the installed cad ran')\n")
    program = (
        "import sys; sys.path.insert(0, sys.argv[2]); sys.path.insert(0, sys.argv[1]); "
        "import cad.checks.container.suite as suite; print(suite.__file__)"
    )
    shown = run_python(program, str(staged), str(tmp_path / "site"))
    assert Path(shown.strip()).is_relative_to(staged)
