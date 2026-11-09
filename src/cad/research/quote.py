import re
import unicodedata
from collections.abc import Iterator, Mapping
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Final

_FOLDS: Final = str.maketrans({"\u2018": "'", "\u2019": "'", "\u2212": "-"})
_NUMBER: Final = re.compile(
    r"(?:(?<![\w.,])-)?(?<![\w.,])(?:\d+(?:[.,]\d+)*|[.,]\d+)(?:e[-+]?\d+)?"
)
_SPACE_GROUPED: Final = re.compile(r"(?<![\w.,-])\d{1,3}(?: \d{3})+(?![\d.,])")
_SEPARATOR: Final = re.compile(r"[.,]")
_RUN: Final = re.compile(r"(?:[^\W_]|[.,])+|-")
_DIGIT_AHEAD: Final = re.compile(r"[.,]?\d")
_EXPONENT: Final = re.compile(r"e[-+]?\d")
_UNIT_TOKEN: Final = re.compile(r"[^\W\d_]+|\d+")
_CONTEXT: Final = 60


def fold(text: str) -> str:
    normal = unicodedata.normalize("NFKC", text).translate(_FOLDS).casefold()
    folded: list[str] = []
    for char in normal:
        if not (char.isspace() or unicodedata.category(char) == "Cc"):
            folded.append(char)
        elif not folded or folded[-1] != " ":
            folded.append(" ")
    return "".join(folded)


def on_page(quote: str, text: str) -> bool:
    """Whether the quote's letters, digits, decimal marks and minus signs appear in that order
    on the page. Spacing, markup and other punctuation are ignored, because a page's text and
    the agent's view of it render them differently: "Density | 1.25 g/cm3" is on a page whose
    table says "Density 1.25 g/cm<sup>3</sup>". The match never starts or ends partway through
    a word or a number, so it cannot drop a sign, an exponent or a unit's prefix: "960 kg/m3"
    is not on a page that says "8960 kg/m3", nor "ratio 0.3" on one that says "ratio -0.3"."""
    needle = _comparable(fold(quote))[0].strip(" .,")
    folded = fold(text)
    hay, at = _comparable(folded)
    start = hay.find(needle) if needle else -1
    while start != -1:
        last = at[start + len(needle) - 1]
        if not _inside(folded, at[start]) and not _inside(folded, last + 1):
            return True
        start = hay.find(needle, start + 1)
    return False


def written_in(value: Decimal, quote: str) -> bool:
    """Whether some number in the quote, read with "." or "," as its decimal mark or as digit
    grouping, equals `value`: 1.24 is written in "1,24 g/cm3" and 1240 in "1.24e3 kg/m3". Digits
    that continue a word, such as the 638 of "D638" or the 3 of "g/cm3", are not a number."""
    return any(reading == value for _, reading in _readings(fold(quote)))


def units_beside(
    value: Decimal, quote: str, units: Mapping[str, Decimal]
) -> tuple[tuple[str, Decimal], ...]:
    """Each unit of `units` that the quote writes closest to a place it writes `value`, as its
    first spelling in `units` and its factor. Units are compared on letters and digits, so
    "kg/m³", "kg/m3" and "kg m-3" are one unit. In "290 MPa (42 ksi)" the unit beside 42 is
    ksi, and in "Tensile strength (MPa) 55-75" the unit beside 75 is MPa."""
    folded = fold(quote)
    written: dict[tuple[int, int], tuple[str, Decimal]] = {}
    for spelling, factor in units.items():
        pattern = _unit_pattern(spelling)
        for match in pattern.finditer(folded) if pattern else ():
            written.setdefault(match.span(), (spelling, factor))
    best: dict[tuple[int, int], tuple[str, Decimal]] = {}
    closest = len(folded)
    for match, reading in _readings(folded):
        for span, unit in written.items() if reading == value else ():
            gap = span[0] - match.end() if span[0] >= match.end() else match.start() - span[1]
            if gap < closest:
                best, closest = {}, gap
            if gap == closest:
                best[span] = unit
    return tuple(best.values())


def where_written(value: Decimal, text: str, limit: int = 2) -> tuple[str, ...]:
    folded = fold(text)
    found: list[str] = []
    for match, reading in _readings(folded):
        if reading == value and len(found) < limit:
            around = folded[max(0, match.start() - _CONTEXT) : match.end() + _CONTEXT]
            found.append(around.strip())
    return tuple(found)


@cache
def _unit_pattern(spelling: str) -> re.Pattern[str] | None:
    tokens = _UNIT_TOKEN.findall(fold(spelling))
    if not tokens:
        return None
    joined = r"[\W_]*".join(re.escape(token) for token in tokens)
    return re.compile(rf"(?<![^\W\d_]){joined}(?![^\W_])")


def _comparable(folded: str) -> tuple[str, tuple[int, ...]]:
    """The folded text's letters, digits, decimal marks and signs, and where each one is in it."""
    chars: list[str] = []
    at: list[int] = []
    for run in _RUN.finditer(folded):
        if run.group() == "-" and not _is_sign(folded, run.start()):
            continue
        if chars and _joins_numbers(chars[-1], run.group()):
            chars.append(" ")
            at.append(run.start())
        chars.extend(run.group())
        at.extend(range(run.start(), run.end()))
    return "".join(chars), tuple(at)


def _joins_numbers(before: str, after: str) -> bool:
    return (before.isdigit() or before in ".,") and (
        after[0].isdigit() or (after[0] in ".," and after[1:2].isdigit())
    )


def _is_sign(text: str, at: int) -> bool:
    if text[at] != "-" or not _DIGIT_AHEAD.match(text, at + 1):
        return False
    if at == 0:
        return True
    before = text[at - 1]
    if before == "e":
        return at >= 2 and text[at - 2].isdigit()
    return not (before.isalnum() or before in ".,")


def _inside(text: str, at: int) -> bool:
    """Whether the characters at `at - 1` and `at` belong to one word or one number."""
    if not 0 < at < len(text):
        return False
    before, char = text[at - 1], text[at]
    if char.isdigit():
        return before.isalnum() or before in ".," or (before == "-" and _is_sign(text, at - 1))
    if char.isalpha():
        exponent = before.isdigit() and _EXPONENT.match(text, at) is not None
        return before.isalpha() or exponent
    if char == "-":
        return before == "e" and _is_sign(text, at)
    if char in ".,":
        return before.isdigit() and text[at + 1 : at + 2].isdigit()
    return False


def _readings(text: str) -> Iterator[tuple[re.Match[str], Decimal]]:
    for match in _NUMBER.finditer(text):
        for reading in _token_readings(match.group()):
            yield match, reading
    for match in _SPACE_GROUPED.finditer(text):
        yield match, Decimal(match.group().replace(" ", ""))


def _token_readings(token: str) -> Iterator[Decimal]:
    mantissa, _, exponent = token.lower().partition("e")
    groups = _SEPARATOR.split(mantissa)
    if groups[0] in ("", "-"):
        groups[0] += "0"
    candidates = [groups[0]] if len(groups) == 1 else []
    if len(groups) > 1 and all(len(group) == 3 for group in groups[1:]):
        candidates.append("".join(groups))
    if len(groups) > 1 and all(len(group) == 3 for group in groups[1:-1]):
        candidates.append("".join(groups[:-1]) + "." + groups[-1])
    for candidate in candidates:
        try:
            yield Decimal(f"{candidate}e{exponent}" if exponent else candidate)
        except InvalidOperation:
            continue
