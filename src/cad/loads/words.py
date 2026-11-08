from typing import assert_never

import pint

from cad.loads.model import (
    Across,
    Along,
    AnyWay,
    Axis,
    FarEnd,
    FlatEnd,
    Holes,
    LargestFlat,
    LoadCase,
    OnHoles,
)
from cad.tables.materials import magnitude

AXIS_WORDS = {Axis.LONG: "the long axis", Axis.HOLE_AXIS: "the hole axis"}


def describe_case(case: LoadCase) -> str:
    return f"{_load(case.load)}, {_direction(case.load.direction)}; {_support(case.support)}"


def _amount(quantity: pint.Quantity, unit: str) -> str:
    return f"{magnitude(quantity, unit):g} {unit}"


def _holes(count: int, diameter: pint.Quantity | None) -> str:
    sized = "" if diameter is None else f" of {_amount(diameter, 'mm')}"
    return f"exactly {count} hole{'' if count == 1 else 's'}{sized}"


def _load(load: FarEnd | OnHoles) -> str:
    force = _amount(load.force, "N")
    match load:
        case FarEnd():
            return f"{force} at the end farthest from the supports"
        case OnHoles(count=count, diameter=diameter):
            return f"{force} hung from {_holes(count, diameter)} that are not supports"
        case _:
            assert_never(load)


def _direction(direction: Along | Across | AnyWay) -> str:
    match direction:
        case Along(axis=axis):
            return f"along {AXIS_WORDS[axis]}"
        case Across(axis=axis):
            return f"in the worst direction across {AXIS_WORDS[axis]}"
        case AnyWay():
            return "in the worst direction"
        case _:
            assert_never(direction)


def _support(support: Holes | LargestFlat | FlatEnd) -> str:
    match support:
        case Holes(count=count, diameter=diameter):
            return f"held by fixing the bores of {_holes(count, diameter)}"
        case LargestFlat():
            return "held by fixing its largest flat face"
        case FlatEnd():
            return "held by fixing the flat face at one end of its long axis"
        case _:
            assert_never(support)
