from pathlib import Path

from cad.checks import job_store, stored
from cad.checks.container import fea
from tests.support.lanes import VID
from tests.support.stress import fea_job, unknown_fea


def test_a_stored_result_of_a_check_is_found_whatever_its_verdict(tmp_path: Path) -> None:
    root = tmp_path / "variants"
    root.mkdir()
    job_store.write(fea_job(root, VID), unknown_fea())
    assert stored.has_result(root, VID, fea.ID)
    assert not stored.has_result(root, VID, "a check that never ran")
    assert not stored.has_result(root, "0000000000000000", fea.ID)


def test_a_result_this_store_did_not_sign_is_not_found(tmp_path: Path) -> None:
    root = tmp_path / "variants"
    root.mkdir()
    spec = fea_job(root, VID)
    job_store.write(spec, unknown_fea("unknown"))
    path = job_store.result_path(spec)
    path.write_bytes(path.read_bytes().replace(b"unknown", b"UNKNOWN"))
    assert not stored.has_result(root, VID, fea.ID)
