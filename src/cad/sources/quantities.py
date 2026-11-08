import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from cad.sources.fields import MAX_QUOTE_LENGTH, SPECS, Field, FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.rules import refuse
from cad.sources.scan import Unclear, Value, values
from cad.sources.tokens import fold, tokens

__all__ = ["Field", "Quantity", "Reason", "Refusal", "one_quantity"]

# Real density tolerances are 1 to 2 %, so a wider one means the quote is not one value.
MAX_TOLERANCE_PERCENT: Final = 10


@dataclass(frozen=True, slots=True)
class Quantity:
    """The value as the quote wrote it, and the same amount in the field's canonical unit."""

    magnitude: float
    unit: str
    canonical: float


def _ascii(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.ASCII)


_SCIENTIFIC: Final = _ascii(
    r"\d(?:[eE][+-]?\d|\s*[x\u00d7*]\s*10|\s*·\s*10\s*(?:\^|\*\*|[²³¹⁰-⁻]))"
)
_BOUND: Final = _ascii(
    r"[<>≤≥≦≧⩽⩾]|&[lg]t;"
    r"|(?<![A-Za-z])(?i:max|maximum|min|minimum|up\s+to|less\s+than|more\s+than|greater\s+than"
    r"|or\s+less|or\s+more|at\s+most|at\s+least)(?![A-Za-z])"
)
_CUBED: Final = _ascii(r"(?<![A-Za-z])((?i:cm|dm|m|in|ft)\.?)(⁻?)³")
_KEEP_COMPATIBILITY: Final = "㎤㎥"
_APOSTROPHE_GROUPS: Final = _ascii(r"\d+(?:['\u2019\u02bc\u2032]\d+)+(?:[.,]\d+)?")


def one_quantity(quote: str, field: Field) -> Quantity | Refusal:
    """Read the single quantity of `field`'s dimension out of `quote`, or say why not.

    A quote is read only when every token fits the grammar in `tokens` and `scan`: one number
    with one unit from the field's list, optionally with a label, a standard, or a condition.
    Any other token refuses the quote, so the reader never has to pick between candidates and
    never assumes a unit. A number such as "1,240" or "1.240" can mean 1240 or 1.24, so it is
    refused: the field's band only rejects a reading, it never chooses between readings.
    """
    spec = SPECS[field]
    if len(quote) > MAX_QUOTE_LENGTH:
        return Refusal(
            Reason.TOO_LONG,
            f"the quote has {len(quote)} characters",
            f"a quote of at most {MAX_QUOTE_LENGTH} characters around the one {spec.label} value",
        )
    if _SCIENTIFIC.search(quote):
        return _scientific(spec)
    cubed = _CUBED.sub(lambda m: m[1] + ("-3" if m[2] else "^3"), quote)
    digit = next((c for c in cubed if _is_foreign_digit(c)), None)
    if digit is not None:
        return Refusal(
            Reason.UNRECOGNISED_TEXT,
            f"the quote has the superscript, subscript or non-ASCII digit {digit!r}",
            f"a quote that writes the {spec.label} with plain digits 0 to 9",
        )
    text = fold(cubed)
    early = _early_refusal(text, spec)
    if early is not None:
        return early
    found = tokens(text)
    items = values(found, spec)
    if isinstance(items, Refusal):
        return items
    refusal = refuse(text, found, items, spec)
    if refusal is not None:
        return refusal
    [value] = [item for item in items if isinstance(item, Value)]
    return _settle(value, text[found[value.first].start : found[value.last].end], spec)


def _scientific(spec: FieldSpec) -> Refusal:
    return Refusal(
        Reason.SCIENTIFIC_NOTATION,
        "the quote uses scientific notation",
        f"a quote that writes the {spec.label} in plain digits, such as 1240 kg/m3",
    )


def _is_foreign_digit(char: str) -> bool:
    if char.isascii() or char in _KEEP_COMPATIBILITY:
        return False
    return (
        unicodedata.category(char) == "Nd"
        or "⁰" <= char <= "₟"
        or re.search("[0-9]", unicodedata.normalize("NFKC", char)) is not None
    )


def _early_refusal(text: str, spec: FieldSpec) -> Refusal | None:
    if _SCIENTIFIC.search(text):
        return _scientific(spec)
    grouped = _APOSTROPHE_GROUPS.search(text)
    if grouped is not None:
        return Refusal(
            Reason.UNRECOGNISED_TEXT,
            f"{grouped[0]!r} groups digits with an apostrophe, which this reader does not read",
            "the number written with one decimal point and no grouping",
        )
    if _BOUND.search(text):
        return Refusal(
            Reason.BOUND,
            "the quote gives a limit (<, >, max, min, up to or less than), not a value",
            f"a quote that states the {spec.label} itself, not a limit on it",
        )
    return None


def _settle(found: Value, shown: str, spec: FieldSpec) -> Quantity | Refusal:
    number = found.number
    if isinstance(number, Unclear):
        return _ambiguous(number)
    if isinstance(found.tolerance, Unclear):
        return _ambiguous(found.tolerance)
    if found.tolerance is not None:
        if found.percent:
            limit = Decimal(MAX_TOLERANCE_PERCENT)
            wide = f"the tolerance ± {found.tolerance} % is more than {MAX_TOLERANCE_PERCENT}%"
        else:
            limit = number * MAX_TOLERANCE_PERCENT / 100
            wide = (
                f"the tolerance ± {found.tolerance} is more than "
                f"{MAX_TOLERANCE_PERCENT}% of {number}"
            )
        if found.tolerance > limit:
            return Refusal(
                Reason.WIDE_TOLERANCE,
                wide,
                f"one {spec.label} value with a tolerance of at most {MAX_TOLERANCE_PERCENT}%",
            )
    canonical = number * found.unit.to_canonical
    if not spec.admits(canonical):
        return Refusal(
            Reason.OUT_OF_BAND,
            f"{shown} is {canonical.normalize():f} {spec.canonical_unit}",
            f"a {spec.label} of {spec.accepts}",
        )
    return Quantity(float(number), found.unit.symbol, float(canonical))


def _ambiguous(number: Unclear) -> Refusal:
    return Refusal(
        Reason.AMBIGUOUS_NUMBER,
        number.detail,
        "the number written with one decimal point and no grouping",
    )
