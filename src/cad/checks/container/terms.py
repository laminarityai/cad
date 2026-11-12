"""The terms a load case is written in. `anchors.resolve` reads only these, and `of_wire` parses
every term the host sends: the reviewed phrases and the described terms."""

from dataclasses import dataclass
from typing import Final, Literal, assert_never

from cad.checks.container.wire import DirectionWire, LoadCaseWire, LoadWire, SupportWire

type Axis = Literal["long", "hole_axis"]
type PartAxis = Literal["middle", "short"]
type Curve = Literal["hole", "inner_curve"]


@dataclass(frozen=True, slots=True)
class Holes:
    count: int
    diameter_mm: float | None


@dataclass(frozen=True, slots=True)
class LargestFlat:
    pass


@dataclass(frozen=True, slots=True)
class FlatEnd:
    pass


@dataclass(frozen=True, slots=True)
class EndOf:
    """The flat face across one end of the part's middle or short axis."""

    axis: PartAxis


@dataclass(frozen=True, slots=True)
class Facing:
    """One of two flat faces that face each other across a gap."""


@dataclass(frozen=True, slots=True)
class Each:
    """One hole or one inner curve, of this diameter when given. Each one is a candidate."""

    curve: Curve
    diameter_mm: float | None


@dataclass(frozen=True, slots=True)
class InOneFlatFace:
    """Exactly `count` holes that open on one flat face. Each such set is a candidate."""

    count: int
    diameter_mm: float | None


type Support = Holes | LargestFlat | FlatEnd | EndOf | Facing | Each | InOneFlatFace


@dataclass(frozen=True, slots=True)
class FarEnd:
    pass


@dataclass(frozen=True, slots=True)
class OnHoles:
    count: int
    diameter_mm: float | None


@dataclass(frozen=True, slots=True)
class OnLargestFlat:
    middle: bool
    """On a disc at the middle of the face, not the whole face."""


@dataclass(frozen=True, slots=True)
class OnOpposite:
    """On the flat face across the gap from a `Facing` support."""

    middle: bool


@dataclass(frozen=True, slots=True)
class OnFarthest:
    """On the hole or inner curve farthest from the supports, of this diameter when given."""

    curve: Curve
    diameter_mm: float | None


type Load = FarEnd | OnHoles | OnLargestFlat | OnOpposite | OnFarthest


@dataclass(frozen=True, slots=True)
class Along:
    axis: Axis


@dataclass(frozen=True, slots=True)
class Across:
    axis: Axis


@dataclass(frozen=True, slots=True)
class AnyWay:
    pass


@dataclass(frozen=True, slots=True)
class Into:
    """Along the inward normal of the loaded flat face: a press."""


@dataclass(frozen=True, slots=True)
class Away:
    """Along the line from the support's centroid to the load's centroid: a pull."""


type Direction = Along | Across | AnyWay | Into | Away

REVIEWED: Final = (Holes, LargestFlat, FlatEnd, FarEnd, OnHoles, Along, Across, AnyWay)


@dataclass(frozen=True, slots=True)
class LoadCase:
    support: Support
    load: Load
    direction: Direction

    @property
    def described(self) -> bool:
        """True when the case uses a term beyond the reviewed phrases."""
        return not all(
            isinstance(term, REVIEWED) for term in (self.support, self.load, self.direction)
        )


def of_wire(case: LoadCaseWire) -> LoadCase:
    load = case["load"]
    return LoadCase(_support(case["support"]), _load(load), _direction(load["direction"]))


def _support(wire: SupportWire) -> Support:
    match wire["kind"]:
        case "holes":
            return Holes(wire["count"], wire["diameter_mm"])
        case "largest_flat":
            return LargestFlat()
        case "flat_end":
            return FlatEnd()
        case "end_of":
            return EndOf(wire["axis"])
        case "facing":
            return Facing()
        case "each":
            return Each(wire["curve"], wire["diameter_mm"])
        case "in_one_flat_face":
            return InOneFlatFace(wire["count"], wire["diameter_mm"])
        case _:
            assert_never(wire["kind"])


def _load(wire: LoadWire) -> Load:
    match wire["kind"]:
        case "far_end":
            return FarEnd()
        case "on_holes":
            return OnHoles(wire["count"], wire["diameter_mm"])
        case "on_largest_flat":
            return OnLargestFlat(wire["middle"])
        case "on_opposite":
            return OnOpposite(wire["middle"])
        case "on_farthest":
            return OnFarthest(wire["curve"], wire["diameter_mm"])
        case _:
            assert_never(wire["kind"])


def _direction(wire: DirectionWire) -> Direction:
    match wire["kind"]:
        case "along":
            return Along(wire["axis"])
        case "across":
            return Across(wire["axis"])
        case "any":
            return AnyWay()
        case "into":
            return Into()
        case "away":
            return Away()
        case _:
            assert_never(wire["kind"])
