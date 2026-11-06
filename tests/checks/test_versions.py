import ast
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from cad.checks.container.suite import CHECKS
from cad.checks.report import SPECS, build_request, specs
from cad.sandbox import stage
from cad.sandbox.container import run_argv
from cad.sandbox.host import build_job, check_job
from cad.sandbox.stage import PACKAGE_PATH, SOURCES, Sources, materialize, read_sources
from cad.tables.materials import load_materials

CONTAINER_PACKAGE = "cad.checks.container"
IMAGE = "sha256:abc"


def edited(sources: Sources, name: str) -> Sources:
    path = f"{PACKAGE_PATH}/{name}"
    return replace(sources, files={**sources.files, path: sources.files[path] + b"\n# edited\n"})


def versions(sources: Sources) -> dict[str, str]:
    return {spec.id: spec.version for spec in specs(sources)}


def test_every_check_file_is_named_by_its_id() -> None:
    assert {f"{PACKAGE_PATH}/{check.ID}.py" for check in CHECKS} <= set(SOURCES.files)


def test_the_check_ids_are_the_suite_order() -> None:
    assert [spec.id for spec in SPECS] == ["closed_solid", "interference", "mass"]


@pytest.mark.parametrize(
    ("check_file", "changed"),
    [
        ("closed_solid.py", {"closed_solid", "mass"}),
        ("interference.py", {"interference", "mass"}),
        ("mass.py", {"mass"}),
    ],
)
def test_editing_a_check_file_changes_the_version_of_every_check_that_runs_it(
    check_file: str, changed: set[str]
) -> None:
    before = versions(SOURCES)
    after = versions(edited(SOURCES, check_file))
    assert {i for i in before if before[i] != after[i]} == changed


@pytest.mark.parametrize("shared", ["kernel.py", "check.py", "wire.py", "runner.py", "suite.py"])
def test_editing_a_shared_file_changes_every_version(shared: str) -> None:
    before = versions(SOURCES)
    after = versions(edited(SOURCES, shared))
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
        imported = checks_imported_by(stage.CHECKS_DIR / f"{check.ID}.py")
        assert imported == {required.ID for required in check.REQUIRES}, check.ID


def test_the_three_versions_differ_from_each_other() -> None:
    assert len({spec.version for spec in SPECS}) == 3


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
    for path in sorted(stage.CHECKS_DIR.glob("*.py")):
        for name in imports_in(path):
            top = name.split(".")[0]
            assert top in allowed or name.startswith(CONTAINER_PACKAGE), (
                f"{path.name} imports {name}, which the check container's image does not have"
            )


def ocp_module_names_in(path: Path) -> set[str]:
    return {
        node.value
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (node.value == "OCP" or node.value.startswith("OCP."))
    }


def test_only_kernel_py_names_an_ocp_module() -> None:
    assert ocp_module_names_in(stage.CHECKS_DIR / "kernel.py")
    for path in sorted(stage.CHECKS_DIR.glob("*.py")):
        if path.name != "kernel.py":
            assert not ocp_module_names_in(path), f"{path.name} must reach OCP through kernel.py"


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
    kernel = staged / PACKAGE_PATH / "kernel.py"
    kernel.chmod(0o644)
    kernel.write_text("raise SystemExit('tampered')\n")
    stray = staged / PACKAGE_PATH / "stray.py"
    (staged / PACKAGE_PATH).chmod(0o755)
    stray.write_text("x = 1\n")
    again = materialize(SOURCES, tmp_path)
    assert again == staged
    assert (staged / PACKAGE_PATH / "kernel.py").read_bytes() == SOURCES.files[
        f"{PACKAGE_PATH}/kernel.py"
    ]
    assert not stray.exists()
    assert os.listdir(tmp_path) == [staged.name]


def test_reading_the_sources_twice_gives_the_same_digest_and_a_changed_file_a_new_one(
    tmp_path: Path,
) -> None:
    for path in stage.CHECKS_DIR.glob("*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    first = read_sources(tmp_path)
    assert first == read_sources(tmp_path)
    with (tmp_path / "mass.py").open("a") as changed:
        changed.write("# edited\n")
    assert read_sources(tmp_path).digest != first.digest


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


def test_the_check_command_boots_the_staged_package_with_the_request() -> None:
    request = build_request("unobtainium", load_materials())
    job = check_job(b"", IMAGE, request, 60)
    assert job.command[:4] == ("python", "-I", "-c", stage.BOOT)
    assert job.command[4] == "120"
    assert "unobtainium" in job.command[5]
