"""What one sandbox build ended as, in the host's terms.

The container's own claim is a `cad.sandbox.wire.Report`. Only `cad.sandbox.host.classify` turns
that claim, plus what Docker observed, into a `BuildOutcome`.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Outcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Built(_Outcome):
    """The code assigned a build123d Shape to `result`; result.brep and result.step are stored."""

    kind: Literal["built"] = "built"


class BuildFailed(_Outcome):
    """The code raised, or the build process died before it reported."""

    kind: Literal["build_failed"] = "build_failed"
    error: str
    traceback: str


class TimedOut(_Outcome):
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
    """One sandbox run, as build.json stores it. `output` is the tail of what the code printed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: BuildOutcome
    output: str


class SandboxUnavailable(Exception):
    """Docker, the sandbox image or the variant store cannot be used.

    Never raised for anything the variant code did. The message is one line a person can act on.
    """
