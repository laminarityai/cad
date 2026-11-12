"""The terms a load case is written in. `anchors.resolve` reads only these, and `of_wire` parses
the reviewed phrases the host sends."""

from dataclasses import dataclass
from typing import Literal, assert_never

from cad.checks.container.wire import DirectionWire, LoadCaseWire, LoadWire, SupportWire

type Axis = Literal["long", "hole_axis"]


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


type Support = Holes | LargestFlat | FlatEnd


@dataclass(frozen=True, slots=True)
class FarEnd:
    pass


@dataclass(frozen=True, slots=True)
class OnHoles:
    count: int
    diameter_mm: float | None


type Load = FarEnd | OnHoles


@dataclass(frozen=True, slots=True)
class Along:
    axis: Axis


@dataclass(frozen=True, slots=True)
class Across:
    axis: Axis


@dataclass(frozen=True, slots=True)
class AnyWay:
    pass


type Direction = Along | Across | AnyWay


@dataclass(frozen=True, slots=True)
class LoadCase:
    support: Support
    load: Load
    direction: Direction


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
        case _:
            assert_never(wire["kind"])


def _load(wire: LoadWire) -> Load:
    match wire["kind"]:
        case "far_end":
            return FarEnd()
        case "on_holes":
            return OnHoles(wire["count"], wire["diameter_mm"])
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
        case _:
            assert_never(wire["kind"])
