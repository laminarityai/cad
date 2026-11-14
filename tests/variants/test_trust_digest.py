"""`TRUST_DIGEST` hashes only the files whose edit can change what a build stores for the same
code and image. Every other file of `sandbox/` and `variants/` is named here with why it is left
out, so a new file fails until someone puts it in one list or the other."""

import ast
import inspect
from pathlib import Path
from typing import Final

import pytest

from cad.sandbox import builder, meter
from cad.variants import entry
from tests.support.deploys import FOLDERS, copied, digest_after_editing

LEFT_OUT: Final = {
    "sandbox/__main__.py": "the cad-sandbox command: it builds images and prints a check run",
    "sandbox/host.py": "it runs checks on a stored build, and check versions hash it",
    "sandbox/meter.py": "it reserves and settles a run's seconds, and never sees the job or result",
    "sandbox/on_body.py": "it names the body a requirement is about, and no build reads it",
    "sandbox/stage.py": "it stages what a check container mounts, and a build mounts nothing",
}
CALLED_AROUND_A_BUILD: Final = {"sandbox/meter.py"}


def python_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for folder in FOLDERS
        for path in (root / folder).rglob("*.py")
        if "__pycache__" not in path.parts
    }


def test_every_file_of_the_two_folders_is_kept_or_left_out_by_name() -> None:
    kept = set(entry.TRUSTED_FILES)
    assert not kept & LEFT_OUT.keys()
    assert python_files(entry.SOURCE) == kept | LEFT_OUT.keys()


def test_a_new_file_in_either_folder_fails_until_it_is_classified(tmp_path: Path) -> None:
    root = copied(tmp_path)
    (root / "sandbox" / "lifecycle.py").write_text("x = 1\n")
    assert python_files(root) - set(entry.TRUSTED_FILES) - LEFT_OUT.keys() == {
        "sandbox/lifecycle.py"
    }


def imported_files(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_bytes())):
        names = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            if isinstance(node, ast.ImportFrom) and node.module is not None
            else []
        )
        for name in names:
            parts = name.split(".")
            if len(parts) >= 3 and parts[0] == "cad" and parts[1] in FOLDERS:
                found.add(f"{parts[1]}/{parts[2]}.py")
    return found


def test_no_kept_file_imports_a_left_out_file_but_the_meter() -> None:
    imported = {one for name in entry.TRUSTED_FILES for one in imported_files(entry.SOURCE / name)}
    assert imported & LEFT_OUT.keys() == CALLED_AROUND_A_BUILD


def test_the_meter_is_given_only_the_kind_and_a_ceiling_and_yields_nothing() -> None:
    assert list(inspect.signature(meter.charged).parameters) == ["kind", "ceiling_seconds"]
    with meter.charged("build", 1.0) as held:
        assert held is None


def test_a_build_job_mounts_nothing_so_staged_sources_never_reach_a_build() -> None:
    assert builder.build_job("result = 1", "image", 60).mounts == ()


def test_the_digest_hashes_the_kept_files_as_they_are_on_disk(tmp_path: Path) -> None:
    assert entry.trust_digest(copied(tmp_path)) == entry.TRUST_DIGEST


@pytest.mark.parametrize("name", sorted(LEFT_OUT))
def test_editing_a_left_out_file_keeps_every_variant_id(tmp_path: Path, name: str) -> None:
    assert digest_after_editing(tmp_path, name) == entry.TRUST_DIGEST


@pytest.mark.parametrize("name", entry.TRUSTED_FILES)
def test_editing_a_kept_file_re_keys_every_variant(tmp_path: Path, name: str) -> None:
    assert digest_after_editing(tmp_path, name) != entry.TRUST_DIGEST
