import re
import unicodedata
from dataclasses import dataclass
from typing import Final

import pint

from cad.sources.fields import MAX_QUOTE_LENGTH, SPECS, Field, FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.scan import BOUND_WORDS, Item, Number, Unit, Word, scan
from cad.tables.materials import UNITS, magnitude

__all__ = ["Field", "Reason", "Refusal", "one_quantity"]

_STANDARD = re.compile(r"\b(?:ISO|ASTM|GB/T|GB|EN|DIN|JIS|IEC)\s*[A-Z]?\d+(?:[-:.]\d+)*")
_TOLERANCE = re.compile(r"\s*(?:±|\+/-|\+-)\s*\d[\d.,]*\d?\s*%?")
_SCIENTIFIC = re.compile(r"\d(?:[eE][+-]?\d|\s*[x\u00d7*\u00b7]\s*10)")
_NEGATIVE = re.compile(r"(?<![\w.)\]])-\d")
_SPLIT = re.compile(r"([:=~≈≤≥<>;])")
_RANGE_SEPARATORS: Final = frozenset({"-", "\u2013", "—", "to", "~", "…", "..."})


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
    spec = SPECS[field]
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
    items = scan(text, spec)
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


def _early_refusal(text: str, spec: FieldSpec) -> Refusal | None:
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


def _within_band(found: _Bound, spec: FieldSpec) -> pint.Quantity | Refusal:
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


def _range(text: str, items: list[Item]) -> str | None:
    for index, item in enumerate(items):
        if not isinstance(item, Number):
            continue
        cursor = index + 1
        if cursor < len(items) and isinstance(items[cursor], Unit):
            cursor += 1
        if cursor + 1 >= len(items):
            continue
        separator, high = items[cursor], items[cursor + 1]
        if (
            isinstance(separator, Word)
            and separator.text.lower() in _RANGE_SEPARATORS
            and isinstance(high, Number)
            and not text[high.end :].lstrip().startswith("/")
        ):
            return text[item.start : high.end]
    return None


def _bind(text: str, items: list[Item]) -> tuple[list[_Bound], list[tuple[str, tuple[float, ...]]]]:
    bound: list[_Bound] = []
    unbound: list[tuple[str, tuple[float, ...]]] = []
    used: set[int] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Number):
            continue
        following = items[index + 1] if index + 1 < len(items) else None
        preceding = items[index - 1] if index > 0 else None
        if (
            isinstance(following, Unit)
            and not following.bracketed
            and not text[item.end : following.start].strip()
        ):
            used.add(index + 1)
            bound.append(_bound(text, items, item, following, index - 1, index + 2, item.start))
        elif (
            isinstance(preceding, Unit)
            and index - 1 not in used
            and _prefix_unit_applies(text, preceding, item)
        ):
            bound.append(
                _bound(text, items, item, preceding, index - 2, index + 1, preceding.start)
            )
        else:
            unbound.append((text[item.start : item.end], item.values))
    return bound, unbound


def _prefix_unit_applies(text: str, unit: Unit, number: Number) -> bool:
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
    items: list[Item],
    number: Number,
    unit: Unit,
    before: int,
    after: int,
    start: int,
) -> _Bound:
    end = max(number.end, unit.end)
    neighbours = [items[i] for i in (before, after) if 0 <= i < len(items)]
    bounded = any(
        isinstance(n, Word) and n.text.lower().rstrip(".") in BOUND_WORDS for n in neighbours
    )
    return _Bound(number.values, unit.unit, unit.fits, text[start:end].strip(), bounded)


def _distinct(found: list[_Bound]) -> list[_Bound]:
    seen: dict[tuple[tuple[float, ...], str], _Bound] = {}
    for item in found:
        seen.setdefault((item.values, f"{item.unit}"), item)
    return list(seen.values())
