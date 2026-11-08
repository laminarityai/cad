import re
import unicodedata
from typing import Final

import pint

from cad.sources.fields import MAX_QUOTE_LENGTH, SPECS, Field, FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.scan import Leftover, Value, scan, unlisted_unit
from cad.tables.materials import UNITS, magnitude

__all__ = ["Field", "Reason", "Refusal", "one_quantity"]

_SCIENTIFIC: Final = re.compile(r"\d(?:[eE][+-]?\d|\s*[x\u00d7*·]\s*10)")
_BOUND: Final = re.compile(
    r"[<>≤≥≦≧⩽⩾]|&[lg]t;"
    r"|(?<![A-Za-z])(?i:max|maximum|min|minimum|up\s+to|less\s+than|more\s+than|greater\s+than"
    r"|or\s+less|or\s+more|at\s+most|at\s+least)(?![A-Za-z])"
)
_NUMBER: Final = r"\d+(?:[.,]\d+)*"
_RANGE: Final = re.compile(
    rf"(?<![\w.,/^]){_NUMBER}\s*(?:\S{{1,12}}\s*)?(?:[-\u2013—~]|\bto\b)\s*{_NUMBER}"
)


def one_quantity(quote: str, field: Field) -> pint.Quantity | Refusal:
    """Read the single quantity of `field`'s dimension out of `quote`, or say why not.

    A quote is read only when its whole text fits the grammar in `scan`: one number with one
    unit from the field's list, optionally with a label, a standard, or a condition. Any other
    token refuses the quote, so the reader never has to pick between candidates and never
    assumes a unit. A number such as "1,240" or "1.240" can mean 1240 or 1.24. The reading that
    lands inside the field's band is used, and the quote is refused when both do.
    """
    spec = SPECS[field]
    if len(quote) > MAX_QUOTE_LENGTH:
        return Refusal(
            Reason.TOO_LONG,
            f"the quote has {len(quote)} characters",
            f"a quote of at most {MAX_QUOTE_LENGTH} characters around the one {spec.label} value",
        )
    text = unicodedata.normalize("NFKC", quote)
    text = re.sub(r"[​-‍﻿]", "", text).replace("\u2212", "-")
    early = _early_refusal(text, spec)
    if early is not None:
        return early
    scanned = scan(text, spec)
    if isinstance(scanned, Refusal):
        return scanned
    values = [t for t in scanned if isinstance(t, Value)]
    leftovers = [t for t in scanned if isinstance(t, Leftover)]
    if len(values) == 1 and not leftovers:
        return _within_band(values[0], spec)
    return _refusal(scanned, values, leftovers, spec)


def _early_refusal(text: str, spec: FieldSpec) -> Refusal | None:
    if _SCIENTIFIC.search(text):
        return Refusal(
            Reason.SCIENTIFIC_NOTATION,
            "the quote uses scientific notation",
            f"a quote that writes the {spec.label} in plain digits, such as 1240 kg/m3",
        )
    if _BOUND.search(text):
        return Refusal(
            Reason.BOUND,
            "the quote gives a limit (<, >, max, min, up to or less than), not a value",
            f"a quote that states the {spec.label} itself, not a limit on it",
        )
    return None


def _refusal(
    tokens: list[Value | Leftover], values: list[Value], leftovers: list[Leftover], spec: FieldSpec
) -> Refusal:
    shown = " ".join(t.shown for t in tokens)
    ranged = _RANGE.search(shown)
    if ranged is not None:
        return Refusal(
            Reason.RANGE,
            f"{ranged[0]!r} is a range",
            f"one value for {spec.label}: choose the figure to use and quote it with its unit",
        )
    if len(values) > 1:
        return Refusal(
            Reason.SEVERAL_QUANTITIES,
            "found " + " and ".join(v.shown for v in values),
            f"a quote with only one {spec.label} value and its unit",
        )
    for item in leftovers:
        if re.match(r"-\d", item.text):
            return Refusal(
                Reason.NEGATIVE,
                f"{item.text!r} is a negative value",
                f"a quote with the {spec.label}, which cannot be negative",
            )
    for item in leftovers:
        if item.kind == "unit_text":
            return unlisted_unit(item.unit_text, spec)
    numbers = [item.text for item in leftovers if item.kind == "number"]
    if numbers and not values:
        return Refusal(
            Reason.MISSING_UNIT,
            ", ".join(numbers) + (" has" if len(numbers) == 1 else " have") + " no unit",
            f"the unit of {numbers[0]}: type it on the page, it is not guessed",
        )
    if leftovers:
        return Refusal(
            Reason.UNRECOGNISED_TEXT,
            f"{leftovers[0].text!r} is not a {spec.label} value, label, standard or condition",
            f"a quote of just the {spec.label} value and its unit, such as 1.24 g/cm3",
        )
    return Refusal(
        Reason.NO_QUANTITY,
        "no number in the quote",
        f"a quote that contains the {spec.label} and its unit",
    )


def _within_band(found: Value, spec: FieldSpec) -> pint.Quantity | Refusal:
    if not found.readings:
        return Refusal(
            Reason.AMBIGUOUS_NUMBER,
            f"{found.shown!r} cannot be read as one number",
            "the number written with one decimal point and no grouping",
        )
    quantities = [UNITS.Quantity(reading, found.unit) for reading in found.readings]
    inside = [q for q in quantities if spec.low <= magnitude(q, spec.canonical_unit) <= spec.high]
    if len(inside) == 1:
        return inside[0]
    if inside:
        return Refusal(
            Reason.AMBIGUOUS_NUMBER,
            f"{found.shown} reads as "
            + " or ".join(f"{r:g}" for r in found.readings)
            + ", and both fit the band",
            "the number written with one decimal point and no grouping",
        )
    canonical = magnitude(quantities[0], spec.canonical_unit)
    return Refusal(
        Reason.OUT_OF_BAND,
        f"{found.shown} is {canonical:g} {spec.canonical_unit}",
        f"a {spec.label} between {spec.low:g} and {spec.high:g} {spec.canonical_unit}",
    )
