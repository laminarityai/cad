from base64 import b64decode
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final

from pydantic import Field, TypeAdapter, ValidationError

from cad.sandbox import container
from cad.sandbox.bodies import read_bodies
from cad.sandbox.container import Attended, ContainerState, Job, TooMuchOutput
from cad.sandbox.outcome import (
    BuildFailed,
    Built,
    Failure,
    NoResult,
    OutOfMemory,
    TimedOut,
    read_areas,
)
from cad.sandbox.wire import Report

TEXT_CAP = 8 * 1024
CONTRACT = "assign the final shape to `result`"
RUNNER: Final = (Path(__file__).parent / "runner.py").read_text()

REPORT = TypeAdapter[Report](Annotated[Report, Field(discriminator="kind")])


@dataclass(frozen=True, slots=True)
class Artifacts:
    brep: bytes
    built: Built


@dataclass(frozen=True, slots=True)
class Run:
    verdict: Artifacts | Failure
    output: str


def encode_code(code: str) -> bytes:
    return code.encode("utf-8", "surrogatepass")


def build_job(code: str, image_id: str, wall_seconds: int) -> Job:
    command = ("python", "-I", "-c", RUNNER, str(wall_seconds * container.CPUS))
    return Job("build", image_id, command, encode_code(code), wall_seconds=wall_seconds)


def build(code: str, image_id: str, *, wall_seconds: int = container.WALL_SECONDS) -> Run:
    job = build_job(code, image_id, wall_seconds)
    ran = container.run(job)
    return Run(classify(ran.attended, ran.state, job), ran.attended.output)


def classify(seen: Attended, state: ContainerState, job: Job) -> Artifacts | Failure:
    """Only the host's own kill means TimedOut. Exit codes 137 and 152 can come from the variant
    signalling itself or its `timeout` parent, and RLIMIT_CPU allows CPUS times the wall clock, so
    it cannot fire before the host's deadline.
    """
    if seen.killed_at_deadline:
        return TimedOut(limit_seconds=job.wall_seconds)
    if isinstance(seen.report, TooMuchOutput):
        if state.OOMKilled:
            return OutOfMemory(limit_mb=job.memory_mb)
        return died(f"the build sent more than {container.REPORT_CAP // 2**20} MiB of output")
    claimed = reported(seen.report) if state.ExitCode == 0 and seen.report else None
    if claimed is not None:
        return claimed
    if state.OOMKilled:
        return OutOfMemory(limit_mb=job.memory_mb)
    if state.ExitCode == 0 and seen.report:
        return died("the build sent a malformed result")
    return died(f"the build process exited with code {state.ExitCode} before it sent a result")


def died(error: str) -> BuildFailed:
    return BuildFailed(error=error, traceback="")


def reported(raw: bytes) -> Artifacts | Failure | None:
    try:
        report = REPORT.validate_json(raw, strict=True)
    except ValidationError:
        return None
    match report["kind"]:
        case "built":
            try:
                brep = b64decode(report["brep"], validate=True)
            except ValueError:
                return None
            bodies = read_bodies(report.get("bodies", []))
            if isinstance(bodies, str):
                return NoResult(reason=bodies)
            painted = read_areas(report.get("areas", []))
            return Artifacts(brep, painted.model_copy(update={"bodies": bodies}))
        case "build_failed":
            return BuildFailed(
                error=report["error"][:TEXT_CAP], traceback=report["traceback"][-TEXT_CAP:]
            )
        case "no_result":
            return NoResult(reason=f"the code never assigned `result`; {CONTRACT}")
        case "not_a_shape":
            found = report["found"][:TEXT_CAP]
            return NoResult(
                reason=f"`result` is of type {found}, not a build123d Shape; {CONTRACT}"
            )
