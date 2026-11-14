from typing import Literal, NotRequired, TypedDict


class AreaReport(TypedDict):
    name: str
    colour: str
    faces: list[int]


class BuiltReport(TypedDict):
    """`areas` is what the runner read off the shape, or the error that stopped it; the host
    parses it apart from the rest, so a bad list never fails the build."""

    kind: Literal["built"]
    brep: str
    areas: NotRequired[object]


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
