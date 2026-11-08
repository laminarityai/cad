import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

import pint

from cad.tables.materials import UNITS, magnitude

type Field = Literal["density"]

MAX_QUOTE_LENGTH: Final = 500


class Reason(StrEnum):
    NO_QUANTITY = "no_quantity"
    SEVERAL_QUANTITIES = "several_quantities"
    RANGE = "range"
    BOUND = "bound"
    MISSING_UNIT = "missing_unit"
    UNKNOWN_UNIT = "unknown_unit"
    WRONG_DIMENSION = "wrong_dimension"
    OUT_OF_BAND = "out_of_band"
    NEGATIVE = "negative_value"
    SCIENTIFIC_NOTATION = "scientific_notation"
    AMBIGUOUS_NUMBER = "ambiguous_number"
    TOO_LONG = "too_long"


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
    units: frozenset[tuple[str, str]]


_SPECS: Final[dict[Field, _FieldSpec]] = {
    "density": _FieldSpec(
        "density",
        "kg/m^3",
        500.0,
        20000.0,
        frozenset(
            {
                ("g", "cm"),
                ("g", "cc"),
                ("g", "ml"),
                ("kg", "m"),
                ("kg", "l"),
                ("kg", "dm"),
                ("Mg", "m"),
                ("t", "m"),
                ("lb", "in"),
                ("lb", "ft"),
            }
        ),
    ),
}

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
_STANDARD = re.compile(r"\b(?:ISO|ASTM|GB/T|GB|EN|DIN|JIS|IEC)\s*[A-Z]?\d+(?:[-:.]\d+)*")
_TOLERANCE = re.compile(r"\s*(?:±|\+/-|\+-)\s*\d[\d.,]*\d?\s*%?")
_SCIENTIFIC = re.compile(r"\d(?:[eE][+-]?\d|\s*[x\u00d7*\u00b7]\s*10)")
_NEGATIVE = re.compile(r"(?<![\w.)\]])-\d")
_SPLIT = re.compile(r"([:=~≈≤≥<>;])")
_RANGE_SEPARATORS: Final = frozenset({"-", "\u2013", "—", "to", "~", "…", "..."})
_BOUND_WORDS: Final = frozenset({"<", ">", "≤", "≥", "max", "min", "maximum", "minimum"})
_NOT_UNITS: Final = frozenset({"at", "a", "as", "to", "or", "by", "is", "of", "per", "no"})


@dataclass(frozen=True, slots=True)
class _Number:
    start: int
    end: int
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _Unit:
    start: int
    end: int
    unit: pint.Unit
    fits: bool
    bracketed: bool


@dataclass(frozen=True, slots=True)
class _Word:
    start: int
    end: int
    text: str


type _Item = _Number | _Unit | _Word


@dataclass(frozen=True, slots=True)
class _Bound:
    values: tuple[float, ...]
    unit: pint.Unit
    fits: bool
    shown: str
    bounded: bool


def one_quantity(quote: str, field: Field) -> pint.Quantity | Refusal:
    """Read the single quantity of `field`'s dimension out of `quote`, or say why not.

    The reader never picks between candidates and never assumes a unit. A unit must be on
    the field's list, so "gr" (grains) and "ton" (short tons) are refused, not converted.
    A number such as "1,240" or "1.240" can mean 1240 or 1.24. The reading that lands inside the
    field's band is used, and the quote is refused when both do.
    """
    spec = _SPECS[field]
    if len(quote) > MAX_QUOTE_LENGTH:
        return Refusal(
            Reason.TOO_LONG,
            f"the quote has {len(quote)} characters",
            f"a quote of at most {MAX_QUOTE_LENGTH} characters around the one {spec.label} value",
        )
    text = _SPLIT.sub(r" \1 ", _clean(quote))
    early = _early_refusal(text, spec)
    if early is not None:
        return early
    items = _scan(text, spec)
    if isinstance(items, Refusal):
        return items
    ranged = _range(text, items)
    if ranged is not None:
        return Refusal(
            Reason.RANGE,
            f"{ranged!r} is a range",
            f"one value for {spec.label}: choose the figure to use and quote it with its unit",
        )
    bound, unbound = _bind(text, items)
    fits = _distinct([b for b in bound if b.fits])
    repeated = {v for f in fits for v in f.values}
    stray = [shown for shown, values in unbound if not repeated.intersection(values)]
    if any(f.bounded for f in fits):
        return Refusal(
            Reason.BOUND,
            "the quote gives a limit (<, >, max or min), not a value",
            f"a quote that states the {spec.label} itself, not a limit on it",
        )
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
    elsewhere = [b for b in bound if not b.fits]
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


def _clean(quote: str) -> str:
    text = unicodedata.normalize("NFKC", quote)
    text = re.sub(r"[​-‍﻿]", "", text).replace("\u2212", "-")
    return _TOLERANCE.sub("", _STANDARD.sub(" ", text))


def _early_refusal(text: str, spec: _FieldSpec) -> Refusal | None:
    scientific = _SCIENTIFIC.search(text)
    if scientific is not None:
        return Refusal(
            Reason.SCIENTIFIC_NOTATION,
            "the quote uses scientific notation",
            f"a quote that writes the {spec.label} in plain digits, such as 1240 kg/m3",
        )
    negative = _NEGATIVE.search(text)
    if negative is not None:
        return Refusal(
            Reason.NEGATIVE,
            "the quote holds a negative value",
            f"a quote with the {spec.label}, which cannot be negative",
        )
    return None


def _within_band(found: _Bound, spec: _FieldSpec) -> pint.Quantity | Refusal:
    quantities = [UNITS.Quantity(value, found.unit) for value in found.values]
    inside = [q for q in quantities if spec.low <= magnitude(q, spec.canonical_unit) <= spec.high]
    if len(inside) == 1:
        return inside[0]
    if inside:
        return Refusal(
            Reason.AMBIGUOUS_NUMBER,
            f"{found.shown} reads as "
            + " or ".join(f"{value:g}" for value in found.values)
            + ", and both fit the band",
            "the number written with one decimal point and no grouping",
        )
    canonical = magnitude(quantities[0], spec.canonical_unit)
    return Refusal(
        Reason.OUT_OF_BAND,
        f"{found.shown} is {canonical:g} {spec.canonical_unit}",
        f"a {spec.label} between {spec.low:g} and {spec.high:g} {spec.canonical_unit}",
    )


def _scan(text: str, spec: _FieldSpec) -> list[_Item] | Refusal:
    items: list[_Item] = []
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
    text: str, position: int, items: list[_Item], spec: _FieldSpec
) -> tuple[_Item | None, int] | Refusal:
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
        return _Unit(position, close + 1, unit, True, True), close + 1
    if char.isdigit():
        return _number(text, position)
    listed = _UNIT.match(text, position)
    if listed is not None:
        unit = _listed_unit(listed, spec)
        if isinstance(unit, Refusal):
            return unit
        return _Unit(position, listed.end(), unit, True, False), listed.end()
    after_number = (
        bool(items)
        and isinstance(items[-1], _Number)
        and not text[items[-1].end : position].strip()
    )
    if after_number:
        other = _other_unit(text, position, spec)
        if other is not None:
            return other
    word = _WORD.match(text, position)
    assert word is not None
    return _Word(position, word.end(), word[0]), word.end()


def _number(text: str, position: int) -> tuple[_Number, int] | Refusal:
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
    return _Number(position, end, values), end


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


def _listed_unit(found: re.Match[str], spec: _FieldSpec) -> pint.Unit | Refusal:
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


def _other_unit(text: str, position: int, spec: _FieldSpec) -> tuple[_Unit, int] | Refusal | None:
    run = _RUN.match(text, position)
    assert run is not None
    word = run[0]
    if word.lower().rstrip(".,") in _NOT_UNITS | _BOUND_WORDS:
        return None
    unit = _pint_unit(word)
    if unit is None:
        if word[0].isascii() and word[0].isalpha() and "/" in word:
            return _unknown(word, spec)
        return None
    if unit.is_compatible_with(spec.canonical_unit):
        return _unknown(word, spec)
    return _Unit(position, run.end(), unit, False, False), run.end()


def _unknown(word: str, spec: _FieldSpec) -> Refusal:
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


def _range(text: str, items: list[_Item]) -> str | None:
    for index, item in enumerate(items):
        if not isinstance(item, _Number):
            continue
        cursor = index + 1
        if cursor < len(items) and isinstance(items[cursor], _Unit):
            cursor += 1
        if cursor + 1 >= len(items):
            continue
        separator, high = items[cursor], items[cursor + 1]
        if (
            isinstance(separator, _Word)
            and separator.text.lower() in _RANGE_SEPARATORS
            and isinstance(high, _Number)
            and not text[high.end :].lstrip().startswith("/")
        ):
            return text[item.start : high.end]
    return None


def _bind(
    text: str, items: list[_Item]
) -> tuple[list[_Bound], list[tuple[str, tuple[float, ...]]]]:
    bound: list[_Bound] = []
    unbound: list[tuple[str, tuple[float, ...]]] = []
    used: set[int] = set()
    for index, item in enumerate(items):
        if not isinstance(item, _Number):
            continue
        following = items[index + 1] if index + 1 < len(items) else None
        preceding = items[index - 1] if index > 0 else None
        if (
            isinstance(following, _Unit)
            and not following.bracketed
            and not text[item.end : following.start].strip()
        ):
            used.add(index + 1)
            bound.append(_bound(text, items, item, following, index - 1, index + 2, item.start))
        elif (
            isinstance(preceding, _Unit)
            and index - 1 not in used
            and _prefix_unit_applies(text, preceding, item)
        ):
            bound.append(
                _bound(text, items, item, preceding, index - 2, index + 1, preceding.start)
            )
        else:
            unbound.append((text[item.start : item.end], item.values))
    return bound, unbound


def _prefix_unit_applies(text: str, unit: _Unit, number: _Number) -> bool:
    if text[unit.end : number.start].strip():
        return False
    if unit.bracketed:
        return True
    written = text[unit.start : unit.end]
    return (
        "/" in written
        and text[unit.start - 1 : unit.start] != "("
        and text[unit.end : unit.end + 1] != ")"
    )


def _bound(
    text: str,
    items: list[_Item],
    number: _Number,
    unit: _Unit,
    before: int,
    after: int,
    start: int,
) -> _Bound:
    end = max(number.end, unit.end)
    neighbours = [items[i] for i in (before, after) if 0 <= i < len(items)]
    bounded = any(
        isinstance(n, _Word) and n.text.lower().rstrip(".") in _BOUND_WORDS for n in neighbours
    )
    return _Bound(number.values, unit.unit, unit.fits, text[start:end].strip(), bounded)


def _distinct(found: list[_Bound]) -> list[_Bound]:
    seen: dict[tuple[tuple[float, ...], str], _Bound] = {}
    for item in found:
        seen.setdefault((item.values, f"{item.unit}"), item)
    return list(seen.values())
