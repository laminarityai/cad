import re
from dataclasses import dataclass
from typing import Final

import pint

from cad.sources.fields import FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.tables.materials import UNITS

_MASS_NAMES: Final = {"g": "g", "kg": "kg", "t": "t", "tonne": "t", "tonnes": "t"}
_MASS_UNITS: Final = {"g": "g", "kg": "kg", "Mg": "Mg", "t": "metric_ton", "lb": "lb"}
_VOLUME_UNITS: Final = {
    "cm": "cm**3",
    "dm": "dm**3",
    "m": "m**3",
    "in": "inch**3",
    "ft": "foot**3",
    "cc": "cm**3",
    "ml": "mL",
    "l": "L",
}

_LENGTH = r"(?:cm|dm|m|in|ft)"
_UNIT = re.compile(
    r"(?<![A-Za-z])(?P<mass>kg|mg|g|t|tonnes?|lbs?\.?)"
    rf"(?:\s*/\s*(?P<volume>{_LENGTH}\.?\^?3|cc|ml|l)|[·*]?\s*(?P<negative>{_LENGTH})\s*-\s*3)"
    r"(?![A-Za-z0-9^])",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")
_GROUP = re.compile(r"[ \u00a0\u202f](\d{3})(?![\d]|[.,]\d)")
_LETTERS = re.compile(r"[a-z]+")
_WORD = re.compile(r"[^\s\d\[\]()]+")
_RUN = re.compile(r"[^\s\[\]()]+")
_NOT_UNITS: Final = frozenset({"at", "a", "as", "to", "or", "by", "is", "of", "per", "no"})

BOUND_WORDS: Final = frozenset({"<", ">", "≤", "≥", "max", "min", "maximum", "minimum"})


@dataclass(frozen=True, slots=True)
class Number:
    start: int
    end: int
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Unit:
    start: int
    end: int
    unit: pint.Unit
    fits: bool
    bracketed: bool


@dataclass(frozen=True, slots=True)
class Word:
    start: int
    end: int
    text: str


type Item = Number | Unit | Word


def scan(text: str, spec: FieldSpec) -> list[Item] | Refusal:
    items: list[Item] = []
    position = 0
    while position < len(text):
        char = text[position]
        if char.isspace() or char in "()]":
            position += 1
            continue
        step = _next_item(text, position, items, spec)
        if isinstance(step, Refusal):
            return step
        item, position = step
        if item is not None:
            items.append(item)
    return items


def _next_item(
    text: str, position: int, items: list[Item], spec: FieldSpec
) -> tuple[Item | None, int] | Refusal:
    char = text[position]
    if char == "[":
        close = text.find("]", position)
        inner = text[position + 1 : close] if close > position else ""
        listed = _UNIT.fullmatch(inner) if inner and not inner.isspace() else None
        if listed is None:
            return None, position + 1
        unit = _listed_unit(listed, spec)
        if isinstance(unit, Refusal):
            return unit
        return Unit(position, close + 1, unit, True, True), close + 1
    if char.isdigit():
        return _number(text, position)
    listed = _UNIT.match(text, position)
    if listed is not None:
        unit = _listed_unit(listed, spec)
        if isinstance(unit, Refusal):
            return unit
        return Unit(position, listed.end(), unit, True, False), listed.end()
    after_number = (
        bool(items) and isinstance(items[-1], Number) and not text[items[-1].end : position].strip()
    )
    if after_number:
        other = _other_unit(text, position, spec)
        if other is not None:
            return other
    word = _WORD.match(text, position)
    assert word is not None
    return Word(position, word.end(), word[0]), word.end()


def _number(text: str, position: int) -> tuple[Number, int] | Refusal:
    token = _NUMBER.match(text, position)
    assert token is not None
    end = token.end()
    grouped: list[float] | None = None
    if re.fullmatch(r"\d{1,3}", token[0]):
        digits = token[0]
        while (group := _GROUP.match(text, end)) is not None:
            digits += group[1]
            end = group.end()
            grouped = [float(digits), float(group[1])]
    values = tuple(grouped) if grouped else _readings(token[0])
    if not values:
        return Refusal(
            Reason.AMBIGUOUS_NUMBER,
            f"{token[0]!r} cannot be read as one number",
            "the number written with one decimal point and no grouping",
        )
    return Number(position, end, values), end


def _readings(token: str) -> tuple[float, ...]:
    dots, commas = token.count("."), token.count(",")
    if dots and commas:
        decimal = "." if token.rfind(".") > token.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        whole, _, fraction = token.rpartition(decimal)
        if not re.fullmatch(rf"\d{{1,3}}(?:\{thousands}\d{{3}})*", whole):
            return ()
        return (float(whole.replace(thousands, "") + "." + fraction),)
    separator = "." if dots else ","
    parts = token.split(separator)
    if len(parts) > 2:
        grouped = len(parts[0]) <= 3 and all(len(part) == 3 for part in parts[1:])
        return (float("".join(parts)),) if grouped and parts[0][0] != "0" else ()
    if len(parts) == 2:
        decimal = float(f"{parts[0]}.{parts[1]}")
        if len(parts[1]) == 3 and 1 <= len(parts[0]) <= 3 and parts[0][0] != "0":
            return (float("".join(parts)), decimal)
        return (decimal,)
    return (float(token),)


def _listed_unit(found: re.Match[str], spec: FieldSpec) -> pint.Unit | Refusal:
    mass = found["mass"]
    letters = _LETTERS.match((found["volume"] or found["negative"]).lower())
    assert letters is not None
    volume = letters[0]
    name = mass.rstrip(".").lower()
    if name == "mg":
        key = "Mg" if mass == "Mg" else None
    else:
        key = "lb" if name in {"lb", "lbs"} else _MASS_NAMES[name]
    if key is None:
        return Refusal(
            Reason.UNKNOWN_UNIT,
            f"{found[0]!r} could be milligrams or megagrams, so the unit is not read",
            "the quote with the unit written as kg/m3 or g/cm3, or the unit typed on the page",
        )
    if (key, volume) not in spec.units:
        return Refusal(
            Reason.UNKNOWN_UNIT,
            f"{found[0]!r} is not a {spec.label} unit this reader knows",
            f"the unit of the {spec.label} on the page, written as g/cm3 or kg/m3",
        )
    return UNITS.Unit(f"{_MASS_UNITS[key]}/{_VOLUME_UNITS[volume]}")


def _other_unit(text: str, position: int, spec: FieldSpec) -> tuple[Unit, int] | Refusal | None:
    run = _RUN.match(text, position)
    assert run is not None
    word = run[0]
    if word.lower().rstrip(".,") in _NOT_UNITS | BOUND_WORDS:
        return None
    unit = _pint_unit(word)
    if unit is None:
        if word[0].isascii() and word[0].isalpha() and "/" in word:
            return _unknown(word, spec)
        return None
    if unit.is_compatible_with(spec.canonical_unit):
        return _unknown(word, spec)
    return Unit(position, run.end(), unit, False, False), run.end()


def _unknown(word: str, spec: FieldSpec) -> Refusal:
    return Refusal(
        Reason.UNKNOWN_UNIT,
        f"{word!r} is not a {spec.label} unit this reader knows",
        f"the unit of the {spec.label} on the page, written as g/cm3 or kg/m3",
    )


def _pint_unit(token: str) -> pint.Unit | None:
    text = token.strip("[],;:")
    for old, new in (("°C", "degC"), ("ºC", "degC"), ("°F", "degF"), ("ºF", "degF")):
        text = text.replace(old, new)
    text = re.sub(r"\blbs?\b", "lb", text)
    text = re.sub(r"\.(?=[/\d])", "", text).rstrip(".")
    text = re.sub(r"([A-Za-z])(\d+)(?!\d)", r"\1^\2", text)
    try:
        unit = UNITS.Unit(text)
    except Exception:  # pint raises many unrelated types on arbitrary datasheet text
        return None
    return None if not text or unit.dimensionless else unit
