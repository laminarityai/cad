"""The one gate every container start passes.

`container.run` asks the meter bound to the current context for a reservation before
`docker run`, and settles it with the seconds the container ran. The operation adapter binds the
tenant's meter, so no function between an operation and `container.run` takes it as an argument,
and a container added later is metered without knowing it.
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from cad.sandbox.outcome import SandboxUnavailable

type Kind = Literal["build", "check"]


@dataclass(frozen=True, slots=True)
class Reservation:
    """Seconds held against an account until `settle` replaces them with the measured ones. `day`
    is the UTC day it is charged to, so a container that runs past midnight settles there."""

    id: str
    day: str
    ceiling_seconds: float


class AccountLimitReached(SandboxUnavailable):
    """The account's container-seconds for the day are spent, so no container started. It is a
    `SandboxUnavailable`, so every handler that already reports one reports this too."""

    def __init__(self, used_seconds: float, cap_seconds: int, resets_at: datetime) -> None:
        self.used_seconds = used_seconds
        self.cap_seconds = cap_seconds
        self.resets_at = resets_at
        super().__init__(
            f"the account limit is reached: {used_seconds:.0f} of {cap_seconds} container-seconds "
            f"used today, so nothing was started; it resets at {resets_at:%Y-%m-%d %H:%M} UTC"
        )


class NoMeter(RuntimeError):
    """A container was asked for outside `metered` in a process that requires a meter."""


class Meter(Protocol):
    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        """Raises `AccountLimitReached` when nothing is left of the day's cap."""
        ...

    def settle(self, reservation: Reservation, seconds: float) -> None: ...


_BOUND: ContextVar[Meter | None] = ContextVar("cad.meter", default=None)
_required = False


def require() -> None:
    """From now on a container started outside `metered` raises `NoMeter`. The HTTP server calls
    this at startup, so a path that loses the account's context fails instead of running free."""
    global _required
    _required = True


@contextmanager
def metered(meter: Meter) -> Generator[None]:
    """Binds `meter` for every container started in this context, including threads that run a
    copy of it, such as the check lanes' background worker."""
    token = _BOUND.set(meter)
    try:
        yield
    finally:
        _BOUND.reset(token)


@contextmanager
def charged(kind: Kind, ceiling_seconds: float) -> Generator[None]:
    """Reserves `ceiling_seconds` on the bound meter before the body runs, then settles the
    seconds it took. With no meter bound, outside the HTTP server, nothing is charged."""
    meter = _BOUND.get()
    if meter is None:
        if _required:
            raise NoMeter("a container was asked for outside any account's meter")
        yield
        return
    reservation = meter.reserve(kind, ceiling_seconds)
    started = time.monotonic()
    try:
        yield
    finally:
        meter.settle(reservation, time.monotonic() - started)
