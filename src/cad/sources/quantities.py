import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

import pint

from cad.tables.materials import UNITS, magnitude

type Field = Literal["density"]


class Reason(StrEnum):
    NO_QUANTITY = "no_quantity"
    SEVERAL_QUANTITIES = "several_quantities"
    RANGE = "range"
    MISSING_UNIT = "missing_unit"
    WRONG_DIMENSION = "wrong_dimension"
    OUT_OF_BAND = "out_of_band"


@dataclass(frozen=True, slots=True)
class Refusal:
    reason: Reason
    detail: str
    needed: str


@dataclass(frozen=True, slots=True)
class _FieldSpec:
    label: str
    canonical_unit: str
    low: float
    high: float


_SPECS: Final[dict[Field, _FieldSpec]] = {
    "density": _FieldSpec("density", "kg/m^3", 500.0, 20000.0),
}

_NUMBER = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d{3})*(?:[.,]\d+)?)(?!\d)"
_SPACES = re.compile(r"[ \u00a0\u202f]")
_ITEM = re.compile(
    rf"(?P<number>{_NUMBER})|(?P<bracket>\[[^\]\s]+\])|(?P<word>[^\s\d\[\]()][^\s\[\]()]*)"
)
_STANDARD = re.compile(r"\b(?:ISO|ASTM|GB/T|GB|EN|DIN|JIS|IEC)\s*[A-Z]?\d+(?:[-:.]\d+)*")
_TOLERANCE = re.compile(rf"\s*(?:±|\+/-|\+-)\s*{_NUMBER}")
_RANGE = re.compile(
    rf"(?P<low>{_NUMBER})\s*(?:\S{{1,12}}\s*)?(?:[-\u2013\u2014]|\bto\b)\s*(?P<high>{_NUMBER})(?!\s*/)"
)
_NOT_UNITS: Final = frozenset({"at", "a", "as", "to", "or", "by", "is", "of", "per", "no"})


@dataclass(frozen=True, slots=True)
class _Item:
    start: int
    end: int
    text: str
    kind: Literal["number", "bracket", "word"]


@dataclass(frozen=True, slots=True)
class _Bound:
    value: float
    unit: pint.Unit
    shown: str


def one_quantity(quote: str, field: Field) -> pint.Quantity | Refusal:
    """Read the single quantity of `field`'s dimension out of `quote`, or say why not.

    The reader never picks between candidates and never assumes a unit.
    """
    spec = _SPECS[field]
    text = _TOLERANCE.sub("", _STANDARD.sub(" ", quote))
    ranged = _RANGE.search(text)
    if ranged is not None:
        return Refusal(
            Reason.RANGE,
            f"{ranged.group(0)!r} is a range",
            f"one value for {spec.label}: choose the figure to use and quote it with its unit",
        )
    bound, unbound = _bind(text)
    matching = [b for b in bound if b.unit.is_compatible_with(spec.canonical_unit)]
    elsewhere = [b for b in bound if b not in matching]
    fits = _distinct(matching)
    repeated = {f.value for f in fits}
    stray = [text for text, value in unbound if value not in repeated]
    if len(fits) > 1:
        return Refusal(
            Reason.SEVERAL_QUANTITIES,
            "found " + " and ".join(f.shown for f in fits),
            f"a quote with only one {spec.label} value and its unit",
        )
    if stray:
        return Refusal(
            Reason.MISSING_UNIT,
            ", ".join(stray) + (" has" if len(stray) == 1 else " have") + " no unit",
            f"the unit of {stray[0]}: type it on the page, it is not guessed",
        )
    if fits:
        return _within_band(fits[0], spec)
    if elsewhere:
        first = elsewhere[0]
        return Refusal(
            Reason.WRONG_DIMENSION,
            f"{first.shown} measures {first.unit.dimensionality}, not {spec.label}",
            f"a quote that gives {spec.label} in a {spec.label} unit such as g/cm3 or kg/m3",
        )
    return Refusal(
        Reason.NO_QUANTITY,
        "no number in the quote",
        f"a quote that contains the {spec.label} and its unit",
    )


def _within_band(found: _Bound, spec: _FieldSpec) -> pint.Quantity | Refusal:
    quantity = UNITS.Quantity(found.value, found.unit)
    canonical = magnitude(quantity, spec.canonical_unit)
    if spec.low <= canonical <= spec.high:
        return quantity
    return Refusal(
        Reason.OUT_OF_BAND,
        f"{found.shown} is {canonical:g} {spec.canonical_unit}",
        f"a {spec.label} between {spec.low:g} and {spec.high:g} {spec.canonical_unit}",
    )


def _bind(text: str) -> tuple[list[_Bound], list[tuple[str, float]]]:
    items = [_item(match) for match in _ITEM.finditer(text)]
    bound: list[_Bound] = []
    unbound: list[tuple[str, float]] = []
    used: set[int] = set()
    for index, item in enumerate(items):
        if item.kind != "number":
            continue
        value = _to_float(item.text)
        after = _unit_after(text, items, index)
        if after is not None:
            used.add(index + 1)
            bound.append(_Bound(value, after[0], text[item.start : after[1]].strip()))
            continue
        before = None if index - 1 in used else _unit_before(text, items, index)
        if before is not None:
            bound.append(_Bound(value, before[0], text[before[1] : item.end].strip()))
        else:
            unbound.append((item.text.strip(), value))
    return bound, unbound


def _item(match: re.Match[str]) -> _Item:
    kind = "number" if match["number"] else "bracket" if match["bracket"] else "word"
    return _Item(match.start(), match.end(), match[0], kind)


def _unit_after(text: str, items: list[_Item], index: int) -> tuple[pint.Unit, int] | None:
    if index + 1 >= len(items):
        return None
    number, word = items[index], items[index + 1]
    if word.kind != "word" or text[number.end : word.start].strip():
        return None
    unit = _unit(word.text)
    return None if unit is None else (unit, word.end)


def _unit_before(text: str, items: list[_Item], index: int) -> tuple[pint.Unit, int] | None:
    if index == 0:
        return None
    word, number = items[index - 1], items[index]
    if word.kind == "number" or text[word.end : number.start].strip():
        return None
    if word.kind == "word" and (
        "/" not in word.text
        or text[word.start - 1 : word.start] == "("
        or text[word.end : word.end + 1] == ")"
    ):
        return None
    unit = _unit(word.text)
    return None if unit is None else (unit, word.start)


def _unit(token: str) -> pint.Unit | None:
    text = token.strip("[],;:")
    if text.lower() in _NOT_UNITS:
        return None
    text = (
        text.replace("³", "^3")
        .replace("²", "^2")
        .replace("·", "*")
        .replace("°C", "degC")
        .replace("ºC", "degC")
        .replace("°F", "degF")
        .replace("ºF", "degF")
    )
    text = re.sub(r"\blbs?\b", "lb", text)
    text = re.sub(r"\bcc\b", "cm^3", text)
    text = re.sub(r"\.(?=[/\d])", "", text).rstrip(".")
    text = re.sub(r"([A-Za-z])(\d+)(?!\d)", r"\1^\2", text)
    try:
        unit = UNITS.Unit(text)
    except Exception:  # pint raises many unrelated types on arbitrary datasheet text
        return None
    return None if not text or unit.dimensionless else unit


def _to_float(text: str) -> float:
    digits = _SPACES.sub("", text)
    if "." in digits and "," in digits:
        decimal = "." if digits.rfind(".") > digits.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        digits = digits.replace(thousands, "").replace(decimal, ".")
    elif digits.count(",") + digits.count(".") > 1 or re.fullmatch(r"[1-9]\d{0,2},\d{3}", digits):
        digits = digits.replace(",", "").replace(".", "")
    return float(digits.replace(",", "."))


def _distinct(found: list[_Bound]) -> list[_Bound]:
    seen: dict[tuple[float, str], _Bound] = {}
    for item in found:
        seen.setdefault((item.value, f"{item.unit}"), item)
    return list(seen.values())
