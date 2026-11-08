import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from cad.sources.fields import MAX_QUOTE_LENGTH, SPECS, Field, FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.scan import Leftover, Unclear, Value, scan, unlisted_unit

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


_SCIENTIFIC: Final = _ascii(r"\d(?:[eE][+-]?\d|\s*[x\u00d7*·]\s*10)")
_BOUND: Final = _ascii(
    r"[<>≤≥≦≧⩽⩾]|&[lg]t;"
    r"|(?<![A-Za-z])(?i:max|maximum|min|minimum|up\s+to|less\s+than|more\s+than|greater\s+than"
    r"|or\s+less|or\s+more|at\s+most|at\s+least)(?![A-Za-z])"
)
_CUBED: Final = _ascii(r"(?<![A-Za-z])((?i:cm|dm|m|in|ft)\.?)(\u207b?)\u00b3")
_GLUED_HIGH: Final = _ascii(r"[-\u2013\u2014~]\d+(?:[.,]\d+)*")
_SEPARATORS: Final = frozenset({"-", "\u2013", "\u2014", "~", "to"})
_KEEP_COMPATIBILITY: Final = "\u33a4\u33a5"
_APOSTROPHE_GROUPS: Final = _ascii(r"\d+(?:['\u2019\u02bc\u2032]\d+)+(?:[.,]\d+)?")


def one_quantity(quote: str, field: Field) -> Quantity | Refusal:
    """Read the single quantity of `field`'s dimension out of `quote`, or say why not.

    A quote is read only when its whole text fits the grammar in `scan`: one number with one
    unit from the field's list, optionally with a label, a standard, or a condition. Any other
    token refuses the quote, so the reader never has to pick between candidates and never
    assumes a unit. A number such as "1,240" or "1.240" can mean 1240 or 1.24, so it is refused:
    the field's band only rejects a reading, it never chooses between readings.
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
    folded = _CUBED.sub(lambda m: m[1] + ("-3" if m[2] else "^3"), quote)
    digit = next((c for c in folded if _is_foreign_digit(c)), None)
    if digit is not None:
        return Refusal(
            Reason.UNRECOGNISED_TEXT,
            f"the quote has the superscript, subscript or non-ASCII digit {digit!r}",
            f"a quote that writes the {spec.label} with plain digits 0 to 9",
        )
    text = unicodedata.normalize("NFKC", folded)
    text = re.sub("[\u200b-\u200d\ufeff]", "", text).replace("\u2212", "-")
    early = _early_refusal(text, spec)
    if early is not None:
        return early
    scanned = scan(text, spec)
    if isinstance(scanned, Refusal):
        return scanned
    values = [t for t in scanned if isinstance(t, Value)]
    leftovers = [t for t in scanned if isinstance(t, Leftover)]
    if len(values) == 1 and not leftovers:
        return _settle(values[0], spec)
    return _refusal(scanned, values, leftovers, spec)


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
        or "\u2070" <= char <= "\u209f"
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


def _refusal(
    tokens: list[Value | Leftover], values: list[Value], leftovers: list[Leftover], spec: FieldSpec
) -> Refusal:
    ranged = _range(tokens)
    if ranged is not None:
        return Refusal(
            Reason.RANGE,
            f"{ranged!r} is a range",
            f"one value for {spec.label}: choose the figure to use and quote it with its unit",
        )
    if len(values) > 1:
        return Refusal(
            Reason.SEVERAL_QUANTITIES,
            "found " + " and ".join(v.shown for v in values),
            f"a quote with only one {spec.label} value and its unit",
        )
    for item in leftovers:
        if re.fullmatch(r"-\d+(?:[.,]\d+)*", item.text):
            return Refusal(
                Reason.NEGATIVE,
                f"{item.text!r} is a negative value",
                f"a quote with the {spec.label}, which cannot be negative",
            )
    for item in leftovers:
        if item.kind == "unit_text" and not values:
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


def _is_number(token: Value | Leftover) -> bool:
    return isinstance(token, Value) or token.kind in {"number", "unit_text"}


def _range(tokens: list[Value | Leftover]) -> str | None:
    for index, low in enumerate(tokens[:-1]):
        if not _is_number(low):
            continue
        follower = tokens[index + 1]
        if isinstance(low, Leftover) and low.unit_text.lower() == "to" and _is_number(follower):
            return f"{low.shown} {follower.shown}"
        if not isinstance(follower, Leftover) or follower.kind != "other":
            continue
        if _GLUED_HIGH.fullmatch(follower.text):
            return f"{low.shown} {follower.text}"
        later = tokens[index + 2 : index + 3]
        if follower.text.lower() in _SEPARATORS and later and _is_number(later[0]):
            return f"{low.shown} {follower.text} {later[0].shown}"
    return None


def _settle(found: Value, spec: FieldSpec) -> Quantity | Refusal:
    number = found.number
    if isinstance(number, Unclear):
        return _ambiguous(number)
    if isinstance(found.tolerance, Unclear):
        return _ambiguous(found.tolerance)
    if found.tolerance is not None:
        limit = (
            Decimal(MAX_TOLERANCE_PERCENT)
            if found.percent
            else number * MAX_TOLERANCE_PERCENT / 100
        )
        if found.tolerance > limit:
            written = f"{found.tolerance}{' %' if found.percent else ''}"
            return Refusal(
                Reason.WIDE_TOLERANCE,
                f"the tolerance \u00b1 {written} is more than {MAX_TOLERANCE_PERCENT}% of {number}",
                f"one {spec.label} value with a tolerance of at most {MAX_TOLERANCE_PERCENT}%",
            )
    canonical = number * found.unit.to_canonical
    if not spec.low <= canonical <= spec.high:
        return Refusal(
            Reason.OUT_OF_BAND,
            f"{found.shown} is {canonical.normalize():f} {spec.canonical_unit}",
            f"a {spec.label} between {spec.low:g} and {spec.high:g} {spec.canonical_unit}",
        )
    return Quantity(float(number), found.unit.symbol, float(canonical))


def _ambiguous(number: Unclear) -> Refusal:
    return Refusal(
        Reason.AMBIGUOUS_NUMBER,
        number.detail,
        "the number written with one decimal point and no grouping",
    )
