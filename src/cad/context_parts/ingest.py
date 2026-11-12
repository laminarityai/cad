import base64
import binascii
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Final, Literal

from pydantic import ConfigDict, Field, TypeAdapter, ValidationError

from cad.checks.container.ingest import IngestWire, ReadAs
from cad.checks.report import IMAGE_TAG
from cad.frozen import Frozen
from cad.sandbox import container, image, stage
from cad.sandbox.container import Job, Ran, TooMuchOutput
from cad.sandbox.outcome import SandboxUnavailable

ENTRY: Final = "cad.checks.container.ingest"
BOOT: Final = f"import sys; sys.path.insert(0, {stage.TARGET!r}); from {ENTRY} import main; main()"
SOURCES: Final = stage.read_sources(ENTRY)
REPORT: Final = TypeAdapter[IngestWire](Annotated[IngestWire, Field(discriminator="kind")])
INCHES_TO_MM: Final = 25.4
MAX_HOLES: Final = 64
MAX_FLATS: Final = 16
MAX_NAMES: Final = 64

type Vector = tuple[float, float, float]


class _Finite(Frozen):
    model_config = ConfigDict(allow_inf_nan=False)


class HoleFact(_Finite):
    """A round hole through or into one solid: concave cylindrical faces around one axis line
    that make a full turn, found by the same code the fea check uses for its anchors."""

    diameter_mm: float
    center: Vector
    axis: Vector
    solid: int


class FlatFact(_Finite):
    """One of the largest planar regions of one solid."""

    normal: Vector
    area_mm2: float
    centroid: Vector
    solid: int


class LeftOut(_Finite):
    """What the reader dropped from the file. `bodies` counts the solids and shells it held;
    `unreadable` counts those it dropped, an open shell or a solid that stayed invalid after
    the tolerance cap; `loose` counts faces, edges and vertices that were in no body."""

    bodies: int
    unreadable: int
    loose: int


class Facts(_Finite):
    """Measured by the analysis container. Shown to the person and the agent so they can
    recognise the part and build in its frame. No check reads them."""

    solids: int
    volume_mm3: float
    box_min: Vector
    box_max: Vector
    holes: tuple[HoleFact, ...] = ()
    flats: tuple[FlatFact, ...] = ()
    names: tuple[str, ...] = ()
    left_out: LeftOut | None = None


@dataclass(frozen=True, slots=True)
class Brep:
    """A variant's BREP. It is measured as it is, so the part id is cut from these bytes."""

    data: bytes


@dataclass(frozen=True, slots=True)
class StepFile:
    data: bytes


@dataclass(frozen=True, slots=True)
class StlFile:
    data: bytes
    unit: Literal["mm", "in"]


type Source = Brep | StepFile | StlFile


@dataclass(frozen=True, slots=True)
class Ingested:
    """The facts and the BREP the checks and the build read: the variant's own bytes, or the
    solids the container kept from a file."""

    facts: Facts
    brep: bytes


@dataclass(frozen=True, slots=True)
class NotAPart:
    reason: str


type Ingest = Callable[[Source], Ingested | NotAPart]


def ingest(source: Source) -> Ingested | NotAPart:
    """Reads the part in the analysis image, under the limits of a check job. Raises
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
    argv = ("python", "-I", "-c", BOOT, cpu_seconds)
    job = Job("check", image_id, argv, framed(source), (mount,))
    return judged(container.run(job), job, source)


def framed(source: Source) -> bytes:
    """One JSON header line that says how to read the bytes, then the bytes."""
    match source:
        case Brep():
            read_as: ReadAs = {"format": "brep", "scale": 1.0}
        case StepFile():
            read_as = {"format": "step", "scale": 1.0}
        case StlFile(unit=unit):
            read_as = {"format": "stl", "scale": INCHES_TO_MM if unit == "in" else 1.0}
    return json.dumps(read_as).encode() + b"\n" + source.data


def judged(ran: Ran, job: Job, source: Source) -> Ingested | NotAPart:
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
        facts = Facts.model_validate(
            {name: value for name, value in report.items() if name not in ("kind", "brep")}
        )
        if isinstance(source, Brep):
            return Ingested(facts, source.data)
        kept = report["brep"]
        if kept is None:
            return NotAPart("reading the part sent no BREP of the solids it kept")
        return Ingested(facts, base64.b64decode(kept, validate=True))
    except (ValidationError, binascii.Error):
        return NotAPart("reading the part sent a malformed report")
