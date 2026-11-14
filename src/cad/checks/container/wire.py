from datetime import date
from typing import Literal, NotRequired, TypedDict


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


class BodyWire(TypedDict):
    """A body of the variant: the solids that share a name, as indices in the kernel's explorer
    order of the BREP, and the values its own material gives."""

    name: str
    solids: list[int]
    values: dict[str, ValueWire]


class RequestWire(TypedDict):
    checks: list[str]
    values: dict[str, ValueWire]
    """The material values of a variant with no named body. Empty when `bodies` is not."""
    load_cases: list["LoadCaseWire"]
    context_bytes: int
    """The last `context_bytes` bytes of stdin are the context part's BREP; 0 sends none."""
    bodies: list[BodyWire]
    """Empty for a variant of one unnamed body."""


class MeasuredWire(TypedDict):
    name: str
    magnitude: float
    unit: str


class FacesWire(TypedDict):
    """Faces of the variant that a load case fixed and loaded, as indices in the kernel's explorer
    order of the BREP the check read. The viewer numbers the same BREP's faces the same way, so an
    index names one face in both."""

    support: list[int]
    load: list[int]


class WhereWire(FacesWire):
    displacement: NotRequired[FacesWire]


class FindingWire(TypedDict):
    verdict: Literal["pass", "fail", "unknown"]
    measured: list[MeasuredWire]
    reason: str
    where: NotRequired[WhereWire]


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
    """The first message on the report channel. The STEP follows as a message of its own, so the
    results reach the host even when the container dies writing the STEP."""

    kind: Literal["checked"]
    results: list[ResultWire]


type PartAxisWire = Literal["middle", "short"]
type CurveWire = Literal["hole", "inner_curve"]


class HolesWire(TypedDict):
    kind: Literal["holes"]
    count: int
    diameter_mm: float | None


class LargestFlatWire(TypedDict):
    kind: Literal["largest_flat"]


class FlatEndWire(TypedDict):
    kind: Literal["flat_end"]


class EndOfWire(TypedDict):
    kind: Literal["end_of"]
    axis: PartAxisWire


class FacingWire(TypedDict):
    kind: Literal["facing"]


class EachWire(TypedDict):
    kind: Literal["each"]
    curve: CurveWire
    diameter_mm: float | None


class InOneFlatFaceWire(TypedDict):
    kind: Literal["in_one_flat_face"]
    count: int
    diameter_mm: float | None


type SupportWire = (
    HolesWire
    | LargestFlatWire
    | FlatEndWire
    | EndOfWire
    | FacingWire
    | EachWire
    | InOneFlatFaceWire
)
type AxisWire = Literal["long", "hole_axis"]


class AlongWire(TypedDict):
    kind: Literal["along"]
    axis: AxisWire


class AcrossWire(TypedDict):
    kind: Literal["across"]
    axis: AxisWire


class AnyWayWire(TypedDict):
    kind: Literal["any"]


class IntoWire(TypedDict):
    kind: Literal["into"]


class AwayWire(TypedDict):
    kind: Literal["away"]


type DirectionWire = AlongWire | AcrossWire | AnyWayWire | IntoWire | AwayWire


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


class OnLargestFlatWire(TypedDict):
    kind: Literal["on_largest_flat"]
    middle: bool
    force_n: float
    direction: DirectionWire


class OnOppositeWire(TypedDict):
    kind: Literal["on_opposite"]
    middle: bool
    force_n: float
    direction: DirectionWire


class OnFarthestWire(TypedDict):
    kind: Literal["on_farthest"]
    curve: CurveWire
    diameter_mm: float | None
    force_n: float
    direction: DirectionWire


type LoadWire = FarEndWire | OnHolesWire | OnLargestFlatWire | OnOppositeWire | OnFarthestWire


class LoadCaseWire(TypedDict):
    support: SupportWire
    load: LoadWire
