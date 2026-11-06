from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Outcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Built(_Outcome):
    """The build reported a shape for `result`; result.brep and result.step are stored."""

    kind: Literal["built"] = "built"


class BuildFailed(_Outcome):
    """The code raised, or the build process died before it reported."""

    kind: Literal["build_failed"] = "build_failed"
    error: str
    traceback: str


class TimedOut(_Outcome):
    """The build ran past its wall clock. Not stored, so the same code builds again next time."""

    kind: Literal["timed_out"] = "timed_out"
    limit_seconds: int


class OutOfMemory(_Outcome):
    kind: Literal["out_of_memory"] = "out_of_memory"
    limit_mb: int


class NoResult(_Outcome):
    """The code ran to the end, but `result` was missing or not a Shape.

    `reason` is written by the host and always names the contract.
    """

    kind: Literal["no_result"] = "no_result"
    reason: str


type Failure = BuildFailed | TimedOut | OutOfMemory | NoResult
type BuildOutcome = Annotated[Built | Failure, Field(discriminator="kind")]


class Build(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: BuildOutcome
    output: str


class SandboxUnavailable(Exception):
    pass
