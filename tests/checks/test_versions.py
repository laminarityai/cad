import ast
import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Final

import pytest

from cad.checks.container.check import CheckModule, Subject
from cad.checks.container.inputs import Input
from cad.checks.container.suite import CHECKS
from cad.checks.container.wire import FindingWire, SourceLiteral
from cad.checks.report import DEPENDENCIES, IMAGE_TAG, SPECS, build_request, specs
from cad.sandbox import container, stage
from cad.sandbox.container import run_argv
from cad.sandbox.host import build_job, check_job
from cad.sandbox.stage import (
    CONTAINER_ENTRY,
    PACKAGE_PATH,
    SOURCES,
    Sources,
    materialize,
    read_sources,
)
from cad.tables.materials import load_materials

CONTAINER_PACKAGE = "cad.checks.container"
IMAGE = "sha256:abc"
CHECKS_DIR = stage.SRC_ROOT / PACKAGE_PATH


def edited(sources: Sources, name: str) -> Sources:
    path = f"{PACKAGE_PATH}/{name}"
    return replace(sources, files={**sources.files, path: sources.files[path] + b"\n# edited\n"})


def versions(sources: Sources) -> dict[str, str]:
    return {spec.id: spec.version for spec in specs(sources, IMAGE_TAG)}


def test_every_check_file_is_named_by_its_id() -> None:
    assert {f"{PACKAGE_PATH}/{check.ID}.py" for check in CHECKS} <= set(SOURCES.files)


class NoSource:
    ID = "bare"
    FORMULA = "none"
    SOURCES: tuple[SourceLiteral, ...] = ()
    MEASURES: Mapping[str, str] = MappingProxyType({"x": "mm"})
    TAKES: frozenset[Input] = frozenset()
    READS: Mapping[str, Input] = MappingProxyType({})
    REQUIRES: tuple[CheckModule, ...] = ()

    def run(self, subject: Subject) -> FindingWire:
        raise NotImplementedError


def test_a_check_that_cites_no_source_is_refused() -> None:
    with pytest.raises(ValueError, match="bare cites no source"):
        specs(SOURCES, IMAGE_TAG, (NoSource(),))


def test_the_check_ids_are_the_suite_order() -> None:
    assert [spec.id for spec in SPECS] == ["closed_solid", "interference", "mass", "extents"]


@pytest.mark.parametrize(
    ("check_file", "changed"),
    [
        ("closed_solid.py", {"closed_solid", "mass", "extents"}),
        ("interference.py", {"interference", "mass"}),
        ("mass.py", {"mass"}),
    ],
)
def test_editing_a_check_file_changes_the_version_of_every_check_that_runs_it(
    check_file: str, changed: set[str]
) -> None:
    before = versions(DEPENDENCIES)
    after = versions(edited(DEPENDENCIES, check_file))
    assert {i for i in before if before[i] != after[i]} == changed


KERNEL_FILES = sorted(
    p.relative_to(CHECKS_DIR).as_posix() for p in (CHECKS_DIR / "kernel").glob("*.py")
)


def test_the_kernel_package_is_staged_whole() -> None:
    assert KERNEL_FILES
    assert set(KERNEL_FILES) <= {name.removeprefix(f"{PACKAGE_PATH}/") for name in SOURCES.files}


@pytest.mark.parametrize("shared", [*KERNEL_FILES, "check.py", "wire.py", "runner.py", "suite.py"])
def test_editing_a_shared_file_changes_every_version(shared: str) -> None:
    before = versions(DEPENDENCIES)
    after = versions(edited(DEPENDENCIES, shared))
    assert {i for i in before if before[i] != after[i]} == set(before)


def checks_imported_by(path: Path) -> set[str]:
    ids = {check.ID for check in CHECKS}
    return {
        alias.name
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ImportFrom) and node.module == CONTAINER_PACKAGE
        for alias in node.names
        if alias.name in ids
    }


def test_every_check_a_check_file_imports_feeds_its_version_through_requires() -> None:
    for check in CHECKS:
        imported = checks_imported_by(CHECKS_DIR / f"{check.ID}.py")
        assert imported == {required.ID for required in check.REQUIRES}, check.ID


def test_the_four_versions_differ_from_each_other() -> None:
    assert len({spec.version for spec in SPECS}) == 4


def imports_in(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
    return found


def test_container_modules_import_only_the_standard_library_and_themselves() -> None:
    allowed = sys.stdlib_module_names
    for path in sorted(CHECKS_DIR.rglob("*.py")):
        for name in imports_in(path):
            top = name.split(".")[0]
            assert top in allowed or name.startswith(CONTAINER_PACKAGE), (
                f"{path.relative_to(CHECKS_DIR)} imports {name}, which the check image lacks"
            )


ADAPTERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "kernel": "OCP",
        "mesher.py": "gmsh",
        "calculix.py": "ccx",
        "orca.py": "orca",
    }
)


def engine_names_in(path: Path, engine: str) -> bool:
    for node in ast.walk(ast.parse(path.read_text())):
        match node:
            case ast.Constant(value=str() as value):
                named = value == engine or value.startswith(f"{engine}.")
            case ast.Import(names=names):
                named = any(alias.name.split(".")[0] == engine for alias in names)
            case ast.ImportFrom(module=str() as module):
                named = module.split(".")[0] == engine
            case _:
                named = False
        if named:
            return True
    return False


def owned_by(adapter: str, relative: Path) -> bool:
    name = relative.as_posix()
    return name == adapter or name.startswith(f"{adapter}/")


def engine_leaks(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root)} names {engine}; only {adapter} may"
        for path in sorted(root.rglob("*.py"))
        for adapter, engine in ADAPTERS.items()
        if not owned_by(adapter, path.relative_to(root)) and engine_names_in(path, engine)
    ]


def test_only_an_engines_adapter_names_that_engine() -> None:
    assert engine_leaks(CHECKS_DIR) == []


def test_an_adapter_that_exists_does_name_its_engine() -> None:
    files = sorted(CHECKS_DIR.rglob("*.py"))
    for adapter, engine in ADAPTERS.items():
        owned = [p for p in files if owned_by(adapter, p.relative_to(CHECKS_DIR))]
        assert owned or adapter != "kernel"
        assert not owned or any(engine_names_in(p, engine) for p in owned), adapter


@pytest.mark.parametrize(
    ("file", "source", "leaks"),
    [
        ("extents.py", "import importlib\nimportlib.import_module('OCP.gp')\n", True),
        ("extents.py", "import gmsh\n", True),
        ("mass.py", "from gmsh import model\n", True),
        ("kernel/other.py", "import importlib\nimportlib.import_module(f'OCP.{1}')\n", False),
        ("mesher.py", "import gmsh\n", False),
        ("mesher.py", "import importlib\nimportlib.import_module('OCP.gp')\n", True),
        ("calculix.py", "import subprocess\nsubprocess.run(['ccx'])\n", False),
        ("fea.py", "import subprocess\nsubprocess.run(['ccx'])\n", True),
        ("orca.py", "ENGINE = 'orca'\n", False),
        ("slice.py", "ENGINE = 'orca'\n", True),
        ("slice.py", "ENGINE = 'the orca whale'\n", False),
    ],
)
def test_the_engine_lint_flags_a_name_outside_its_adapter(
    tmp_path: Path, file: str, source: str, leaks: bool
) -> None:
    path = tmp_path / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    assert bool(engine_leaks(tmp_path)) is leaks


def test_the_staged_directory_holds_exactly_the_hashed_bytes_read_only(tmp_path: Path) -> None:
    staged = materialize(SOURCES, tmp_path)
    assert staged == materialize(SOURCES, tmp_path)
    assert staged.name == SOURCES.digest[: stage.DIGEST_CHARS]
    files = {p.relative_to(staged).as_posix(): p for p in staged.rglob("*") if p.is_file()}
    assert {name: path.read_bytes() for name, path in files.items()} == SOURCES.files
    assert {stat.S_IMODE(path.stat().st_mode) for path in files.values()} == {0o444}
    directories = [staged, *(p for p in staged.rglob("*") if p.is_dir())]
    assert {stat.S_IMODE(path.stat().st_mode) for path in directories} == {0o555}


def test_a_tampered_or_extended_staged_directory_is_rebuilt_from_the_hashed_bytes(
    tmp_path: Path,
) -> None:
    staged = materialize(SOURCES, tmp_path)
    kernel = staged / PACKAGE_PATH / "kernel" / "ocp_kernel.py"
    kernel.chmod(0o644)
    kernel.write_text("raise SystemExit('tampered')\n")
    stray = staged / PACKAGE_PATH / "stray.py"
    (staged / PACKAGE_PATH).chmod(0o755)
    stray.write_text("x = 1\n")
    again = materialize(SOURCES, tmp_path)
    assert again == staged
    assert kernel.read_bytes() == SOURCES.files[f"{PACKAGE_PATH}/kernel/ocp_kernel.py"]
    assert not stray.exists()
    assert os.listdir(tmp_path) == [staged.name]


def test_a_symlinked_staged_directory_is_replaced_without_touching_its_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "stage"
    root.mkdir()
    outside = tmp_path / "outside"
    locked = outside / "locked"
    locked.mkdir(parents=True)
    locked.chmod(0o500)
    planted = root / SOURCES.digest[: stage.DIGEST_CHARS]
    planted.symlink_to(outside, target_is_directory=True)
    try:
        staged = materialize(SOURCES, root)
        assert stat.S_IMODE(locked.stat().st_mode) == 0o500
    finally:
        locked.chmod(0o755)
    assert staged == planted
    assert not staged.is_symlink()
    assert os.listdir(outside) == ["locked"]


def test_reading_the_sources_twice_gives_the_same_digest_and_a_changed_file_a_new_one(
    tmp_path: Path,
) -> None:
    for name, data in SOURCES.files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(data)
    first = read_sources(CONTAINER_ENTRY, root=tmp_path)
    assert first == read_sources(CONTAINER_ENTRY, root=tmp_path) == SOURCES
    with (tmp_path / PACKAGE_PATH / "mass.py").open("a") as changed:
        changed.write("# edited\n")
    assert read_sources(CONTAINER_ENTRY, root=tmp_path).digest != first.digest


def test_the_build_container_gets_no_mount() -> None:
    job = build_job("x = 1\n", IMAGE, 60)
    argv = run_argv("n", job)
    assert job.mounts == ()
    assert "--mount" not in argv and "-v" not in argv and "--volume" not in argv


def test_the_check_container_gets_one_read_only_mount_and_the_limits_of_a_build() -> None:
    request = build_request("prusament-pla", load_materials())
    job = check_job(b"BREP", IMAGE, request, 60)
    argv = run_argv("n", job)
    mount = argv.index("--mount")
    assert argv.count("--mount") == 1
    assert (
        argv[mount + 1] == f"type=bind,source={job.mounts[0].source},target=/opt/trusted,readonly"
    )
    head = argv[: argv.index(IMAGE)]
    without_mount = [*head[:mount], *head[mount + 2 :]]
    build_head = run_argv("n", build_job("x = 1\n", IMAGE, 60))
    assert [
        part.replace("cad.sandbox=check", "cad.sandbox=build") for part in without_mount
    ] == list(build_head[: build_head.index(IMAGE)])
    assert job.stdin == b"BREP"
    assert job.wall_seconds == 60


def test_the_check_command_boots_the_staged_package_with_the_request_and_the_report_cap() -> None:
    request = build_request("unobtainium", load_materials())
    job = check_job(b"", IMAGE, request, 60)
    assert job.command[:4] == ("python", "-I", "-c", stage.BOOT)
    assert job.command[4] == "120"
    assert "unobtainium" in job.command[5]
    assert job.command[6] == str(container.REPORT_CAP)
