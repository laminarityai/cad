import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Final

from pydantic import Field, TypeAdapter, ValidationError

from cad.checks.report import IMAGE_TAG
from cad.geometry.container.wire import TessellationReport
from cad.geometry.model import Tessellated, TessellationFailed
from cad.sandbox import container, image, stage
from cad.sandbox.container import Job, TooMuchOutput
from cad.sandbox.outcome import SandboxUnavailable

ENTRY: Final = "cad.geometry.container.tessellate"
WALL_SECONDS: Final = 60
SOURCES: Final = stage.read_sources(ENTRY)
BOOT: Final = f"import sys; sys.path.insert(0, {stage.TARGET!r}); from {ENTRY} import main; main()"
VERSION: Final = hashlib.sha256(json.dumps([IMAGE_TAG, SOURCES.digest]).encode()).hexdigest()[:12]
REPORT: Final = TypeAdapter[TessellationReport](
    Annotated[TessellationReport, Field(discriminator="kind")]
)


@dataclass(frozen=True, slots=True)
class Ran:
    """`lasting` is false when the outcome says nothing about the BREP, such as a timeout, so
    it is not stored and the next read runs the job again."""

    read: Tessellated | TessellationFailed
    lasting: bool


def tessellate(brep: bytes, brep_sha256: str) -> Ran:
    image_id = image.current_image(IMAGE_TAG)
    try:
        mount = stage.check_mount(SOURCES)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            "cannot stage the tessellation sources", error, stage.STAGE_ROOT
        ) from error
    cpu_seconds = str(WALL_SECONDS * container.CPUS)
    command = ("python", "-I", "-c", BOOT, cpu_seconds)
    ran = container.run(Job("check", image_id, command, brep, (mount,), WALL_SECONDS))

    def failed(reason: str, lasting: bool = False) -> Ran:
        return Ran(
            TessellationFailed(brep_sha256=brep_sha256, version=VERSION, reason=reason), lasting
        )

    seen, state = ran.attended, ran.state
    if seen.killed_at_deadline:
        return failed(f"the tessellation ran past {WALL_SECONDS} s and was killed")
    if isinstance(seen.report, TooMuchOutput):
        return failed(f"the mesh is over {container.REPORT_CAP // 2**20} MiB", lasting=True)
    if state.OOMKilled or state.ExitCode != 0 or not seen.report:
        return failed(f"the tessellation container exited with code {state.ExitCode}")
    try:
        report = REPORT.validate_json(seen.report)
    except ValidationError as error:
        return failed(f"the tessellation container sent a malformed mesh: {error.errors()[0]}")
    if report["kind"] == "unreadable":
        return failed(f"the BREP could not be tessellated: {report['reason']}", lasting=True)
    return Ran(Tessellated(brep_sha256=brep_sha256, version=VERSION, shapes=report["shapes"]), True)
