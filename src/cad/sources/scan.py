"""The values a token list writes. A value is one of these token sequences:

    number [tolerance number [percent]] unit
    number unit [tolerance number [percent | unit]]
    unit number [tolerance number [percent]]
    [ unit ] number [tolerance number [percent]]

Every other token is left over, and the caller refuses the quote because of it.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from cad.sources.fields import UNITLESS, FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.tokens import UNIT_PATTERN, Token
from cad.sources.units import PRESSURE_UNITS, Unit, dimension

_MASS_NAMES: Final = {"g": "g", "kg": "kg", "t": "t", "tonne": "t", "tonnes": "t"}
_UNIT: Final = re.compile(UNIT_PATTERN, re.ASCII)
DASHES: Final = frozenset("-\u2010\u2011\u2012\u2013\u2014\u2015")


@dataclass(frozen=True, slots=True)
class Unclear:
    detail: str


@dataclass(frozen=True, slots=True)
class Value:
    number: Decimal | Unclear
    unit: Unit
    first: int
    last: int
    tolerance: Decimal | Unclear | None = None
    percent: bool = False


def is_negative(found: list[Token], index: int) -> bool:
    """A dash right before the number, with no number right before the dash."""
    if index == 0 or found[index].spaced:
        return False
    dash = found[index - 1]
    if dash.kind != "mark" or dash.text not in DASHES:
        return False
    before = found[index - 2] if index >= 2 else None
    return before is None or before.kind != "number" or dash.spaced


def values(found: list[Token], spec: FieldSpec) -> list[Value | int] | Refusal:
    """Each value in `found`, and the index of every token left over, in order."""
    items: list[Value | int] = []
    index = 0
    while index < len(found):
        value = _value_at(found, index, spec)
        if isinstance(value, Refusal):
            return value
        if value is None:
            items.append(index)
            index += 1
        else:
            items.append(value)
            index = value.last + 1
    return items


def _value_at(found: list[Token], index: int, spec: FieldSpec) -> Value | Refusal | None:
    def kind(at: int) -> str:
        return found[at].kind if at < len(found) else ""

    def text(at: int) -> str:
        return found[at].text if at < len(found) else ""

    if spec.unitless and kind(index) == "number":
        return _unitless_value(found, index, spec)
    if kind(index) == "number":
        if kind(index + 1) == "tolerance" and kind(index + 2) == "number":
            percent = kind(index + 3) == "percent"
            unit_at = index + 3 + percent
            if kind(unit_at) != "unit" or is_negative(found, index):
                return None
            return _build(found, spec, index, index, unit_at, index + 2, percent, None, unit_at)
        if kind(index + 1) != "unit":
            return None
        number_at, unit_at, after, unit_may_repeat = index, index + 1, index + 1, True
    elif kind(index) == "unit" and kind(index + 1) == "number":
        number_at, unit_at, after, unit_may_repeat = index + 1, index, index + 1, False
    elif text(index) == "[" and kind(index + 1) == "unit" and text(index + 2) == "]":
        if kind(index + 3) != "number":
            return None
        number_at, unit_at, after, unit_may_repeat = index + 3, index + 1, index + 3, False
    else:
        return None
    if is_negative(found, number_at):
        return None
    tolerance_at: int | None = None
    percent = False
    repeated_at: int | None = None
    last = after
    if kind(after + 1) == "tolerance" and kind(after + 2) == "number":
        tolerance_at = last = after + 2
        if kind(last + 1) == "percent":
            percent, last = True, last + 1
        elif unit_may_repeat and kind(last + 1) == "unit":
            repeated_at = last = last + 1
    return _build(found, spec, index, number_at, unit_at, tolerance_at, percent, repeated_at, last)


def _unitless_value(found: list[Token], index: int, spec: FieldSpec) -> Value | Refusal | None:
    def kind(at: int) -> str:
        return found[at].kind if at < len(found) else ""

    if is_negative(found, index):
        return None
    last, tolerance, percent = index, None, False
    if kind(index + 1) == "tolerance" and kind(index + 2) == "number":
        last, tolerance = index + 2, read_number(found[index + 2].text)
        if kind(last + 1) == "percent":
            last, percent = last + 1, True
    for at in (index + 1, last + 1):
        if kind(at) == "unit":
            return unlisted_unit(found[at].text, spec)
    return Value(read_number(found[index].text), UNITLESS, index, last, tolerance, percent)


def _build(
    found: list[Token],
    spec: FieldSpec,
    first: int,
    number_at: int,
    unit_at: int,
    tolerance_at: int | None,
    percent: bool,
    repeated_at: int | None,
    last: int,
) -> Value | Refusal:
    unit = _unit(found[unit_at].text, spec)
    if isinstance(unit, Refusal):
        return unit
    if repeated_at is not None and _unit(found[repeated_at].text, spec) != unit:
        shown = " ".join(token.text for token in found[first : last + 1])
        return Refusal(
            Reason.UNRECOGNISED_TEXT,
            f"the tolerance in {shown!r} has a different unit from the value",
            f"a quote whose tolerance is unitless or in the unit of the {spec.label}",
        )
    tolerance = None if tolerance_at is None else read_number(found[tolerance_at].text)
    return Value(read_number(found[number_at].text), unit, first, last, tolerance, percent)


def _unit(text: str, spec: FieldSpec) -> Unit | Refusal:
    if text in PRESSURE_UNITS:
        listed = spec.units.get(text)
        return unlisted_unit(text, spec) if listed is None else listed
    found = _UNIT.fullmatch(text)
    assert found is not None
    if not spec.per_volume:
        return unlisted_unit(text, spec)
    mass = found["mass"]
    letters = re.match(r"[a-z]+", (found["volume"] or found["negative"]).lower())
    assert letters is not None
    volume = letters[0]
    name = mass.rstrip(".").lower()
    if mass == "mg":
        return Refusal(
            Reason.UNKNOWN_UNIT,
            f"{text!r} is milligrams per volume, which is not on this reader's list of "
            f"{spec.label} units",
            "the quote with the unit written as kg/m3 or g/cm3, or the unit typed on the page",
        )
    if name == "mg" and mass != "Mg":
        return Refusal(
            Reason.UNKNOWN_UNIT,
            f"{text!r} could be milligrams or megagrams, so the unit is not read",
            "the quote with the unit written as kg/m3 or g/cm3, or the unit typed on the page",
        )
    key = "Mg" if name == "mg" else "lb" if name in {"lb", "lbs"} else _MASS_NAMES[name]
    listed = spec.units.get(f"{key}/{volume}")
    return unlisted_unit(text, spec) if listed is None else listed


def unlisted_unit(text: str, spec: FieldSpec) -> Refusal:
    known = dimension(text)
    needed = f"the unit of the {spec.label} on the page, written as {spec.unit_hint}"
    if known is not None:
        return Refusal(
            Reason.WRONG_DIMENSION, f"{text!r} measures {known}, not {spec.label}", needed
        )
    return Refusal(
        Reason.UNKNOWN_UNIT, f"{text!r} is not a {spec.label} unit this reader knows", needed
    )


def read_number(token: str) -> Decimal | Unclear:
    """The one number `token` writes, or why it has more than one reading or none."""
    if " " in token:
        return Unclear(f"{token!r} could be one number or several, because spaces split its digits")
    whole = re.split(r"[.,]", token)[0]
    if len(whole) > 1 and whole[0] == "0":
        return Unclear(f"{token!r} has a leading zero, so a digit or a mark may be missing")
    separators = re.findall(r"[.,]", token)
    if not separators:
        return Decimal(token)
    decimal = separators[-1]
    whole, _, fraction = token.rpartition(decimal)
    if len(separators) > 1:
        if separators.count(decimal) > 1:
            whole, fraction = token, ""
        return _grouped(token, whole, fraction)
    if len(fraction) == 3 and len(whole) <= 3 and whole[0] != "0":
        return Unclear(
            f"{token!r} could be {whole}{fraction} or {whole}.{fraction}, because a single "
            f"{decimal!r} before three digits can group thousands or mark a decimal"
        )
    return Decimal(f"{whole}.{fraction}")


def _grouped(token: str, whole: str, fraction: str) -> Decimal | Unclear:
    groups = re.split(r"[.,]", whole)
    one_grouping = len(set(re.findall(r"[.,]", whole))) == 1
    if one_grouping and len(groups[0]) <= 3 and all(len(group) == 3 for group in groups[1:]):
        return Decimal("".join(groups) + (f".{fraction}" if fraction else ""))
    return Unclear(f"{token!r} is not a number grouped in threes with at most one decimal mark")
