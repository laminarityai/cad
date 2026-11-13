from pathlib import Path
from typing import Literal, TypeAliasType, get_args, get_origin, get_type_hints, is_typeddict

import pytest
from pydantic import BaseModel

from cad.geometry import job, store
from cad.geometry.model import Stored, TessellationFailed
from cad.sandbox.outcome import SandboxUnavailable

SHA = "a" * 64
FAILED = TessellationFailed(brep_sha256=SHA, version=job.VERSION, reason="no faces")


def test_a_mesh_is_stored_under_a_new_directory_as_its_json(tmp_path: Path) -> None:
    root = tmp_path / "geometry"
    store.write(root, FAILED)
    path = root / job.VERSION / f"{SHA}.json"
    assert path.read_bytes() == FAILED.model_dump_json().encode()
    assert store.read(root, SHA) == FAILED
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_an_unwritable_store_is_refused_and_leaves_no_temporary(tmp_path: Path) -> None:
    (tmp_path / job.VERSION).mkdir()
    (tmp_path / job.VERSION).chmod(0o555)
    try:
        with pytest.raises(SandboxUnavailable, match=f"cannot store the mesh of BREP {SHA}"):
            store.write(tmp_path, FAILED)
    finally:
        (tmp_path / job.VERSION).chmod(0o755)
    assert list((tmp_path / job.VERSION).iterdir()) == []


def test_a_write_that_cannot_replace_the_mesh_leaves_no_temporary(tmp_path: Path) -> None:
    path = store.path(tmp_path, SHA)
    (path / "occupied").mkdir(parents=True)
    with pytest.raises(SandboxUnavailable, match="cannot store the mesh"):
        store.write(tmp_path, FAILED)
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def _modules_of(hint: object, seen: set[object]) -> set[str]:
    """The modules that define the served type and every type its fields hold, and their bases."""
    if hint in seen:
        return set()
    seen.add(hint)
    found: set[str] = set()
    if isinstance(hint, TypeAliasType):
        found |= {str(hint.__module__)} | _modules_of(hint.__value__, seen)
    elif get_origin(hint) is Literal:
        return found
    if isinstance(hint, type):
        found |= {one.__module__ for one in hint.__mro__}
        if is_typeddict(hint) or issubclass(hint, BaseModel):
            for field in get_type_hints(hint, include_extras=True).values():
                found |= _modules_of(field, seen)
    for argument in get_args(hint):
        found |= _modules_of(argument, seen)
    return found


def test_the_mesh_version_hashes_every_module_the_served_mesh_is_defined_in() -> None:
    """The mesh URL names the version and is served immutable, so an edit to any module that
    shapes its bytes must make a new version."""
    hashed = set(job.SOURCES.files) | set(job.SERVED.files)
    defined_in = {
        module.replace(".", "/") + ".py"
        for module in _modules_of(Stored, set())
        if module.split(".")[0] == "cad"
    }
    assert "cad/geometry/model.py" in defined_in
    assert defined_in <= hashed
    assert set(job.SERVED.packages) >= {"pydantic", "pydantic-core"}
