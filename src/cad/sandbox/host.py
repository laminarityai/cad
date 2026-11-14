import json
from base64 import b64decode
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, TypeAdapter, ValidationError

from cad.checks.report import IMAGE_TAG, Request, build_request, parse
from cad.checks.result import CheckRun, StepMissing, StepStored
from cad.sandbox import container, image, stage
from cad.sandbox.container import Attended, ContainerState, Job, TooMuchOutput
from cad.sandbox.outcome import (
    BuildFailed,
    Built,
    Failure,
    NoResult,
    OutOfMemory,
    SandboxUnavailable,
    TimedOut,
    read_areas,
)
from cad.sandbox.wire import Report
from cad.tables.materials import TABLE_PATH, MaterialsTable, load_materials
from cad.variants import entry

TEXT_CAP = 8 * 1024
CONTRACT = "assign the final shape to `result`"

REPORT = TypeAdapter[Report](Annotated[Report, Field(discriminator="kind")])


@dataclass(frozen=True, slots=True)
class Artifacts:
    brep: bytes
    built: Built


@dataclass(frozen=True, slots=True)
class Run:
    verdict: Artifacts | Failure
    output: str


def build_job(code: str, image_id: str, wall_seconds: int) -> Job:
    command = ("python", "-I", "-c", stage.RUNNER, str(wall_seconds * container.CPUS))
    return Job("build", image_id, command, entry.encode_code(code), wall_seconds=wall_seconds)


def build(code: str, image_id: str, *, wall_seconds: int = container.WALL_SECONDS) -> Run:
    job = build_job(code, image_id, wall_seconds)
    ran = container.run(job)
    return Run(classify(ran.attended, ran.state, job), ran.attended.output)


def check_job(brep: bytes, image_id: str, request: Request, wall_seconds: int) -> Job:
    cpu_seconds = str(wall_seconds * container.CPUS)
    report_cap = str(container.REPORT_CAP)
    command = ("python", "-I", "-c", stage.BOOT, cpu_seconds, json.dumps(request.wire), report_cap)
    return Job("check", image_id, command, brep, (stage.check_mount(),), wall_seconds)


def run_checks(
    variant_id: str,
    material_key: str,
    root: Path = entry.VARIANTS_ROOT,
    *,
    wall_seconds: int = container.WALL_SECONDS,
) -> CheckRun:
    """Raises
        UnknownVariant       not 16 lowercase hex digits, or no such entry
        StaleVariant         the entry does not re-derive to its own id: stored before the fix for
                             issue #6, under another image, or edited. `OutdatedVariant` when
                             its signed record pins the code an older sandbox stored
        NotBuilt             the stored outcome is not `built`
        SandboxUnavailable   Docker, the image, the store, or the materials table is unusable
    Returns a `CheckRun` with one result per check, always. A container that times out, runs out of
    memory, dies, or sends a malformed report yields `unknown` results, never an exception and
    never `pass`. A STEP too large for the report is left out, and the results stand. A material
    key that is not in the table makes `mass` `unknown`.
    """
    request = build_request(material_key, materials_table())
    return run_request(variant_id, request, root, wall_seconds=wall_seconds)


def run_request(
    variant_id: str,
    request: Request,
    root: Path = entry.VARIANTS_ROOT,
    *,
    wall_seconds: int = container.WALL_SECONDS,
) -> CheckRun:
    held = entry.open_entry(root, variant_id, image.image_tag(image.BUILD))
    image_id = image.current_image(IMAGE_TAG)
    try:
        job = check_job(held.brep, image_id, request, wall_seconds)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot stage the check sources for variant {held.id}", error, stage.STAGE_ROOT
        ) from error
    ran = container.run(job)
    parsed = parse(ran, request, job)
    try:
        step = (
            parsed.step
            if isinstance(parsed.step, StepMissing)
            else StepStored(sha256=held.attach_step(parsed.step))
        )
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot store the STEP of variant {held.id}", error, held.directory / entry.STEP
        ) from error
    return CheckRun(
        variant_id=held.id,
        material_key=request.material_key,
        table_version=request.table_version,
        check_image_tag=IMAGE_TAG,
        check_image_digest=image_id,
        brep_sha256=held.brep_sha256,
        step=step,
        results=parsed.results,
        timed_out=parsed.timed_out,
    )


def materials_table() -> MaterialsTable:
    try:
        return load_materials()
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise SandboxUnavailable.hiding_host(
            "cannot read the materials table", error, TABLE_PATH
        ) from error


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
            return Artifacts(brep, read_areas(report.get("areas", [])))
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
