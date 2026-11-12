import hashlib
import json
from enum import StrEnum
from typing import Annotated, Final, Literal, NewType, Self, assert_never

import pint
from pydantic import Field, model_validator

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


class PartAxis(StrEnum):
    MIDDLE = "middle"
    """The principal axis of second-largest spread."""
    SHORT = "short"
    """The principal axis of least spread. The long one stays the reviewed `flat_end`."""


class Curve(StrEnum):
    HOLE = "hole"
    """The bores of one hole."""
    INNER_CURVE = "inner_curve"
    """A concave cylindrical face that is not part of a hole."""


class EndOf(Frozen):
    """Fixed at the flat face across one end of the middle or short axis."""

    kind: Literal["end_of"] = "end_of"
    axis: PartAxis


class Facing(Frozen):
    """Fixed at one of two flat faces that face each other across a gap."""

    kind: Literal["facing"] = "facing"


class Each(Frozen):
    """Fixed at one hole or one inner curved face, of this diameter when given. Each one is a
    candidate, and the check keeps the worst."""

    kind: Literal["each"] = "each"
    curve: Curve
    diameter: Length | None = None


class InOneFlatFace(Frozen):
    """Fixed at exactly `count` holes that open on one flat face. Each such set is a candidate."""

    kind: Literal["in_one_flat_face"] = "in_one_flat_face"
    count: HoleCount
    diameter: Length | None = None


type Support = Annotated[
    Holes | LargestFlat | FlatEnd | EndOf | Facing | Each | InOneFlatFace,
    Field(discriminator="kind"),
]


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


class Into(Frozen):
    """Along the inward normal of the loaded flat face: a press."""

    kind: Literal["into"] = "into"


class Away(Frozen):
    """Along the line from the support's centroid to the load's centroid: a pull."""

    kind: Literal["away"] = "away"


type Direction = Annotated[Along | Across | AnyWay | Into | Away, Field(discriminator="kind")]


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


class OnLargestFlat(Frozen):
    """On the largest flat face, or on a disc at its middle."""

    kind: Literal["on_largest_flat"] = "on_largest_flat"
    middle: bool = False
    force: Force
    direction: Direction


class OnOpposite(Frozen):
    """On the flat face across the gap from a `Facing` support, or on a disc at its middle."""

    kind: Literal["on_opposite"] = "on_opposite"
    middle: bool = False
    force: Force
    direction: Direction


class OnFarthest(Frozen):
    """On the hole or inner curved face farthest from the supports, of this diameter when
    given."""

    kind: Literal["on_farthest"] = "on_farthest"
    curve: Curve
    diameter: Length | None = None
    force: Force
    direction: Direction


type Load = Annotated[
    FarEnd | OnHoles | OnLargestFlat | OnOpposite | OnFarthest, Field(discriminator="kind")
]

REVIEWED: Final = frozenset(
    {"holes", "largest_flat", "flat_end", "far_end", "on_holes", "along", "across", "any"}
)
"""The kinds of the reviewed phrases. A load case with any other kind is described."""


class LoadCase(Frozen):
    support: Support
    load: Load

    @property
    def described(self) -> bool:
        """True when the case uses a term beyond the reviewed phrases."""
        return not {self.support.kind, self.load.kind, self.load.direction.kind} <= REVIEWED

    @model_validator(mode="after")
    def _terms_name_something(self) -> Self:
        """The pairings that name nothing. Only a described case is held to the hole axis rule,
        so a reviewed case stored before it still reads."""
        load, support, direction = self.load, self.support, self.load.direction
        if isinstance(load, OnOpposite) and not isinstance(support, Facing):
            raise ValueError("on_opposite needs a facing support: the flat face across the gap")
        if isinstance(direction, Into) and not isinstance(load, OnLargestFlat | OnOpposite):
            raise ValueError("into presses on a flat face, so only on_largest_flat or on_opposite")
        through_holes = isinstance(support, Holes | InOneFlatFace) or (
            isinstance(support, Each) and support.curve is Curve.HOLE
        )
        on_hole_axis = isinstance(direction, Along | Across) and direction.axis is Axis.HOLE_AXIS
        if self.described and on_hole_axis and not through_holes:
            raise ValueError("the hole_axis needs a support through holes")
        return self

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


def _support_wire(support: Support) -> SupportWire:
    match support:
        case Holes(count=count, diameter=diameter):
            return {"kind": "holes", "count": count, "diameter_mm": _millimetres(diameter)}
        case LargestFlat():
            return {"kind": "largest_flat"}
        case FlatEnd():
            return {"kind": "flat_end"}
        case EndOf(axis=axis):
            return {"kind": "end_of", "axis": axis.value}
        case Facing():
            return {"kind": "facing"}
        case Each(curve=curve, diameter=diameter):
            return {"kind": "each", "curve": curve.value, "diameter_mm": _millimetres(diameter)}
        case InOneFlatFace(count=count, diameter=diameter):
            return {
                "kind": "in_one_flat_face",
                "count": count,
                "diameter_mm": _millimetres(diameter),
            }
        case _:
            assert_never(support)


def _direction_wire(direction: Direction) -> DirectionWire:
    match direction:
        case Along(axis=axis):
            return {"kind": "along", "axis": axis.value}
        case Across(axis=axis):
            return {"kind": "across", "axis": axis.value}
        case AnyWay():
            return {"kind": "any"}
        case Into():
            return {"kind": "into"}
        case Away():
            return {"kind": "away"}
        case _:
            assert_never(direction)


def _load_wire(load: Load) -> LoadWire:
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
        case OnLargestFlat(middle=middle):
            return {
                "kind": "on_largest_flat",
                "middle": middle,
                "force_n": force_n,
                "direction": direction,
            }
        case OnOpposite(middle=middle):
            return {
                "kind": "on_opposite",
                "middle": middle,
                "force_n": force_n,
                "direction": direction,
            }
        case OnFarthest(curve=curve, diameter=diameter):
            return {
                "kind": "on_farthest",
                "curve": curve.value,
                "diameter_mm": _millimetres(diameter),
                "force_n": force_n,
                "direction": direction,
            }
        case _:
            assert_never(load)
