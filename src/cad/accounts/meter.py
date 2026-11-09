"""AccountMeter: container-seconds per account against a daily cap.

The only state is one file per account per UTC day, `<base>/usage/<YYYY-MM-DD>.jsonl`, so a restart
reads the same number. Each container appends two lines:

    {"op": "reserve", "id": "9f2c…", "seconds": 75}
    {"op": "settle", "id": "9f2c…", "seconds": 5.4}

A day's use is the settled seconds plus the ceiling of every reservation that has no settle line.
A server that dies while a container runs leaves that container charged at its ceiling, which
needs no repair. The read, the check and the append happen under an flock on the day's file, so
two servers on one home cannot both spend the last seconds.
"""

import fcntl
import logging
import os
import secrets
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from cad.sandbox.meter import AccountLimitReached, Kind, Reservation
from cad.sandbox.outcome import SandboxUnavailable

USAGE: Final = "usage"
LOG = logging.getLogger(__name__)


class Line(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["reserve", "settle"]
    id: str
    seconds: float
    kind: Kind | None = None


def used_seconds(lines: Iterable[Line]) -> float:
    reserved: dict[str, float] = {}
    settled: dict[str, float] = {}
    for line in lines:
        target = reserved if line.op == "reserve" else settled
        target.setdefault(line.id, line.seconds)
    return sum(settled.get(one, ceiling) for one, ceiling in reserved.items())


def parse_lines(raw: bytes) -> tuple[Line, ...]:
    """A torn last line, left by a crash during a write, is skipped."""
    parsed: list[Line] = []
    for text in raw.splitlines():
        try:
            parsed.append(Line.model_validate_json(text))
        except ValidationError:
            continue
    return tuple(parsed)


def _now() -> datetime:
    return datetime.now(UTC)


def _next_midnight(moment: datetime) -> datetime:
    return datetime.combine(moment.date() + timedelta(days=1), datetime.min.time(), UTC)


@dataclass(frozen=True, slots=True)
class AccountMeter:
    """`cap_seconds` None records use and never refuses: the stdio server's local account."""

    usage: Path
    cap_seconds: int | None
    now: Callable[[], datetime] = field(default=_now)

    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        moment = self.now()
        day = moment.date().isoformat()
        reservation = Reservation(secrets.token_hex(8), day, ceiling_seconds)
        line = Line(op="reserve", id=reservation.id, seconds=ceiling_seconds, kind=kind)
        try:
            with _locked(self._path(day)) as file:
                used = used_seconds(parse_lines(file.read()))
                if self.cap_seconds is not None and used >= self.cap_seconds:
                    raise AccountLimitReached(used, self.cap_seconds, _next_midnight(moment))
                _append(file, line)
        except OSError as error:
            raise SandboxUnavailable.hiding_host(
                "cannot read the account's usage", error, self.usage
            ) from error
        return reservation

    def settle(self, reservation: Reservation, seconds: float) -> None:
        line = Line(op="settle", id=reservation.id, seconds=round(seconds, 3))
        try:
            with _locked(self._path(reservation.day)) as file:
                _append(file, line)
        except OSError as error:
            LOG.error("cannot settle %s in %s, so it stays charged: %s", line, self.usage, error)

    def _path(self, day: str) -> Path:
        return self.usage / f"{day}.jsonl"


@contextmanager
def _locked(path: Path) -> Generator[BinaryIO]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        file.seek(0)
        yield file


def _append(file: BinaryIO, line: Line) -> None:
    """A torn last line is ended first, so it cannot swallow this one."""
    end = file.seek(0, os.SEEK_END)
    torn = end > 0 and file.seek(end - 1) >= 0 and file.read(1) != b"\n"
    file.write((b"\n" if torn else b"") + line.model_dump_json(exclude_none=True).encode() + b"\n")
    file.flush()
