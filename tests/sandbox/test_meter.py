from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from cad.sandbox import container, meter
from cad.sandbox.meter import AccountLimitReached, Kind, NoMeter, Reservation, charged, metered

JOB = container.Job(kind="build", image_id="sha256:none", command=("true",), stdin=b"")


@dataclass
class Ledger:
    cap_reached: bool = False
    reserved: list[tuple[Kind, float]] = field(default_factory=list[tuple[Kind, float]])
    settled: list[float] = field(default_factory=list[float])

    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        if self.cap_reached:
            raise AccountLimitReached(60, 60, datetime(2026, 11, 10, tzinfo=UTC))
        self.reserved.append((kind, ceiling_seconds))
        return Reservation(str(len(self.reserved)), "2026-11-09", ceiling_seconds)

    def settle(self, reservation: Reservation, seconds: float) -> None:
        del reservation
        self.settled.append(seconds)


@pytest.fixture
def docker_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def refuse(*args: object) -> object:
        calls.append(str(args[0]))
        raise container.SandboxUnavailable("docker is not running")

    monkeypatch.setattr(container, "attend", refuse)

    def docker(*args: str) -> None:
        calls.append(args[0])

    monkeypatch.setattr(container, "docker", docker)
    return calls


def test_a_capped_account_starts_no_container(docker_calls: list[str]) -> None:
    with metered(Ledger(cap_reached=True)), pytest.raises(AccountLimitReached, match="limit"):
        container.run(JOB)
    assert docker_calls == []


def test_a_container_is_reserved_at_its_ceiling_and_settled(docker_calls: list[str]) -> None:
    ledger = Ledger()
    with metered(ledger), pytest.raises(container.SandboxUnavailable):
        container.run(JOB)
    assert ledger.reserved == [("build", container.ceiling_seconds(JOB))]
    assert len(ledger.settled) == 1
    assert docker_calls[0].startswith("cad-build-")


def test_a_process_that_requires_a_meter_refuses_an_unmetered_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(meter, "_required", True)
    with pytest.raises(NoMeter), charged("check", 1):
        pass
