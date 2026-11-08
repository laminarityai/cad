"""Why a token list does not state exactly one value, checked in a fixed order.

The order puts the most useful reason first: a range or a second value says more than a stray
token does. Every check reads only token kinds, texts and whether whitespace separates them.
"""

import re
from typing import Final

from cad.sources.fields import FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.scan import DASHES, Value, is_negative, unlisted_unit
from cad.sources.tokens import Token
from cad.sources.units import dimension

# These separators never sit inside a number, so one that touches a digit hides where the
# number starts or ends: ",9" could be 0.9 and "1;24" could be 1.24.
_LIKE_A_DECIMAL_MARK: Final = frozenset(",;:")
_TOUCHING: Final = _LIKE_A_DECIMAL_MARK | frozenset("()")
_BENIGN: Final = frozenset({"separator", "label", "standard", "unlisted_standard", "condition"})
_RANGE_WORDS: Final = frozenset({"to", "bis"})
_BEFORE_AN_EDITION: Final = frozenset(",:") | DASHES


def refuse(
    text: str, found: list[Token], items: list[Value | int], spec: FieldSpec
) -> Refusal | None:
    """The first reason the quote is not exactly one value, or None when it is."""
    found_values = [item for item in items if isinstance(item, Value)]
    leftovers = [item for item in items if isinstance(item, int)]
    for check in (
        _ends(text, found),
        _range(text, found, items, spec),
        _several(text, found, found_values, spec),
        _conditions(found, spec),
        _negative(found, leftovers, spec),
        _touching(text, found, early=True),
        None if found_values else _unit_text(found, leftovers, spec),
        None if found_values else _missing_unit(found, leftovers),
        _touching(text, found, early=False),
        _edition_year(found, spec),
        _unrecognised(found, leftovers, spec),
    ):
        if check is not None:
            return check
    if not found_values:
        return Refusal(
            Reason.NO_QUANTITY,
            "no number in the quote",
            f"a quote that contains the {spec.label} and its unit",
        )
    return None


def _ends(text: str, found: list[Token]) -> Refusal | None:
    """An unlisted standard or a condition ends at whitespace, a separator, or the quote's end.

    A listed standard always ends there, by its pattern. An unlisted one followed by a number is
    refused too, since from its shape alone it is unclear where its own number ends.
    """
    for index, token in enumerate(found[:-1]):
        if token.kind not in {"unlisted_standard", "condition"}:
            continue
        after = found[index + 1]
        if token.kind == "unlisted_standard" and after.kind == "unit":
            digits = re.findall(r"\d+", token.text)[-1]
            return _unlisted(
                f"{token.text!r} is not on this reader's list of density test standards, and "
                f"its last digits {digits!r} sit right before the unit {after.text!r}, so they "
                "could be the value or part of the standard, such as its edition year"
            )
        if not after.spaced and after.kind != "separator":
            rest = text[after.start :].split(" ")[0]
            if token.kind == "condition":
                return Refusal(
                    Reason.AMBIGUOUS_NUMBER,
                    f"the condition {token.text!r} runs into {rest!r}, so it is unclear where "
                    "the condition's number ends",
                    "the value quoted apart from the condition, or typed on the page",
                )
            return _unlisted(
                f"{token.text + rest!r} is not on this reader's list of density test standards, "
                "so it is unclear where the standard's number ends"
            )
        if token.kind == "unlisted_standard" and after.kind == "number":
            return _unlisted(
                f"the standard {token.text!r} is not on this reader's list of density test "
                f"standards, so it is unclear where its number ends and the value {after.text!r} "
                "starts"
            )
    return None


def _unlisted(detail: str) -> Refusal:
    return Refusal(
        Reason.AMBIGUOUS_NUMBER,
        detail,
        "the value quoted apart from the standard or typed on the page; the standard's exact "
        "spelling can also be added to the list",
    )


def _edition_year(found: list[Token], spec: FieldSpec) -> Refusal | None:
    """A whole number right after a listed standard could be the standard's edition year.

    "ISO 1183 2019 kg/m3" reads as ISO 1183 of 2019 as easily as a density of 2019 kg/m3. Only
    the grammar decides: a number with a decimal mark cannot be a year, a whole number can.
    """
    for index, token in enumerate(found[:-1]):
        if token.kind != "standard":
            continue
        after = index + 2 if found[index + 1].text in _BEFORE_AN_EDITION else index + 1
        if after < len(found) and found[after].kind == "number" and found[after].text.isdigit():
            return Refusal(
                Reason.AMBIGUOUS_NUMBER,
                f"the number {found[after].text!r} right after the standard {token.text!r} might "
                f"be part of the standard, such as its edition year, not the {spec.label}",
                f"the {spec.label} typed on the page; a whole number written right after a "
                "standard cannot be told apart from the standard's year",
            )
    return None


def _conditions(found: list[Token], spec: FieldSpec) -> Refusal | None:
    """Two different temperatures, pressures or humidities leave the value's condition unclear."""
    seen: dict[str, tuple[Token, str]] = {}
    for token in found:
        if token.kind != "condition":
            continue
        kind, written = _condition(token.text)
        first, first_written = seen.setdefault(kind, (token, written))
        if first_written != written:
            return Refusal(
                Reason.SEVERAL_CONDITIONS,
                f"the quote gives two {kind}s, {first.text!r} and {token.text!r}, so it is "
                f"unclear which one the {spec.label} applies to",
                f"a quote with the {spec.label} at one {kind}",
            )
    return None


def _condition(text: str) -> tuple[str, str]:
    """What a condition measures, and its value written without "at", spaces or a degree sign."""
    written = re.sub(r"^(?i:at|@)|[ °]", "", text)
    if written.endswith("RH"):
        return "humidity", written
    return ("temperature" if written[-1] in "CFK" else "pressure"), written


def _is_number(found: list[Token], item: Value | int) -> bool:
    return isinstance(item, Value) or found[item].kind == "number"


def _first(found: list[Token], item: Value | int) -> Token:
    return found[item.first] if isinstance(item, Value) else found[item]


def _last(found: list[Token], item: Value | int) -> Token:
    return found[item.last] if isinstance(item, Value) else found[item]


def _range(
    text: str, found: list[Token], items: list[Value | int], spec: FieldSpec
) -> Refusal | None:
    for position, low in enumerate(items[:-2]):
        between, high = items[position + 1], items[position + 2]
        if not (_is_number(found, low) and _is_number(found, high)) or isinstance(between, Value):
            continue
        word = found[between]
        joined = word.kind == "mark" or (word.kind == "word" and word.text.lower() in _RANGE_WORDS)
        if joined and _ends_cleanly(found, high):
            shown = text[_first(found, low).start : _last(found, high).end]
            return Refusal(
                Reason.RANGE,
                f"{shown!r} is a range",
                f"one value for {spec.label}: choose the figure to use and quote it with its unit",
            )
    return None


def _ends_cleanly(found: list[Token], item: Value | int) -> bool:
    """A range's high end is not glued to more text, as the 6 in a header's "10-6/K" is."""
    after = item.last + 1 if isinstance(item, Value) else item + 1
    if isinstance(item, Value) or after >= len(found) or found[after].spaced:
        return True
    return found[after].kind not in {"mark", "other", "word"}


def _several(
    text: str, found: list[Token], found_values: list[Value], spec: FieldSpec
) -> Refusal | None:
    if len(found_values) < 2:
        return None
    return Refusal(
        Reason.SEVERAL_QUANTITIES,
        "found " + " and ".join(_shown(text, found, value) for value in found_values),
        f"a quote with only one {spec.label} value and its unit",
    )


def _shown(text: str, found: list[Token], value: Value) -> str:
    """The value's text, with any separator that touches its first or last token."""
    first, last = value.first, value.last
    if first > 0 and not found[first].spaced and found[first - 1].text in _TOUCHING:
        first -= 1
    if last + 1 < len(found) and not found[last + 1].spaced and found[last + 1].text in _TOUCHING:
        last += 1
    return text[found[first].start : found[last].end]


def _negative(found: list[Token], leftovers: list[int], spec: FieldSpec) -> Refusal | None:
    for index in leftovers:
        if found[index].kind == "number" and is_negative(found, index):
            return Refusal(
                Reason.NEGATIVE,
                f"'-{found[index].text}' is a negative value",
                f"a quote with the {spec.label}, which cannot be negative",
            )
    return None


def _unit_text(found: list[Token], leftovers: list[int], spec: FieldSpec) -> Refusal | None:
    """A word right after a bare number is the unit the quote wrote, though not one listed."""
    for index in leftovers:
        if found[index].kind != "number" or index + 1 >= len(found):
            continue
        word = found[index + 1]
        if word.kind != "word" or word.text.lower() in _RANGE_WORDS:
            continue
        exponent = found[index + 2] if index + 2 < len(found) else None
        detached = exponent is not None and exponent.spaced and exponent.text == "3"
        if detached and dimension(word.text) == "mass per length":
            return Refusal(
                Reason.UNKNOWN_UNIT,
                f"'{word.text} 3' has its exponent apart from the unit",
                f"the unit of the {spec.label} on the page, written as g/cm3 or kg/m3",
            )
        return unlisted_unit(word.text, spec)
    return None


def _missing_unit(found: list[Token], leftovers: list[int]) -> Refusal | None:
    numbers = [found[index].text for index in leftovers if found[index].kind == "number"]
    if not numbers:
        return None
    return Refusal(
        Reason.MISSING_UNIT,
        ", ".join(numbers) + (" has" if len(numbers) == 1 else " have") + " no unit",
        f"the unit of {numbers[0]}: type it on the page, it is not guessed",
    )


def _touching(text: str, found: list[Token], *, early: bool) -> Refusal | None:
    """A number's digits touch only a unit, a tolerance, a percent sign or a label.

    The early pass finds what could be a lost decimal mark: ",9", "9," or "1240.". The late
    pass, after a missing unit has been reported, finds brackets and stray characters.
    """
    for index, token in enumerate(found):
        if token.kind != "number":
            continue
        before = found[index - 1] if index > 0 and not token.spaced else None
        after = found[index + 1] if index + 1 < len(found) else None
        after = after if after is not None and not after.spaced else None
        shown = text[(before or token).start : (after or token).end]
        separators = _LIKE_A_DECIMAL_MARK if early else _TOUCHING
        for neighbour in (before, after):
            if neighbour is not None and neighbour.text in separators:
                return Refusal(
                    Reason.AMBIGUOUS_NUMBER,
                    f"the {neighbour.text!r} touches the digits in {shown!r}, so it is unclear "
                    "where the number starts or ends",
                    "the number written apart from punctuation, with one decimal point",
                )
        trailing = after is not None and after.text == "." and not _number_follows(found, index)
        if early and trailing:
            return Refusal(
                Reason.TRAILING_DECIMAL,
                f"{shown!r} ends in a decimal point with no digits after it",
                "the number written in full, such as 1240 or 1240.5",
            )
        strays = [] if early else [n for n in (before, after) if n is not None]
        for neighbour in strays:
            if neighbour.kind in {"other", "mark"} and neighbour.text not in DASHES:
                return _stray(neighbour.text, shown)
    return None


def _number_follows(found: list[Token], index: int) -> bool:
    after = index + 2
    return after < len(found) and not found[after].spaced and found[after].kind == "number"


def _stray(char: str, shown: str) -> Refusal:
    name = f"U+{ord(char[0]):04X}"
    return Refusal(
        Reason.UNRECOGNISED_TEXT,
        f"the character {char!r} ({name}) touches the digits in {shown!r}, which this reader "
        "does not read",
        "the number written with plain digits and one decimal point",
    )


def _unrecognised(found: list[Token], leftovers: list[int], spec: FieldSpec) -> Refusal | None:
    for index in leftovers:
        token = found[index]
        if token.kind in _BENIGN:
            continue
        shown = repr(token.text)
        if token.kind == "other":
            shown = f"the character {token.text!r} (U+{ord(token.text):04X})"
        return Refusal(
            Reason.UNRECOGNISED_TEXT,
            f"{shown} is not a {spec.label} value, label, standard or condition",
            f"a quote of just the {spec.label} value and its unit, such as 1.24 g/cm3",
        )
    return None
