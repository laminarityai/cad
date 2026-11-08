import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from packaging.utils import canonicalize_name

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


VERSIONS_WITH_SITE = (
    "import json, sys; sys.path.insert(0, sys.argv[1]); "
    "from cad.checks.report import SPECS; "
    "print(json.dumps({spec.id: spec.version for spec in SPECS}))"
)

DISTRIBUTIONS_LOADED = (
    "import json, sys, importlib.metadata as m; import cad.scorecard.score; "
    "owners = m.packages_distributions(); "
    "print(json.dumps(sorted({m.distribution(d).name for n in list(sys.modules) "
    "for d in owners.get(n.split('.')[0], ())})))"
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
    shutil.copytree(SRC.parent / "sandbox", tmp_path / "sandbox")
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
        "cad/checks/container/kernel/__init__.py",
        "cad/checks/container/kernel/protocol.py",
        "cad/checks/container/kernel/ocp_handles.py",
        "cad/checks/container/kernel/ocp_kernel.py",
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


@pytest.mark.parametrize("outside", ["cad/briefs/", "cad/scorecard/requirements.py"])
def test_judging_requirements_is_outside_what_check_versions_hash(outside: str) -> None:
    inside = [path for path in report.DEPENDENCIES.files if path.startswith(outside)]
    assert inside == []


def test_every_library_scoring_loads_feeds_the_check_versions() -> None:
    loaded = {canonicalize_name(name) for name in json.loads(run_python(DISTRIBUTIONS_LOADED))}
    assert loaded - set(report.DEPENDENCIES.packages) == set()


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


def site_with_bumped(tmp_path: Path, distribution: str) -> Path:
    metadata = importlib.metadata.distribution(distribution).read_text("METADATA") or ""
    site = tmp_path / "site"
    bumped = site / f"{distribution.replace('-', '_')}-999.0.dist-info"
    bumped.mkdir(parents=True)
    text = re.sub(r"^Version: .*$", "Version: 999.0", metadata, flags=re.M)
    (bumped / "METADATA").write_text(text)
    return site


@pytest.mark.parametrize(
    "distribution",
    ["pint", "pydantic", "pydantic-core", "pyyaml", "typing-extensions", "flexparser"],
)
def test_bumping_a_library_scoring_imports_changes_every_check_version(
    tmp_path: Path, distribution: str
) -> None:
    after = json.loads(
        run_python(VERSIONS_WITH_SITE, str(site_with_bumped(tmp_path, distribution)))
    )
    unchanged = [spec.id for spec in SPECS if after[spec.id] == spec.version]
    assert unchanged == [], (
        f"{distribution} changed, but these checks kept their version: {unchanged}"
    )


def test_bumping_a_dev_tool_keeps_every_check_version(tmp_path: Path) -> None:
    after = json.loads(run_python(VERSIONS_WITH_SITE, str(site_with_bumped(tmp_path, "ruff"))))
    assert after == {spec.id: spec.version for spec in SPECS}
