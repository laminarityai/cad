import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from cad.checks import report
from cad.geometry import job as mesh_job
from cad.geometry.exports import job, store
from cad.geometry.exports.lane import Exports
from cad.geometry.exports.model import Exported, ExportFailed, ExportPending
from cad.records import files
from cad.sandbox.meter import Kind, Reservation, charged, metered
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants import entry
from cad.variants.entry import Entry, VariantId

BREP = b"CASCADE Topology V3, a part\n"
SHA = hashlib.sha256(BREP).hexdigest()
HELD = Entry(VariantId("0123456789abcdef"), Path("/nowhere"), BREP, SHA)
MADE = job.Made(step=b"step", stl=b"stl", threemf=b"3mf")
EXPORTED = Exported(brep_sha256=SHA, version=job.VERSION)
NEW_CODE = (
    "cad/geometry/exports/",
    "cad/geometry/container/export",
    "cad/operations/exports.py",
    "cad/geometry/flights.py",
)


def made() -> job.Ran:
    return job.Ran(EXPORTED, True, MADE)


def failed(reason: str, lasting: bool) -> job.Ran:
    return job.Ran(ExportFailed(brep_sha256=SHA, version=job.VERSION, reason=reason), lasting)


class Gated:
    def __init__(self, ran: job.Ran) -> None:
        self.ran = ran
        self.calls = 0
        self.gate = threading.Event()

    def __call__(self, brep: bytes, brep_sha256: str) -> job.Ran:
        assert (brep, brep_sha256) == (BREP, SHA)
        self.calls += 1
        self.gate.wait(5)
        return self.ran


def test_a_read_while_the_job_runs_is_pending_and_starts_no_second_job_then_it_is_ready(
    tmp_path: Path,
) -> None:
    run = Gated(made())
    lane = Exports(run)
    assert lane.read(tmp_path, HELD) == ExportPending(brep_sha256=SHA)
    assert lane.read(tmp_path, HELD) == ExportPending(brep_sha256=SHA)
    run.gate.set()
    assert lane.read(tmp_path, HELD, wait_seconds=5) == EXPORTED
    assert run.calls == 1
    assert [store.read_file(tmp_path, SHA, one) for one in ("step", "stl", "3mf")] == [
        b"step",
        b"stl",
        b"3mf",
    ]


def test_a_read_that_missed_the_record_just_before_the_job_stored_it_starts_no_second_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Gated(made())
    run.gate.set()
    lane = Exports(run)
    assert lane.read(tmp_path, HELD, wait_seconds=5) == EXPORTED
    real, missed = store.read, [None]

    def misses_once(root: Path, brep_sha256: str) -> Exported | ExportFailed | None:
        return missed.pop() if missed else real(root, brep_sha256)

    monkeypatch.setattr(store, "read", misses_once)
    assert lane.read(tmp_path, HELD, wait_seconds=5) == EXPORTED
    assert run.calls == 1


def test_a_stored_export_is_read_with_no_job(tmp_path: Path) -> None:
    run = Gated(made())
    run.gate.set()
    Exports(run).read(tmp_path, HELD, wait_seconds=5)
    again = Gated(failed("never", lasting=True))
    assert Exports(again).read(tmp_path, HELD) == EXPORTED
    assert again.calls == 0


def test_a_lasting_failure_is_stored_with_its_reason_and_no_files(tmp_path: Path) -> None:
    run = Gated(failed("the files are over 64 MiB", lasting=True))
    run.gate.set()
    Exports(run).read(tmp_path, HELD, wait_seconds=5)
    assert store.read(tmp_path, SHA) == run.ran.read
    assert store.read_file(tmp_path, SHA, "step") is None


def test_an_outcome_that_says_nothing_about_the_brep_is_not_stored(tmp_path: Path) -> None:
    run = Gated(failed("timed out", lasting=False))
    run.gate.set()
    lane = Exports(run)
    assert lane.read(tmp_path, HELD, wait_seconds=5) == run.ran.read
    assert store.read(tmp_path, SHA) is None
    lane.read(tmp_path, HELD, wait_seconds=5)
    assert run.calls == 2


def test_the_record_is_written_last_so_a_write_that_dies_leaves_no_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = files.replace

    def dies_on_the_stl(path: Path, data: bytes) -> None:
        if path.suffix == ".stl":
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr(files, "replace", dies_on_the_stl)
    with pytest.raises(SandboxUnavailable):
        store.write(tmp_path, made())
    assert store.read(tmp_path, SHA) is None


def test_a_job_that_raises_raises_for_its_reader_and_the_next_read_retries(
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def down(brep: bytes, brep_sha256: str) -> job.Ran:
        calls.append(1)
        raise SandboxUnavailable("docker is not reachable")

    lane = Exports(down)
    for _ in range(2):
        with pytest.raises(SandboxUnavailable):
            lane.read(tmp_path, HELD, wait_seconds=5)
    assert len(calls) == 2


def test_the_store_names_a_brep_only_by_its_sha256_under_the_export_version(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="64 lowercase hex"):
        store.path(tmp_path, "../../etc/passwd", "step")
    assert store.path(tmp_path, SHA, "3mf") == tmp_path / "exports" / job.VERSION / f"{SHA}.3mf"


@dataclass
class Charges:
    kinds: list[Kind] = field(default_factory=list[Kind])

    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        self.kinds.append(kind)
        return Reservation(str(len(self.kinds)), "2026-11-09", ceiling_seconds)

    def settle(self, reservation: Reservation, seconds: float) -> None:
        del reservation, seconds


def test_a_first_export_is_charged_as_one_check_to_the_account_that_asked_and_a_stored_one_is_free(
    tmp_path: Path,
) -> None:
    def charging(brep: bytes, brep_sha256: str) -> job.Ran:
        with charged("check", 1):
            return made()

    charges = Charges()
    with metered(charges):
        lane = Exports(charging)
        lane.read(tmp_path, HELD, wait_seconds=5)
        lane.read(tmp_path, HELD, wait_seconds=5)
    assert charges.kinds == ["check"]


def test_the_export_job_is_versioned_apart_from_the_mesh_and_hashes_its_own_sources() -> None:
    assert job.VERSION != mesh_job.VERSION
    assert "cad/geometry/container/export.py" in job.SOURCES.files
    assert "cad/geometry/container/tessellate.py" not in job.SOURCES.files


def test_no_export_file_feeds_a_check_version_the_mesh_version_or_a_variant_id() -> None:
    """Adding the export edits no file that a check version, the mesh version or a variant id
    hashes, so every one of them keeps its value."""
    hashed = set(report.DEPENDENCIES.files) | set(mesh_job.SOURCES.files)
    hashed |= {f"{one.parent.name}/{one.name}" for one in trusted_files()}
    assert not [path for path in hashed if path.startswith(NEW_CODE)]


def trusted_files() -> list[Path]:
    return [path for directory in entry.TRUSTED_DIRECTORIES for path in directory.glob("*.py")]
