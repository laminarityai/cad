from typing import assert_never

import pint

from cad.loads.model import (
    Across,
    Along,
    AnyWay,
    Away,
    Axis,
    Curve,
    Direction,
    Each,
    EndOf,
    Facing,
    FarEnd,
    FlatEnd,
    Holes,
    InOneFlatFace,
    Into,
    LargestFlat,
    Load,
    LoadCase,
    OnFarthest,
    OnHoles,
    OnLargestFlat,
    OnOpposite,
    Support,
)
from cad.tables.materials import magnitude

AXIS_WORDS = {Axis.LONG: "the long axis", Axis.HOLE_AXIS: "the hole axis"}


def describe_case(case: LoadCase) -> str:
    """The words a person confirms. The server writes them from the terms, so no agent writes
    them and they say what the check runs."""
    return f"{_load(case.load)}, {_direction(case.load.direction)}; {_support(case.support)}"


def _amount(quantity: pint.Quantity, unit: str) -> str:
    return f"{magnitude(quantity, unit):g} {unit}"


def _holes(count: int, diameter: pint.Quantity | None) -> str:
    sized = "" if diameter is None else f" of {_amount(diameter, 'mm')}"
    return f"exactly {count} hole{'' if count == 1 else 's'}{sized}"


def _of(diameter: pint.Quantity | None) -> str:
    return "" if diameter is None else f" of {_amount(diameter, 'mm')}"


def _curve(curve: Curve, diameter: pint.Quantity | None) -> str:
    match curve:
        case Curve.HOLE:
            return f"hole{_of(diameter)}"
        case Curve.INNER_CURVE:
            return f"inner curved face{_of(diameter)}"
        case _:
            assert_never(curve)


def _one(curve: Curve, diameter: pint.Quantity | None) -> str:
    match curve:
        case Curve.HOLE:
            return f"the bore of one hole{_of(diameter)}"
        case Curve.INNER_CURVE:
            return f"one inner curved face{_of(diameter)}"
        case _:
            assert_never(curve)


def _middle(middle: bool) -> str:
    return "the middle of " if middle else ""


def _load(load: Load) -> str:
    force = _amount(load.force, "N")
    match load:
        case FarEnd():
            return f"{force} at the end farthest from the supports"
        case OnHoles(count=count, diameter=diameter):
            return f"{force} hung from {_holes(count, diameter)} that are not supports"
        case OnLargestFlat(middle=middle):
            return f"{force} on {_middle(middle)}its largest flat face"
        case OnOpposite(middle=middle):
            return f"{force} on {_middle(middle)}the flat face across the gap from the supports"
        case OnFarthest(curve=curve, diameter=diameter):
            return f"{force} on the {_curve(curve, diameter)} farthest from the supports"
        case _:
            assert_never(load)


def _direction(direction: Direction) -> str:
    match direction:
        case Along(axis=axis):
            return f"along {AXIS_WORDS[axis]}"
        case Across(axis=axis):
            return f"in the worst direction across {AXIS_WORDS[axis]}"
        case AnyWay():
            return "in the worst direction"
        case Into():
            return "pressing into the face"
        case Away():
            return "pulling straight away from the supports"
        case _:
            assert_never(direction)


def _support(support: Support) -> str:
    match support:
        case Holes(count=count, diameter=diameter):
            return f"held by fixing the bores of {_holes(count, diameter)}"
        case LargestFlat():
            return "held by fixing its largest flat face"
        case FlatEnd():
            return "held by fixing the flat face at one end of its long axis"
        case EndOf(axis=axis):
            return f"held by fixing the flat face at one end of its {axis.value} axis"
        case Facing():
            return "held by fixing one of two flat faces that face each other across a gap"
        case Each(curve=curve, diameter=diameter):
            return f"held by fixing {_one(curve, diameter)}, whichever is worse"
        case InOneFlatFace(count=count, diameter=diameter):
            return (
                f"held by fixing the bores of {_holes(count, diameter)} that open on one flat "
                "face, whichever face is worse"
            )
        case _:
            assert_never(support)
