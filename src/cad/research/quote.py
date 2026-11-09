"""The two checks the server makes on a researched value: its quote is on the fetched page, and
the agent's number is written in that quote. Neither reads labels, units or prose."""

import re
import unicodedata
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Final

_APOSTROPHES: Final = str.maketrans({"\u2018": "'", "\u2019": "'", "\u2212": "-"})
_NUMBER: Final = re.compile(r"(?<![\d.,])(?:\d+(?:[.,]\d+)*|[.,]\d+)(?:[eE][-+]?\d+)?")
_SPACE_GROUPED: Final = re.compile(r"(?<![\d.,])\d{1,3}(?: \d{3})+(?![\d.,])")
_SEPARATOR: Final = re.compile(r"[.,]")


def fold(text: str) -> str:
    """NFKC, case folded, one apostrophe and minus sign, and every whitespace or control
    character run as one space."""
    normal = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).casefold()
    folded: list[str] = []
    for char in normal:
        if not (char.isspace() or unicodedata.category(char) == "Cc"):
            folded.append(char)
        elif not folded or folded[-1] != " ":
            folded.append(" ")
    return "".join(folded)


def on_page(quote: str, text: str) -> bool:
    """The quote must sit on boundaries in the page's text, so it never starts or ends partway
    through a number: "960 kg/m3" is not on a page that says "8960 kg/m3"."""
    needle, hay = fold(quote).strip(), fold(text)
    start = hay.find(needle) if needle else -1
    while start != -1:
        if _opens(hay, start) and _closes(hay, start + len(needle)):
            return True
        start = hay.find(needle, start + 1)
    return False


def written_in(value: Decimal, quote: str) -> bool:
    """Whether some number in the quote, read with "." or "," as its decimal mark or as digit
    grouping, equals `value`: 1.24 is written in "1,24 g/cm3" and 1240 in "1.24e3 kg/m3"."""
    folded = fold(quote)
    return any(reading == value for reading in _readings(folded))


def _readings(text: str) -> Iterator[Decimal]:
    for match in _NUMBER.finditer(text):
        yield from _token_readings(match.group())
    for match in _SPACE_GROUPED.finditer(text):
        yield Decimal(match.group().replace(" ", ""))


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
    before = text[at - 1]
    in_number = before in ".," and (text[at].isdigit() or text[at - 2 : at - 1].isdigit())
    return not (before.isalnum() or in_number)


def _closes(text: str, at: int) -> bool:
    """A "." or "," after the quote ends it unless a digit follows, as in "0.35." at the end of
    a sentence; "0.3" is cut from "0.35"."""
    if at == len(text):
        return True
    after = text[at]
    return not (after.isalnum() or (after in ".," and text[at + 1 : at + 2].isdigit()))
