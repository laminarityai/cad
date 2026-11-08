"""The grammar a quote must fit. Every token must be accounted for, or the quote is refused.

    quote     = (value | label | standard | condition | separator)*
    value     = number [± tolerance] unit | unit number [± tolerance]
    unit      = one of the field's listed units
    label     = density, typical, nominal, value, and the word for density in a few languages
    standard  = ISO, ASTM, DIN, or GB/T followed by its number, and never by a digit group
    condition = "at" or "@" and a temperature or a pressure, or "% RH"
    number    = digits with at most one reading; a separator that could group thousands or
                mark a decimal, or spaces between digit groups, make the number ambiguous

Anything else is left over, and the caller refuses the quote because of it.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from cad.sources.fields import FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.units import Unit, dimension


def _ascii(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.ASCII)


_MASS_NAMES: Final = {"g": "g", "kg": "kg", "t": "t", "tonne": "t", "tonnes": "t"}

_LENGTH = r"(?:cm|dm|m|in|ft)"
_UNIT_NAMED = (
    r"(?<![A-Za-z])(?i:(?P<mass>kg|mg|g|t|tonnes?|lbs?\.?)"
    rf"(?:\s*/\s*(?P<volume>{_LENGTH}\.?\^?3|cc|ml|l)|[·* ]?(?P<negative>{_LENGTH})-3))"
    r"(?![A-Za-z0-9^/-])"
)
_UNIT_PLAIN = re.sub(r"\(\?P<\w+>", "(?:", _UNIT_NAMED)
_UNIT = _ascii(_UNIT_NAMED)

_PLAIN_NUM = r"\d+(?:[.,]\d+)*"
_NUM = rf"(?:\d{{1,3}}(?:[ \u00a0\u202f]\d{{3}})+(?!\d)(?:[.,]\d+)?|{_PLAIN_NUM})"
_TOL = r"(?:±|\+/-|\+-)"
_SEPARATORS = r",;:()=\[\]"

_SUFFIX = _ascii(
    rf"(?P<n>{_NUM})\s*(?:(?P<u1>{_UNIT_PLAIN})"
    rf"(?:\s*{_TOL}\s*(?P<t1>{_NUM})\s*(?:(?P<u2>{_UNIT_PLAIN})|(?P<p1>%))?)?"
    rf"|{_TOL}\s*(?P<t2>{_NUM})\s*(?P<p2>%)?\s*(?P<u3>{_UNIT_PLAIN}))"
)
_PREFIX = _ascii(
    rf"(?:\[(?P<bu>{_UNIT_PLAIN})\]|(?P<pu>{_UNIT_PLAIN}))\s*(?P<n>{_NUM})"
    rf"(?:\s*{_TOL}\s*(?P<t3>{_NUM})\s*(?P<p3>%)?)?"
)
_STANDARD = _ascii(
    r"(?<![A-Za-z0-9.,])(?:ISO\s*\d{3,5}(?:-\d+)?(?::\d{4})?|ASTM\s*[A-Z]\d+(?:-\d+)?"
    r"|DIN(?:\s*EN)?(?:\s*ISO)?\s*\d+(?:-\d+)?|GB/T\s*\d+(?:-\d+)?)"
    r"(?![\d.,]\d|\d|[A-Za-z])"
)
_DIGIT_GROUP: Final = _ascii(r"\s+(?:\d{3}(?!\d)|\d+(?!\d|[.,]\d))")
_CONDITION = _ascii(
    rf"(?<![A-Za-z])(?i:at|@)\s*(?:-?{_PLAIN_NUM}\s*(?:[°º]\s?)?[CF]"
    rf"|{_PLAIN_NUM}\s*(?:K|bar|atm|kPa|MPa|Pa|psi))(?![A-Za-z])"
    rf"|(?<![A-Za-z\d.,]){_PLAIN_NUM}\s*%\s*RH(?![A-Za-z])"
)
_LABEL = _ascii(
    r"(?<![A-Za-z])(?i:mass\s+density|density|typical|nominal|value|densidad|dichte|densité)"
    r"(?![A-Za-z])|\u03c1"
)
_SEPARATOR = _ascii(rf"[{_SEPARATORS}]")
_NUMBER = _ascii(_NUM)
_WORD_AFTER_NUMBER = re.compile(rf"\s*(?P<unit>[^\W\d_][^\s{_SEPARATORS}]*)")
_RUN = _ascii(rf"[^\s{_SEPARATORS}]+")
_SPACE_GROUPS = _ascii(r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?")


@dataclass(frozen=True, slots=True)
class Unclear:
    detail: str


@dataclass(frozen=True, slots=True)
class Value:
    number: Decimal | Unclear
    unit: Unit
    shown: str
    tolerance: Decimal | Unclear | None = None
    percent: bool = False


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
    standard = _STANDARD.match(text, position)
    if standard is not None:
        digits = _DIGIT_GROUP.match(text, standard.end())
        if digits is not None:
            return Refusal(
                Reason.AMBIGUOUS_NUMBER,
                f"the standard {standard[0]!r} is followed by the digits {digits[0].strip()!r}, "
                "so it is unclear where the standard's number ends and the value starts",
                f"the {spec.label} quoted apart from the standard, or typed on the page",
            )
        return None, standard.end()
    condition = _CONDITION.match(text, position)
    if condition is not None:
        return None, condition.end()
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
    tolerance = groups.get("t1") or groups.get("t2") or groups.get("t3")
    percent = bool(groups.get("p1") or groups.get("p2") or groups.get("p3"))
    return Value(
        _read_number(groups["n"]),
        unit,
        found[0].strip(),
        None if tolerance is None else _read_number(tolerance),
        percent,
    )


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


def _unit(text: str, spec: FieldSpec) -> Unit | Refusal:
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
    listed = spec.units.get((key, volume))
    return unlisted_unit(text, spec) if listed is None else listed


def unlisted_unit(text: str, spec: FieldSpec) -> Refusal:
    known = dimension(text)
    needed = f"the unit of the {spec.label} on the page, written as g/cm3 or kg/m3"
    if known is not None:
        return Refusal(
            Reason.WRONG_DIMENSION, f"{text!r} measures {known}, not {spec.label}", needed
        )
    return Refusal(
        Reason.UNKNOWN_UNIT, f"{text!r} is not a {spec.label} unit this reader knows", needed
    )


def _read_number(token: str) -> Decimal | Unclear:
    """The one number `token` writes, or why it has more than one reading or none."""
    if _SPACE_GROUPS.fullmatch(token):
        return Unclear(f"{token!r} could be one number or several, because spaces split its digits")
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
    leading = len(groups[0]) <= 3 and groups[0][0] != "0"
    if one_grouping and leading and all(len(group) == 3 for group in groups[1:]):
        return Decimal("".join(groups) + (f".{fraction}" if fraction else ""))
    return Unclear(f"{token!r} is not a number grouped in threes with at most one decimal mark")
