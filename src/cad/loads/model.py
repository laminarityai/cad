import hashlib
import json
from enum import StrEnum
from typing import Annotated, Final, Literal, NewType, assert_never

import pint
from pydantic import Field

from cad.checks.container.wire import (
    DirectionWire,
    LoadCaseWire,
    LoadWire,
    SupportWire,
)
from cad.checks.units import Force, Length
from cad.frozen import Frozen
from cad.tables.materials import magnitude

LoadCaseId = NewType("LoadCaseId", str)
UnitCaseKey = NewType("UnitCaseKey", str)
MAX_HOLES: Final = 12
type HoleCount = Annotated[int, Field(ge=1, le=MAX_HOLES)]


class Holes(Frozen):
    """Bolted or screwed through exactly `count` holes, of this bore diameter when given."""

    kind: Literal["holes"] = "holes"
    count: HoleCount
    diameter: Length | None = None


class LargestFlat(Frozen):
    """Glued down or sitting on its largest flat face."""

    kind: Literal["largest_flat"] = "largest_flat"


class FlatEnd(Frozen):
    """Fixed at the flat face across one end of its long axis."""

    kind: Literal["flat_end"] = "flat_end"


type Support = Annotated[Holes | LargestFlat | FlatEnd, Field(discriminator="kind")]


class Axis(StrEnum):
    LONG = "long"
    """The principal axis along which the solid's volume spreads furthest."""
    HOLE_AXIS = "hole_axis"
    """The common axis direction of the support holes, so only with a `Holes` support."""


class Along(Frozen):
    kind: Literal["along"] = "along"
    axis: Axis


class Across(Frozen):
    """Any direction in the plane normal to the axis."""

    kind: Literal["across"] = "across"
    axis: Axis


class AnyWay(Frozen):
    kind: Literal["any"] = "any"


type Direction = Annotated[Along | Across | AnyWay, Field(discriminator="kind")]


class FarEnd(Frozen):
    """At the end farthest from the supports."""

    kind: Literal["far_end"] = "far_end"
    force: Force
    direction: Direction


class OnHoles(Frozen):
    """Hangs from exactly `count` holes that are not supports."""

    kind: Literal["on_holes"] = "on_holes"
    count: HoleCount
    diameter: Length | None = None
    force: Force
    direction: Direction


type Load = Annotated[FarEnd | OnHoles, Field(discriminator="kind")]


class LoadCase(Frozen):
    support: Support
    load: Load

    @property
    def id(self) -> LoadCaseId:
        """The single name of this case, as a measure qualifier and on the wire."""
        return LoadCaseId(_digest(self.wire()))

    @property
    def unit_case(self) -> UnitCaseKey:
        """The case without its force magnitude. Cases that differ only in magnitude share one
        set of unit solves."""
        wire = self.wire()
        return UnitCaseKey(
            _digest({"support": wire["support"], "load": {**wire["load"], "force_n": 1.0}})
        )

    def wire(self) -> LoadCaseWire:
        return {"support": _support_wire(self.support), "load": _load_wire(self.load)}


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def _millimetres(length: pint.Quantity | None) -> float | None:
    return None if length is None else magnitude(length, "mm")


def _support_wire(support: Holes | LargestFlat | FlatEnd) -> SupportWire:
    match support:
        case Holes(count=count, diameter=diameter):
            return {"kind": "holes", "count": count, "diameter_mm": _millimetres(diameter)}
        case LargestFlat():
            return {"kind": "largest_flat"}
        case FlatEnd():
            return {"kind": "flat_end"}
        case _:
            assert_never(support)


def _direction_wire(direction: Along | Across | AnyWay) -> DirectionWire:
    match direction:
        case Along(axis=axis):
            return {"kind": "along", "axis": axis.value}
        case Across(axis=axis):
            return {"kind": "across", "axis": axis.value}
        case AnyWay():
            return {"kind": "any"}
        case _:
            assert_never(direction)


def _load_wire(load: FarEnd | OnHoles) -> LoadWire:
    force_n = magnitude(load.force, "N")
    direction = _direction_wire(load.direction)
    match load:
        case FarEnd():
            return {"kind": "far_end", "force_n": force_n, "direction": direction}
        case OnHoles(count=count, diameter=diameter):
            return {
                "kind": "on_holes",
                "count": count,
                "diameter_mm": _millimetres(diameter),
                "force_n": force_n,
                "direction": direction,
            }
        case _:
            assert_never(load)
