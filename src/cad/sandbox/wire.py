from typing import Literal, TypedDict


class BuiltReport(TypedDict):
    kind: Literal["built"]
    brep: str
    step: str


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
