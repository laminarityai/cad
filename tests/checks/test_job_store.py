import hashlib
import hmac
from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks import job_store
from cad.checks.jobs import JobSpec
from cad.sandbox.outcome import SandboxUnavailable
from tests.support.lanes import VID, job, measured

RESULT = measured("stored")


def mac(root: Path, spec: JobSpec, record: bytes) -> bytes:
    key = (root.parent / f"{root.name}.key").read_bytes()
    slot = f"{VID}\0{spec.key}".encode()
    return hmac.new(key, slot + b"\0" + record, hashlib.sha256).hexdigest().encode()


def stored(root: Path) -> tuple[JobSpec, Path]:
    spec = job(root)
    job_store.write(spec, RESULT)
    return spec, job_store.result_path(spec)


def test_a_result_is_its_mac_a_newline_and_its_json(tmp_path: Path) -> None:
    root = tmp_path / "variants"
    root.mkdir()
    spec, path = stored(root)
    record = RESULT.model_dump_json().encode()
    assert path == root / VID / "jobs" / f"{spec.key}.signed"
    assert path.read_bytes() == mac(root, spec, record) + b"\n" + record
    assert job_store.read(spec) == RESULT
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]


def test_a_result_written_by_hand_in_that_format_reads_back(tmp_path: Path) -> None:
    root = tmp_path / "variants"
    root.mkdir()
    spec, path = stored(root)
    other = measured("written by hand").model_dump_json().encode()
    path.write_bytes(mac(root, spec, other) + b"\n" + other)
    assert job_store.read(spec) == measured("written by hand")


SPOILED: dict[str, Callable[[bytes], bytes]] = {
    "tampered": lambda data: data.replace(b"stored", b"STORED"),
    "no record": lambda data: data[: data.index(b"\n")],
    "truncated": lambda data: data[:-1],
    "empty": lambda data: b"",
    "no newline": lambda data: data.replace(b"\n", b" ", 1),
}


@pytest.mark.parametrize("spoil", SPOILED)
def test_a_spoiled_result_reads_as_not_run(tmp_path: Path, spoil: str) -> None:
    spec, path = stored(tmp_path)
    path.write_bytes(SPOILED[spoil](path.read_bytes()))
    assert job_store.read(spec) is None


def test_a_missing_result_reads_as_not_run(tmp_path: Path) -> None:
    assert job_store.read(job(tmp_path)) is None


def test_a_timed_out_result_is_not_stored(tmp_path: Path) -> None:
    spec = job(tmp_path)
    job_store.write(spec, RESULT.model_copy(update={"timed_out": True}))
    assert not (tmp_path / VID / "jobs").exists()


def test_an_unusable_key_refuses_the_write_and_the_read(tmp_path: Path) -> None:
    (tmp_path / "variants").mkdir()
    spec, _ = stored(tmp_path / "variants")
    (tmp_path / "variants.key").chmod(0o644)
    with pytest.raises(SandboxUnavailable, match="key is unusable"):
        job_store.read(spec)
    with pytest.raises(SandboxUnavailable, match="key is unusable"):
        job_store.write(spec, RESULT)


def test_a_store_that_cannot_be_written_is_refused_and_leaves_no_temporary(
    tmp_path: Path,
) -> None:
    spec, path = stored(tmp_path)
    path.parent.chmod(0o555)
    try:
        with pytest.raises(
            SandboxUnavailable, match=f"cannot store the result of a job for variant {VID}"
        ):
            job_store.write(spec, measured("again"))
        with pytest.raises(SandboxUnavailable, match="cannot store the attempt count"):
            job_store.begin_attempt(spec)
    finally:
        path.parent.chmod(0o755)
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
    assert job_store.read(spec) == RESULT


def test_a_write_that_cannot_replace_the_result_leaves_no_temporary(tmp_path: Path) -> None:
    spec = job(tmp_path)
    path = job_store.result_path(spec)
    (path / "occupied").mkdir(parents=True)
    with pytest.raises(SandboxUnavailable, match="cannot store the result"):
        job_store.write(spec, RESULT)
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]


def test_a_variant_that_is_not_stored_gets_no_jobs_directory(tmp_path: Path) -> None:
    spec = job(tmp_path)
    (tmp_path / VID).rmdir()
    with pytest.raises(SandboxUnavailable, match="cannot store the result"):
        job_store.write(spec, RESULT)
    with pytest.raises(SandboxUnavailable, match="cannot store the attempt count"):
        job_store.begin_attempt(spec)
    assert not (tmp_path / VID).exists()


def test_attempts_count_up_and_end_clears_them(tmp_path: Path) -> None:
    spec = job(tmp_path)
    job_store.begin_attempt(spec)
    job_store.begin_attempt(spec)
    attempt = job_store.result_path(spec).with_suffix(".attempt")
    assert (attempt.read_bytes(), job_store.interrupted_runs(spec)) == (b"2", 2)
    assert sorted(p.name for p in attempt.parent.iterdir()) == [attempt.name]
    job_store.end_attempt(spec)
    assert job_store.interrupted_runs(spec) == 0
