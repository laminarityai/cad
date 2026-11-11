from pathlib import Path

import pytest

from cad.geometry import job, store
from cad.geometry.model import TessellationFailed
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
