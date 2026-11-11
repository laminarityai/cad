import logging
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field

from cad.errors import Unavailable
from cad.frozen import Frozen

LOG = logging.getLogger(__name__)


class Built(Frozen):
    kind: Literal["built"] = "built"


class BuildFailed(Frozen):
    """The code raised, or the build process died before it reported."""

    kind: Literal["build_failed"] = "build_failed"
    error: str
    traceback: str


class TimedOut(Frozen):
    """The build ran past its wall clock. Not stored, so the same code builds again next time."""

    kind: Literal["timed_out"] = "timed_out"
    limit_seconds: int


class OutOfMemory(Frozen):
    kind: Literal["out_of_memory"] = "out_of_memory"
    limit_mb: int


class NoResult(Frozen):
    """The code ran to the end, but `result` was missing or not a Shape.

    `reason` is written by the host and always names the contract.
    """

    kind: Literal["no_result"] = "no_result"
    reason: str


type Failure = BuildFailed | TimedOut | OutOfMemory | NoResult
type BuildOutcome = Annotated[Built | Failure, Field(discriminator="kind")]


class Build(Frozen):
    outcome: BuildOutcome
    output: str


class SandboxUnavailable(Unavailable):
    @classmethod
    def hiding_host(cls, message: str, error: Exception | str, path: Path | None = None) -> Self:
        LOG.error("%s%s: %s", message, "" if path is None else f" ({path})", error)
        if isinstance(error, str):
            return cls(message)
        return cls(f"{message}: {type(error).__name__}")
