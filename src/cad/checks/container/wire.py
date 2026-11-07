from datetime import date
from typing import Literal, TypedDict


class SourceLiteral(TypedDict):
    url: str
    title: str
    page: str
    retrieved: date
    standard: str | None
    quote: str


class DensityKnown(TypedDict):
    kind: Literal["known"]
    kg_per_mm3: float


class DensityUnknown(TypedDict):
    kind: Literal["unknown"]
    reason: str


type DensityWire = DensityKnown | DensityUnknown


class RequestWire(TypedDict):
    density: DensityWire


class MeasuredWire(TypedDict):
    name: str
    magnitude: float
    unit: str


class FindingWire(TypedDict):
    verdict: Literal["pass", "fail", "unknown"]
    measured: list[MeasuredWire]
    reason: str


class ResultWire(FindingWire):
    id: str


class StepWritten(TypedDict):
    kind: Literal["written"]
    base64: str


class StepNotWritten(TypedDict):
    kind: Literal["missing"]
    reason: str


type StepWire = StepWritten | StepNotWritten


class CheckedReport(TypedDict):
    kind: Literal["checked"]
    results: list[ResultWire]
    step: StepWire
