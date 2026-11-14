"""A person's change to one requirement's number, typed on the confirmation page.

The page stores the typed text in the signed PageAnswer (`cad.confirmations.answers.Edit`). This
module turns that text into the requirement the person confirmed. The page runs it before it
records the answer, and the brief store runs it again on every read, so what checks read is
exactly what the person typed. Only the number changes: the kind and the brief span stay.

A plain hole's row takes a diameter, a tolerance, or both: "6 mm", "8 mm H7", "8 mm +/- 0.1 mm",
"H7" or "+/- 0.1 mm". What is not typed stays as proposed. A clearance hole of a fastener takes its
series: "close", "medium", "coarse", or "any" for the whole range.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, assert_never

import pint
from pydantic import ValidationError

from cad.briefs.holes import (
    ByClass,
    FastenerHoles,
    HoleFit,
    HoleTolerance,
    PlainHoles,
    PlusMinus,
)
from cad.briefs.model import (
    AgentLimit,
    ClosedSolid,
    Envelope,
    FitsWith,
    MadeOf,
    MaxClearance,
    MaxDeflection,
    MaxMass,
    MeasureLimit,
    MinClearance,
    MinMass,
    MinSafetyFactor,
    Requirement,
    Unchecked,
    amount,
    requirement_id,
)
from cad.briefs.words import NO_NAMES, describe
from cad.confirmations.answers import Edit
from cad.tables.fasteners import ClearanceSeries
from cad.tables.materials import UNITS
from cad.tables.tolerances import load_tolerances

type Dimension = Literal["mass", "length"]

# The only units the page reads, by exact key after lowercasing. No two keys differ only by case,
# so "G" and "MM" have one reading each, and pint never parses what a person typed. Keep this
# table growing only: a stored answer's text is read again on every read of its brief.
UNIT_NAMES: Final[Mapping[str, tuple[Dimension, str]]] = {
    "g": ("mass", "gram"),
    "gram": ("mass", "gram"),
    "grams": ("mass", "gram"),
    "kg": ("mass", "kilogram"),
    "kilogram": ("mass", "kilogram"),
    "kilograms": ("mass", "kilogram"),
    "lb": ("mass", "pound"),
    "lbs": ("mass", "pound"),
    "pound": ("mass", "pound"),
    "pounds": ("mass", "pound"),
    "oz": ("mass", "ounce"),
    "ounce": ("mass", "ounce"),
    "ounces": ("mass", "ounce"),
    "mm": ("length", "millimeter"),
    "millimeter": ("length", "millimeter"),
    "millimeters": ("length", "millimeter"),
    "millimetre": ("length", "millimeter"),
    "millimetres": ("length", "millimeter"),
    "cm": ("length", "centimeter"),
    "centimeter": ("length", "centimeter"),
    "centimeters": ("length", "centimeter"),
    "centimetre": ("length", "centimeter"),
    "centimetres": ("length", "centimeter"),
    "m": ("length", "meter"),
    "meter": ("length", "meter"),
    "meters": ("length", "meter"),
    "metre": ("length", "meter"),
    "metres": ("length", "meter"),
    "in": ("length", "inch"),
    "inch": ("length", "inch"),
    "inches": ("length", "inch"),
}
SHORT: Final[Mapping[Dimension, str]] = {"mass": "g, kg, lb or oz", "length": "mm, cm, m or in"}
MAX_DIGITS: Final = 6
"""`amount` shows six significant digits, so a person's change always shows in what is recorded."""
AMOUNT: Final = re.compile(r"\s*([0-9]+(?:\.[0-9]+)?|\.[0-9]+)\s*([A-Za-z]+)?\s*")
NOT_PLAIN_DIGITS: Final = re.compile(r"[0-9][,eE][0-9+-]")
EDGES: Final = re.compile(r"[x\u00d7]", re.IGNORECASE)  # x or the multiplication sign
PLUS_OR_MINUS: Final = re.compile(r"\s*(?:\u00b1|\+\s*/\s*-|\+\s*-)\s*")
SERIES: Final = re.compile(r"\s*(close|medium|coarse|any)(?:\s+(?:series|fit))?\s*", re.IGNORECASE)
ANY_SERIES: Final = "any"


@dataclass(frozen=True, slots=True)
class _Shape:
    dimension: Dimension
    count: int
    example: str
    unit_example: str


MASS: Final = _Shape("mass", 1, "120 g", "120 g")
BOX: Final = _Shape("length", 3, "120 x 80 x 40 mm", "40 mm")
LENGTH: Final = _Shape("length", 1, "2 mm", "2 mm")


def placeholder(requirement: Requirement) -> str | None:
    """What the page shows in the row's empty edit field, or None when the row has no number."""
    target = requirement.target
    match target:
        case (
            ClosedSolid()
            | MeasureLimit()
            | Unchecked()
            | MadeOf()
            | MinSafetyFactor()
            | FitsWith()
            | AgentLimit()
        ):
            return None
        case FastenerHoles():
            if target.fit is HoleFit.TAPPED:
                return None
            return "any series" if target.series is None else f"{target.series.value} series"
        case PlainHoles():
            return f"{amount(target.diameter)} {_tolerance_text(target.tolerance)}"
        case MaxMass() | MinMass():
            return amount(target.mass)
        case MaxDeflection():
            return amount(target.deflection)
        case MinClearance() | MaxClearance():
            return amount(target.clearance)
        case Envelope():
            return " x ".join(amount(edge) for edge in target.edges)
        case _:
            assert_never(target)


def _tolerance_text(tolerance: HoleTolerance) -> str:
    """The tolerance as the page reads it back, so a person edits from what they see."""
    match tolerance:
        case PlusMinus(within=within):
            return f"\u00b1 {amount(within)}"
        case ByClass(key=key):
            return key
        case _:
            assert_never(tolerance)


def apply_edits(
    requirements: Sequence[Requirement],
    edits: Sequence[Edit],
    names: Mapping[str, str] = NO_NAMES,
) -> tuple[Requirement, ...] | str:
    """The requirements with each edit applied, or a message for the person refusing them."""
    by_row = {edit.row: edit.text for edit in edits}
    known = {r.id for r in requirements}
    if len(by_row) != len(edits) or not set(by_row) <= known:
        return "This page changed since it opened. Ask the agent to open it again."
    changed: list[Requirement] = []
    for requirement in requirements:
        text = by_row.get(requirement.id)
        one = requirement if text is None else _edited(requirement, text)
        if isinstance(one, str):
            return f"{describe(requirement, names)}: {one}"
        changed.append(one)
    if len({r.id for r in changed}) != len(changed):
        return "Two rows would say the same thing. Change one of them, or decline."
    return tuple(changed)


def _edited(requirement: Requirement, text: str) -> Requirement | str:
    target = requirement.target
    try:
        match target:
            case (
                ClosedSolid()
                | MeasureLimit()
                | Unchecked()
                | MadeOf()
                | MinSafetyFactor()
                | FitsWith()
                | AgentLimit()
            ):
                return "This row has no number to change."
            case FastenerHoles() if target.fit is HoleFit.TAPPED:
                return "This row has no number to change."
            case FastenerHoles():
                new = FastenerHoles(
                    size=target.size,
                    fit=target.fit,
                    count=target.count,
                    series=_series(text),
                    body=target.body,
                )
            case PlainHoles():
                new = _plain_hole(target, text)
            case MaxMass() | MinMass():
                [mass] = _quantities(text, MASS)
                new = type(target).model_validate({"mass": mass, "body": target.body})
            case MaxDeflection():
                [deflection] = _quantities(text, LENGTH)
                new = MaxDeflection(load=target.load, deflection=deflection)
            case MinClearance() | MaxClearance():
                [clearance] = _quantities(text, LENGTH)
                new = type(target)(part=target.part, clearance=clearance)
            case Envelope():
                edges = _quantities(text, BOX)
                new = Envelope.model_validate({"edges": edges})
            case _:
                assert_never(target)
    except _Unreadable as error:
        return str(error)
    except ValidationError as error:
        return _first_message(error)
    return requirement.model_copy(
        update={
            "target": new,
            "id": requirement_id(requirement.brief_id, new, requirement.origin),
        }
    )


class _Unreadable(Exception):
    pass


def _series(text: str) -> ClearanceSeries | None:
    found = SERIES.fullmatch(text)
    if found is None:
        raise _Unreadable("Write close, medium, coarse or any, such as close.")
    word = found.group(1).lower()
    return None if word == ANY_SERIES else ClearanceSeries(word)


def _plain_hole(target: PlainHoles, text: str) -> PlainHoles:
    """The hole with the diameter and the tolerance the text names, and the rest as it was."""
    keys = sorted(load_tolerances().classes, key=len, reverse=True)
    shown = f"{amount(target.diameter)} {_tolerance_text(target.tolerance)}"
    try:
        return _read_plain_hole(target, text, keys)
    except _Unreadable as error:
        raise _Unreadable(f"{error} To change the tolerance, write it as {shown}.") from error


def _read_plain_hole(target: PlainHoles, text: str, keys: list[str]) -> PlainHoles:
    signed = PLUS_OR_MINUS.split(text, maxsplit=1)
    tolerance = target.tolerance
    if len(signed) == 2:
        [diameter_text, wide] = signed
        unit = AMOUNT.fullmatch(diameter_text)
        spelled = (
            f"{wide} {unit.group(2)}" if unit and unit.group(2) and not _has_unit(wide) else wide
        )
        [within] = _quantities(spelled, LENGTH)
        tolerance = PlusMinus(within=within)
    else:
        diameter_text = text
        named = next((key for key in keys if _ends_with_word(text, key)), None)
        if named is not None:
            diameter_text = text[: len(text.rstrip()) - len(named)]
            tolerance = ByClass(key=named)
    diameter = target.diameter
    if diameter_text.strip():
        [diameter] = _quantities(diameter_text, LENGTH)
    return PlainHoles(diameter=diameter, count=target.count, tolerance=tolerance, body=target.body)


def _has_unit(amount_text: str) -> bool:
    found = AMOUNT.fullmatch(amount_text)
    return found is not None and found.group(2) is not None


def _ends_with_word(text: str, word: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith(word) and (
        len(stripped) == len(word) or stripped[-len(word) - 1].isspace()
    )


def _quantities(text: str, shape: _Shape) -> list[pint.Quantity]:
    """`shape.count` amounts split by "x". A bare number takes the only unit written."""
    parts = EDGES.split(text) if shape.count > 1 else [text]
    matches = [AMOUNT.fullmatch(part) for part in parts]
    if any(NOT_PLAIN_DIGITS.search(part) for part in parts):
        raise _Unreadable(
            "Write the number with digits and a decimal point only, such as "
            + ("1200 g." if shape.dimension == "mass" else "1200 mm.")
        )
    if len(parts) != shape.count or any(m is None for m in matches):
        what = "a number" if shape.count == 1 else "three lengths"
        raise _Unreadable(f"Write {what} and a unit, such as {shape.example}.")
    found = [(m.group(1), m.group(2)) for m in matches if m is not None]
    last_unit = found[-1][1]
    if last_unit is None:
        raise _Unreadable(f"Say the unit too, such as {shape.example}.")
    written = {UNIT_NAMES.get(unit.lower(), (None, unit))[1] for _, unit in found if unit}
    if len(written) > 1 and any(unit is None for _, unit in found):
        raise _Unreadable("Give each length its own unit, such as 20 cm x 100 mm x 5 cm.")
    return [_quantity(number, unit or last_unit, shape) for number, unit in found]


def _quantity(number: str, unit: str, shape: _Shape) -> pint.Quantity:
    named = UNIT_NAMES.get(unit.lower())
    if named is None:
        raise _Unreadable(f'"{unit}" is not a unit this page reads. Use {SHORT[shape.dimension]}.')
    dimension, name = named
    if dimension != shape.dimension:
        raise _Unreadable(
            f"{unit} is a {dimension}, not a {shape.dimension}. "
            f"Write a {shape.dimension}, such as {shape.unit_example}."
        )
    if len(number.replace(".", "").strip("0")) > MAX_DIGITS:
        raise _Unreadable(
            f"Use at most {MAX_DIGITS} digits, not counting zeros at either end, "
            f"such as 150.125 {unit}."
        )
    value = float(number)
    if value <= 0:
        raise _Unreadable("Write a number above zero.")
    return UNITS.Quantity(value, name)


def _first_message(error: ValidationError) -> str:
    message = str(error.errors()[0]["msg"])
    return message.removeprefix("Value error, ")
