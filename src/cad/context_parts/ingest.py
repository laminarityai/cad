from dataclasses import dataclass
from typing import Annotated, Final

from pydantic import ConfigDict, Field, TypeAdapter, ValidationError

from cad.checks.container.ingest import IngestWire
from cad.checks.report import IMAGE_TAG
from cad.frozen import Frozen
from cad.sandbox import container, image, stage
from cad.sandbox.container import Job, Ran, TooMuchOutput
from cad.sandbox.outcome import SandboxUnavailable

ENTRY: Final = "cad.checks.container.ingest"
BOOT: Final = f"import sys; sys.path.insert(0, {stage.TARGET!r}); from {ENTRY} import main; main()"
SOURCES: Final = stage.read_sources(ENTRY)
REPORT: Final = TypeAdapter[IngestWire](Annotated[IngestWire, Field(discriminator="kind")])


class Facts(Frozen):
    """Measured by the analysis container. Shown to the person and the agent so they can
    recognise the part and build in its frame. No check reads them."""

    model_config = ConfigDict(allow_inf_nan=False)

    solids: int
    volume_mm3: float
    box_min: tuple[float, float, float]
    box_max: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class NotAPart:
    reason: str


def ingest(brep: bytes) -> Facts | NotAPart:
    """Reads the BREP in the analysis image, under the limits of a check job. Raises
    `SandboxUnavailable` when Docker, the image or the stage is unusable. Anything the container
    does other than send a well-formed report is a `NotAPart` that says what happened."""
    image_id = image.current_image(IMAGE_TAG)
    try:
        mount = stage.check_mount(SOURCES)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            "cannot stage the ingest sources", error, stage.STAGE_ROOT
        ) from error
    cpu_seconds = str(container.WALL_SECONDS * container.CPUS)
    job = Job("check", image_id, ("python", "-I", "-c", BOOT, cpu_seconds), brep, (mount,))
    return judged(container.run(job), job)


def judged(ran: Ran, job: Job) -> Facts | NotAPart:
    seen, state = ran.attended, ran.state
    if seen.killed_at_deadline:
        return NotAPart(f"reading the part ran past {job.wall_seconds} s and was stopped")
    if state.OOMKilled:
        return NotAPart(f"reading the part ran out of memory ({job.memory_mb} MB)")
    if isinstance(seen.report, TooMuchOutput):
        return NotAPart("reading the part sent more output than a report holds")
    if state.ExitCode != 0:
        return NotAPart(f"reading the part exited with code {state.ExitCode} before it reported")
    try:
        report = REPORT.validate_json(seen.report, strict=True)
        if report["kind"] == "refused":
            return NotAPart(report["reason"])
        return Facts.model_validate(
            {name: value for name, value in report.items() if name != "kind"}
        )
    except ValidationError:
        return NotAPart("reading the part sent a malformed report")
