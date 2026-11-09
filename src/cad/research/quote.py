import re
import unicodedata
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Final

_FOLDS: Final = str.maketrans({"\u2018": "'", "\u2019": "'", "\u2212": "-"})
_NUMBER: Final = re.compile(r"(?<![\d.,])(?:\d+(?:[.,]\d+)*|[.,]\d+)(?:[eE][-+]?\d+)?")
_SPACE_GROUPED: Final = re.compile(r"(?<![\d.,])\d{1,3}(?: \d{3})+(?![\d.,])")
_SEPARATOR: Final = re.compile(r"[.,]")
_RUN: Final = re.compile(r"(?:[^\W_]|[.,])+")
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
    """Whether the quote's letters, digits and decimal marks appear in that order on the page.
    Spacing, markup and other punctuation are ignored, because a page's text and the agent's
    view of it render them differently: "Density | 1.25 g/cm3" is on a page whose table says
    "Density 1.25 g/cm<sup>3</sup>". The match never starts or ends partway through a number:
    "960 kg/m3" is not on a page that says "8960 kg/m3"."""
    needle, hay = _comparable(quote).strip(" .,"), _comparable(text)
    start = hay.find(needle) if needle else -1
    while start != -1:
        if _opens(hay, start) and _closes(hay, start + len(needle)):
            return True
        start = hay.find(needle, start + 1)
    return False


def written_in(value: Decimal, quote: str) -> bool:
    """Whether some number in the quote, read with "." or "," as its decimal mark or as digit
    grouping, equals `value`: 1.24 is written in "1,24 g/cm3" and 1240 in "1.24e3 kg/m3"."""
    return any(reading == value for _, reading in _readings(fold(quote)))


def where_written(value: Decimal, text: str, limit: int = 2) -> tuple[str, ...]:
    folded = fold(text)
    found: list[str] = []
    for match, reading in _readings(folded):
        if reading == value and len(found) < limit:
            around = folded[max(0, match.start() - _CONTEXT) : match.end() + _CONTEXT]
            found.append(around.strip())
    return tuple(found)


def _comparable(text: str) -> str:
    joined: list[str] = []
    for run in _RUN.findall(fold(text)):
        if joined and _joins_numbers(joined[-1], run):
            joined.append(" ")
        joined.append(run)
    return "".join(joined)


def _joins_numbers(before: str, after: str) -> bool:
    return (before[-1].isdigit() or before[-1] in ".,") and (
        after[0].isdigit() or (after[0] in ".," and after[1:2].isdigit())
    )


def _readings(text: str) -> Iterator[tuple[re.Match[str], Decimal]]:
    for match in _NUMBER.finditer(text):
        for reading in _token_readings(match.group()):
            yield match, reading
    for match in _SPACE_GROUPED.finditer(text):
        yield match, Decimal(match.group().replace(" ", ""))


def _token_readings(token: str) -> Iterator[Decimal]:
    mantissa, _, exponent = token.lower().partition("e")
    groups = _SEPARATOR.split(mantissa)
    if groups[0] == "":
        groups[0] = "0"
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


def _opens(text: str, at: int) -> bool:
    if at == 0:
        return True
    return not (text[at].isdigit() and (text[at - 1].isdigit() or text[at - 1] in ".,"))


def _closes(text: str, at: int) -> bool:
    if at == len(text):
        return True
    digits_continue = text[at].isdigit() and text[at - 1].isdigit()
    decimals_follow = text[at] in ".," and text[at + 1 : at + 2].isdigit()
    return not (digits_continue or decimals_follow)
