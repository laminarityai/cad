import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from cad.geometry import job, store
from cad.geometry.lane import Tessellations
from cad.geometry.model import TessellationFailed, TessellationPending
from cad.sandbox.meter import Kind, Reservation, charged, metered
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants.entry import Entry, VariantId

BREP = b"CASCADE Topology V3, a part\n"
SHA = hashlib.sha256(BREP).hexdigest()
HELD = Entry(VariantId("0123456789abcdef"), Path("/nowhere"), BREP, SHA)


def failed(reason: str, lasting: bool) -> job.Ran:
    return job.Ran(TessellationFailed(brep_sha256=SHA, version=job.VERSION, reason=reason), lasting)


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


def test_a_read_while_the_job_runs_is_pending_and_starts_no_second_job(tmp_path: Path) -> None:
    run = Gated(failed("unreadable", lasting=True))
    lanes = Tessellations(run)
    assert lanes.read(tmp_path, HELD) == TessellationPending(brep_sha256=SHA)
    assert lanes.read(tmp_path, HELD) == TessellationPending(brep_sha256=SHA)
    run.gate.set()
    assert lanes.read(tmp_path, HELD, wait_seconds=5) == run.ran.read
    assert run.calls == 1


def test_a_lasting_outcome_is_stored_and_read_with_no_job(tmp_path: Path) -> None:
    run = Gated(failed("unreadable", lasting=True))
    run.gate.set()
    Tessellations(run).read(tmp_path, HELD, wait_seconds=5)
    again = Gated(failed("never", lasting=True))
    assert Tessellations(again).read(tmp_path, HELD) == run.ran.read
    assert again.calls == 0
    assert store.path(tmp_path, SHA).is_file()


def test_an_outcome_that_says_nothing_about_the_brep_is_not_stored(tmp_path: Path) -> None:
    run = Gated(failed("timed out", lasting=False))
    run.gate.set()
    lanes = Tessellations(run)
    assert lanes.read(tmp_path, HELD, wait_seconds=5) == run.ran.read
    assert store.read(tmp_path, SHA) is None
    lanes.read(tmp_path, HELD, wait_seconds=5)
    assert run.calls == 2


def test_a_job_that_raises_raises_for_its_reader_and_the_next_read_retries(
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def down(brep: bytes, brep_sha256: str) -> job.Ran:
        calls.append(1)
        raise SandboxUnavailable("docker is not reachable")

    lanes = Tessellations(down)
    for _ in range(2):
        with pytest.raises(SandboxUnavailable):
            lanes.read(tmp_path, HELD, wait_seconds=5)
    assert len(calls) == 2


def test_the_store_names_a_brep_only_by_its_sha256(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="64 lowercase hex"):
        store.path(tmp_path, "../../etc/passwd")
    assert store.path(tmp_path, SHA) == tmp_path / job.VERSION / f"{SHA}.json"


@dataclass
class Charges:
    kinds: list[Kind] = field(default_factory=list[Kind])

    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        self.kinds.append(kind)
        return Reservation(str(len(self.kinds)), "2026-11-09", ceiling_seconds)

    def settle(self, reservation: Reservation, seconds: float) -> None:
        del reservation, seconds


def test_a_tessellation_is_charged_to_the_account_that_asked(tmp_path: Path) -> None:
    ran = failed("unreadable", lasting=True)

    def charging(brep: bytes, brep_sha256: str) -> job.Ran:
        with charged("check", 1):
            return ran

    charges = Charges()
    with metered(charges):
        assert Tessellations(charging).read(tmp_path, HELD, wait_seconds=5) == ran.read
    assert charges.kinds == ["check"]
