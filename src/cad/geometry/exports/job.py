import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Final

from pydantic import Field, TypeAdapter, ValidationError

from cad.checks.report import IMAGE_TAG
from cad.geometry.container.export_wire import ExportReport
from cad.geometry.exports.model import Exported, ExportFailed
from cad.sandbox import container, image, stage
from cad.sandbox.container import Job, TooMuchOutput
from cad.sandbox.outcome import AREAS, Areas, SandboxUnavailable

ENTRY: Final = "cad.geometry.container.export"
WALL_SECONDS: Final = 120
SOURCES: Final = stage.read_sources(ENTRY)
BOOT: Final = f"import sys; sys.path.insert(0, {stage.TARGET!r}); from {ENTRY} import main; main()"
VERSION: Final = hashlib.sha256(json.dumps([IMAGE_TAG, SOURCES.digest]).encode()).hexdigest()[:12]
REPORT: Final = TypeAdapter[ExportReport](Annotated[ExportReport, Field(discriminator="kind")])


@dataclass(frozen=True, slots=True)
class Made:
    step: bytes
    stl: bytes
    threemf: bytes


@dataclass(frozen=True, slots=True)
class Ran:
    """`made` holds the files when the BREP was exported. `lasting` is false when the outcome says
    nothing about the BREP, such as a timeout, so it is not stored and the next read runs the job
    again."""

    read: Exported | ExportFailed
    lasting: bool
    made: Made | None = None


def key_of(brep_sha256: str, areas: Areas) -> str:
    """The BREP's sha256 when the build code coloured nothing, so an uncoloured BREP keeps one
    export however many variants built it. The STEP carries no area names, so a rename keeps
    the export."""
    if not areas:
        return brep_sha256
    painted = [[area.colour, list(area.faces)] for area in areas]
    return hashlib.sha256(json.dumps([brep_sha256, painted]).encode()).hexdigest()


def export(brep: bytes, key: str, areas: Areas) -> Ran:
    image_id = image.current_image(IMAGE_TAG)
    try:
        mount = stage.check_mount(SOURCES)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            "cannot stage the export sources", error, stage.STAGE_ROOT
        ) from error
    cpu_seconds = str(WALL_SECONDS * container.CPUS)
    painted = AREAS.dump_json(areas).decode()
    command = ("python", "-I", "-c", BOOT, cpu_seconds, str(container.REPORT_CAP), painted)
    ran = container.run(Job("check", image_id, command, brep, (mount,), WALL_SECONDS))

    def failed(reason: str, lasting: bool = False) -> Ran:
        return Ran(ExportFailed(key=key, version=VERSION, reason=reason), lasting)

    seen, state = ran.attended, ran.state
    if seen.killed_at_deadline:
        return failed(f"the export ran past {WALL_SECONDS} s and was killed")
    if isinstance(seen.report, TooMuchOutput):
        return failed(f"the files are over {container.REPORT_CAP // 2**20} MiB", lasting=True)
    if state.OOMKilled or state.ExitCode != 0 or not seen.report:
        return failed(f"the export container exited with code {state.ExitCode}")
    try:
        report = REPORT.validate_json(seen.report)
    except ValidationError as error:
        return failed(f"the export container sent a malformed report: {error.errors()[0]}")
    if report["kind"] != "exported":
        return failed(report["reason"], lasting=True)
    made = Made(
        step=base64.b64decode(report["step"]),
        stl=base64.b64decode(report["stl"]),
        threemf=base64.b64decode(report["threemf"]),
    )
    return Ran(Exported(key=key, version=VERSION), True, made)
