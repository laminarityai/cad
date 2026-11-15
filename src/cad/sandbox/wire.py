from typing import Literal, NotRequired, TypedDict


class PlacementListing(TypedDict):
    at: list[float]
    rotate: list[float]


class PartListing(TypedDict):
    """A supplied part the build reads. Its BREP is `size` bytes of stdin after the code, the
    parts in the order listed."""

    id: str
    size: int
    placements: list[PlacementListing]


class AreaReport(TypedDict):
    name: str
    colour: str
    faces: list[int]


class BodyReport(TypedDict):
    name: str
    solids: list[int]


class BuiltReport(TypedDict):
    """`areas` is what the runner read off the shape, or the error that stopped it; the host
    parses it apart from the rest, so a bad list never fails the build. `bodies` is the name of
    each solid, or the error that stopped the runner reading them; a bad one refuses the build."""

    kind: Literal["built"]
    brep: str
    areas: NotRequired[object]
    bodies: NotRequired[object]


class FailedReport(TypedDict):
    kind: Literal["build_failed"]
    error: str
    traceback: str


class NoResultReport(TypedDict):
    kind: Literal["no_result"]


class NotAShapeReport(TypedDict):
    kind: Literal["not_a_shape"]
    found: str


type Report = BuiltReport | FailedReport | NoResultReport | NotAShapeReport
