import logging
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, Field, Strict, StringConstraints, TypeAdapter, ValidationError

from cad.errors import Unavailable
from cad.frozen import Frozen

LOG = logging.getLogger(__name__)
MAX_AREAS: Final = 16
MAX_AREA_FACES: Final = 10_000
# The export container takes the areas as one argument, and Linux caps one at 128 KiB.
MAX_FACE_NUMBER: Final = 2**24
MAX_DROPPED_CHARS: Final = 200

type AreaName = Annotated[str, Strict(), StringConstraints(pattern=r"^[^\x00-\x1f\x7f]{1,60}$")]
type Colour = Annotated[str, Strict(), StringConstraints(pattern=r"^#[0-9a-f]{6}$")]
type FaceNumber = Annotated[int, Strict(), Field(ge=0, lt=MAX_FACE_NUMBER)]


class Area(Frozen):
    """A name and a colour that the build code gave a set of the variant's faces, numbered as
    the BREP numbers them. It is how the model looks: no check, table or verdict reads it."""

    name: AreaName
    colour: Colour
    faces: Annotated[tuple[FaceNumber, ...], Field(min_length=1)]


def _apart(areas: tuple[Area, ...]) -> tuple[Area, ...]:
    faces = [face for area in areas for face in area.faces]
    if len(faces) > MAX_AREA_FACES:
        raise ValueError(f"the areas name {len(faces)} faces, over {MAX_AREA_FACES}")
    if len(set(faces)) != len(faces):
        raise ValueError("a face is in two areas")
    return areas


type Areas = Annotated[tuple[Area, ...], Field(max_length=MAX_AREAS), AfterValidator(_apart)]
AREAS: Final = TypeAdapter[Areas](Areas)


class Built(Frozen):
    """`areas` are the colours the build code set, or none. `areas_dropped` says why the
    colours it set were not kept; the build stands either way."""

    kind: Literal["built"] = "built"
    areas: Areas = ()
    areas_dropped: str | None = None


class AreaCount(Frozen):
    """An area as the build tool tells the agent: its faces counted, not listed, so a
    coloured build stays short. The viewer reads the faces themselves."""

    name: AreaName
    colour: Colour
    face_count: int


class BuiltTold(Frozen):
    kind: Literal["built"] = "built"
    areas: tuple[AreaCount, ...] = ()
    areas_dropped: str | None = None


def read_areas(raw: object) -> Built:
    """`raw` is what the runner sent from inside the sandbox for the areas: untrusted JSON, or
    the error that stopped it reading them."""
    if isinstance(raw, str):
        return Built(areas_dropped=f"the colours could not be read: {raw}"[:MAX_DROPPED_CHARS])
    try:
        return Built(areas=AREAS.validate_python(raw))
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        said = f"the colours were dropped: {where or 'areas'}: {first['msg']}"
        return Built(areas_dropped=said[:MAX_DROPPED_CHARS])


def on_faces(areas: Areas, faces: int) -> Areas:
    """The areas, when every face they name is one of the `faces` the shape has, else none."""
    return areas if all(face < faces for area in areas for face in area.faces) else ()


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
type ToldOutcome = Annotated[BuiltTold | Failure, Field(discriminator="kind")]


def told(outcome: Built | Failure) -> BuiltTold | Failure:
    if not isinstance(outcome, Built):
        return outcome
    counted = (
        AreaCount(name=a.name, colour=a.colour, face_count=len(a.faces)) for a in outcome.areas
    )
    return BuiltTold(areas=tuple(counted), areas_dropped=outcome.areas_dropped)


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
