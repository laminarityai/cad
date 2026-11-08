"""The grammar a quote must fit. Every token must be accounted for, or the quote is refused.

    quote     = (value | label | standard | condition | separator)*
    value     = number [± tolerance] unit | unit number [± tolerance]
    unit      = one of the field's listed units
    label     = density, typical, nominal, value, and the word for density in a few languages
    standard  = ISO, ASTM, DIN, or GB/T followed by its number
    condition = "at" or "@" and a temperature or a pressure, or "% RH"

Anything else is left over, and the caller refuses the quote because of it.
"""

import re
from dataclasses import dataclass
from typing import Final, Literal

import pint

from cad.sources.fields import FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.tables.materials import UNITS


def _ascii(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.ASCII)


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
_UNIT_NAMED = (
    r"(?<![A-Za-z])(?i:(?P<mass>kg|mg|g|t|tonnes?|lbs?\.?)"
    rf"(?:\s*/\s*(?P<volume>{_LENGTH}\.?\^?3|cc|ml|l)|[·* ]?(?P<negative>{_LENGTH})-3))"
    r"(?![A-Za-z0-9^/-])"
)
_UNIT_PLAIN = re.sub(r"\(\?P<\w+>", "(?:", _UNIT_NAMED)
_UNIT = _ascii(_UNIT_NAMED)

_NUM = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\d)(?:[.,]\d+)?|\d+(?:[.,]\d+)*)"
_TOL = r"(?:±|\+/-|\+-)"
_SEPARATORS = r",;:()=\[\]"

_SUFFIX = _ascii(
    rf"(?P<n>{_NUM})\s*(?:(?P<u1>{_UNIT_PLAIN})(?:\s*{_TOL}\s*{_NUM}\s*(?:(?P<u2>{_UNIT_PLAIN})|%)?)?"
    rf"|{_TOL}\s*{_NUM}\s*%?\s*(?P<u3>{_UNIT_PLAIN}))"
)
_PREFIX = _ascii(
    rf"(?:\[(?P<bu>{_UNIT_PLAIN})\]|(?P<pu>{_UNIT_PLAIN}))\s*(?P<n>{_NUM})(?:\s*{_TOL}\s*{_NUM}\s*%?)?"
)
_STANDARD = _ascii(
    r"(?<![A-Za-z0-9.,])(?:ISO\s*\d{3,5}(?:-\d+)?(?::\d{4})?|ASTM\s*[A-Z]\d+(?:-\d+)?"
    r"|DIN(?:\s*EN)?(?:\s*ISO)?\s*\d+(?:-\d+)?|GB/T\s*\d+(?:-\d+)?)"
    r"(?![\d.,]\d|\d|[A-Za-z]|[ \u00a0\u202f]\d{3}(?!\d))"
)
_CONDITION = _ascii(
    rf"(?<![A-Za-z])(?i:at|@)\s*{_NUM}\s*(?:(?:[°º]\s?)?[CF]|K|bar|atm|kPa|MPa|Pa|psi)(?![A-Za-z])"
    rf"|(?<![A-Za-z]){_NUM}\s*%\s*RH(?![A-Za-z])"
)
_LABEL = _ascii(
    r"(?<![A-Za-z])(?i:mass\s+density|density|typical|nominal|value|densidad|dichte|densité)"
    r"(?![A-Za-z])|\u03c1"
)
_SEPARATOR = _ascii(rf"[{_SEPARATORS}]")
_NUMBER = _ascii(_NUM)
_WORD_AFTER_NUMBER = _ascii(rf"\s*(?P<unit>[A-Za-z][^\s{_SEPARATORS}]*)")
_RUN = _ascii(rf"[^\s{_SEPARATORS}]+")
_SPACE_GROUPS = _ascii(r"(\d{1,3}(?:[ \u00a0\u202f]\d{3})+)(?:[.,](\d+))?")


@dataclass(frozen=True, slots=True)
class Value:
    readings: tuple[float, ...]
    unit: pint.Unit
    shown: str


@dataclass(frozen=True, slots=True)
class Leftover:
    kind: Literal["number", "unit_text", "other"]
    text: str
    unit_text: str = ""

    @property
    def shown(self) -> str:
        return f"{self.text} {self.unit_text}".strip()


def scan(text: str, spec: FieldSpec) -> list[Value | Leftover] | Refusal:
    tokens: list[Value | Leftover] = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        found = _value_at(text, position, spec)
        if isinstance(found, Refusal):
            return found
        if found is not None:
            value, position = found
            if value is not None:
                tokens.append(value)
            continue
        leftover, position = _leftover_at(text, position)
        tokens.append(leftover)
    return tokens


def _value_at(
    text: str, position: int, spec: FieldSpec
) -> tuple[Value | None, int] | Refusal | None:
    for accounted in (_STANDARD, _CONDITION):
        found = accounted.match(text, position)
        if found is not None:
            return None, found.end()
    for pattern in (_SUFFIX, _PREFIX):
        found = pattern.match(text, position)
        if found is not None:
            value = _value(found, spec)
            return (value, found.end()) if isinstance(value, Value) else value
    for accounted in (_LABEL, _SEPARATOR):
        found = accounted.match(text, position)
        if found is not None:
            return None, found.end()
    return None


def _value(found: re.Match[str], spec: FieldSpec) -> Value | Refusal:
    groups = found.groupdict()
    unit_text = groups.get("u1") or groups.get("u3") or groups.get("bu") or groups.get("pu") or ""
    unit = _unit(unit_text, spec)
    if isinstance(unit, Refusal):
        return unit
    if groups.get("u2"):
        tolerance = _unit(groups["u2"], spec)
        if isinstance(tolerance, Refusal) or tolerance != unit:
            return Refusal(
                Reason.UNRECOGNISED_TEXT,
                f"the tolerance in {found[0]!r} has a different unit from the value",
                f"a quote whose tolerance is unitless or in the unit of the {spec.label}",
            )
    return Value(_readings(groups["n"]), unit, found[0].strip())


def _leftover_at(text: str, position: int) -> tuple[Leftover, int]:
    if text[position] in "0123456789":
        number = _NUMBER.match(text, position)
        assert number is not None
        word = _WORD_AFTER_NUMBER.match(text, number.end())
        if word is not None and not _is_accounted_word(text, word.start("unit")):
            return Leftover("unit_text", number[0], word["unit"]), word.end()
        return Leftover("number", number[0]), number.end()
    run = _RUN.match(text, position)
    assert run is not None
    return Leftover("other", run[0]), run.end()


def _is_accounted_word(text: str, position: int) -> bool:
    return any(p.match(text, position) for p in (_STANDARD, _CONDITION, _LABEL, _UNIT))


def _unit(text: str, spec: FieldSpec) -> pint.Unit | Refusal:
    found = _UNIT.fullmatch(text)
    assert found is not None
    mass = found["mass"]
    letters = re.match(r"[a-z]+", (found["volume"] or found["negative"]).lower())
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
            f"{text!r} could be milligrams or megagrams, so the unit is not read",
            "the quote with the unit written as kg/m3 or g/cm3, or the unit typed on the page",
        )
    if (key, volume) not in spec.units:
        return unlisted_unit(text, spec)
    return UNITS.Unit(f"{_MASS_UNITS[key]}/{_VOLUME_UNITS[volume]}")


def unlisted_unit(text: str, spec: FieldSpec) -> Refusal:
    known = _pint_unit(text)
    needed = f"the unit of the {spec.label} on the page, written as g/cm3 or kg/m3"
    if known is not None and not known.is_compatible_with(spec.canonical_unit):
        return Refusal(
            Reason.WRONG_DIMENSION,
            f"{text!r} measures {known.dimensionality}, not {spec.label}",
            needed,
        )
    return Refusal(
        Reason.UNKNOWN_UNIT, f"{text!r} is not a {spec.label} unit this reader knows", needed
    )


def _pint_unit(text: str) -> pint.Unit | None:
    cleaned = re.sub(r"\blbs?\b", "lb", text.strip(".,"))
    cleaned = re.sub(r"\.(?=[/\d])", "", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d+)(?!\d)", r"\1^\2", cleaned)
    try:
        unit = UNITS.Unit(cleaned)
    except Exception:  # pint raises many unrelated types on arbitrary datasheet text
        return None
    return None if unit.dimensionless else unit


def _readings(token: str) -> tuple[float, ...]:
    grouped = _SPACE_GROUPS.fullmatch(token)
    if grouped is not None:
        groups = re.split(r"[ \u00a0\u202f]", grouped[1])
        whole = float("".join(groups))
        if grouped[2]:
            return (float(f"{whole:.0f}.{grouped[2]}"), float(f"{groups[-1]}.{grouped[2]}"))
        return (whole, float(groups[-1]))
    parts = re.split(r"[.,]", token)
    if len(parts) == 1:
        return (float(token),)
    separators = set(re.findall(r"[.,]", token))
    if len(separators) == 2:
        decimal = "." if token.rfind(".") > token.rfind(",") else ","
        whole_text, _, fraction = token.rpartition(decimal)
        whole_parts = re.split(r"[.,]", whole_text)
        if len(whole_parts[0]) > 3 or any(len(p) != 3 for p in whole_parts[1:]):
            return ()
        return (float("".join(whole_parts) + "." + fraction),)
    if len(parts) > 2:
        grouped_digits = len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:])
        return (float("".join(parts)),) if grouped_digits and parts[0][0] != "0" else ()
    decimal_reading = float(f"{parts[0]}.{parts[1]}")
    if len(parts[1]) == 3 and 1 <= len(parts[0]) <= 3 and parts[0][0] != "0":
        return (float("".join(parts)), decimal_reading)
    return (decimal_reading,)
