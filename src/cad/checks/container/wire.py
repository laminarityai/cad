from datetime import date
from typing import Literal, TypedDict


class SourceLiteral(TypedDict):
    url: str
    title: str
    page: str
    retrieved: date
    standard: str | None
    quote: str


class ValueKnown(TypedDict):
    kind: Literal["known"]
    magnitude: float


class ValueUnknown(TypedDict):
    kind: Literal["unknown"]
    reason: str


type ValueWire = ValueKnown | ValueUnknown


class RequestWire(TypedDict):
    checks: list[str]
    values: dict[str, ValueWire]
    load_cases: list["LoadCaseWire"]
    context_bytes: int
    """The last `context_bytes` bytes of stdin are the context part's BREP; 0 sends none."""


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


class HolesWire(TypedDict):
    kind: Literal["holes"]
    count: int
    diameter_mm: float | None


class LargestFlatWire(TypedDict):
    kind: Literal["largest_flat"]


class FlatEndWire(TypedDict):
    kind: Literal["flat_end"]


type SupportWire = HolesWire | LargestFlatWire | FlatEndWire
type AxisWire = Literal["long", "hole_axis"]


class AlongWire(TypedDict):
    kind: Literal["along"]
    axis: AxisWire


class AcrossWire(TypedDict):
    kind: Literal["across"]
    axis: AxisWire


class AnyWayWire(TypedDict):
    kind: Literal["any"]


type DirectionWire = AlongWire | AcrossWire | AnyWayWire


class FarEndWire(TypedDict):
    kind: Literal["far_end"]
    force_n: float
    direction: DirectionWire


class OnHolesWire(TypedDict):
    kind: Literal["on_holes"]
    count: int
    diameter_mm: float | None
    force_n: float
    direction: DirectionWire


type LoadWire = FarEndWire | OnHolesWire


class LoadCaseWire(TypedDict):
    support: SupportWire
    load: LoadWire
