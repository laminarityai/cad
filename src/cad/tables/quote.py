"""The server's two checks on a quote: that it is on a page, and that a value is written in it as
one number. Research makes both on a researched value; the datasheet check uses `on_page`. The
agent reads the value and its unit from the page. Nothing here reads a unit, a label or a
sentence."""

import re
import unicodedata
from collections.abc import Iterator
from decimal import Decimal
from typing import Final

_DIGITS: Final = r"\d+(?:[.,]\d+)*(?:e[-+]?\d+)?"
_WORD: Final = re.compile(rf"[.,]?{_DIGITS}|[^\W\d_]+")
_NUMBER: Final = re.compile(rf"(?<![\w.,])(?:{_DIGITS}|[.,]\d+)")
_SPACE_GROUPED: Final = re.compile(r"(?<![\w.,])\d{1,3}(?: \d{3})+(?![\w.,])")
_CONTEXT: Final = 60


def on_page(quote: str, text: str) -> bool:
    """Whether the quote's words and numbers appear in that order on the page. Whitespace,
    punctuation, markup and case may differ: "Density | 1.25 g/cm3" is on a page whose text
    reads "density 1.25 g/cm 3". The quote may not start or end inside a number, so
    "960 kg/m3" is not on a page that says "8960 kg/m3" or "8,960 kg/m3", nor "modulus 2.1" on
    one that says "modulus 2.1e5"."""
    needle, hay, inside = _words(quote)[0], *_words(text)
    start = hay.find(needle) if needle else -1
    while start != -1:
        if start not in inside and start + len(needle) not in inside:
            return True
        start = hay.find(needle, start + 1)
    return False


def written_as_one_number(value: Decimal, quote: str) -> bool:
    """Whether the quote writes `value` as one number, with "." or "," as its decimal mark or
    as digit grouping: 1.24 is written in "1.24" and "1,24", but not in "124" or "1.245", and
    1240 is written in "1.24e3".
    Digits that follow a letter, as in "D638" or "cm3", are not a number, and "193 x 103" writes
    193 and 103. `cad.tables.datasheet_text.written_in_text_layer` reads a PDF text layer
    instead."""
    return any(reading == value for _, reading in _readings(_fold(quote).casefold()))


def where_written(value: Decimal, text: str, limit: int = 2) -> tuple[str, ...]:
    folded = _fold(text).casefold()
    found: list[str] = []
    for match, reading in _readings(folded):
        if reading == value and len(found) < limit:
            around = folded[max(0, match.start() - _CONTEXT) : match.end() + _CONTEXT]
            found.append(around.strip())
    return tuple(found)


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _words(text: str) -> tuple[str, frozenset[int]]:
    """The text's letters and numbers in order, case folded, with nothing between them except
    a space between two numbers, so that "1 24" never reads as "124"; and each place in that
    string that falls inside a number."""
    out: list[str] = []
    inside: set[int] = set()
    at = 0
    for word in _WORD.finditer(_fold(text).casefold()):
        token = word.group()
        number = token[-1].isdigit()
        if number and out and out[-1][-1].isdigit():
            out.append(" ")
            at += 1
        if number:
            inside.update(range(at + 1, at + len(token)))
        out.append(token)
        at += len(token)
    return "".join(out), frozenset(inside)


def _readings(text: str) -> Iterator[tuple[re.Match[str], Decimal]]:
    for match in _NUMBER.finditer(text):
        for reading in _token_readings(match.group()):
            yield match, reading
    for match in _SPACE_GROUPED.finditer(text):
        yield match, Decimal(match.group().replace(" ", ""))


def _token_readings(token: str) -> Iterator[Decimal]:
    """ "1,337" reads as 1337 and as 1.337; "1,24" only as 1.24, since a group of digits after
    a thousands mark has three."""
    mantissa, _, exponent = token.partition("e")
    head, *rest = re.split(r"[.,]", mantissa)
    head = head or "0"
    readings: list[str] = []
    if not rest:
        readings.append(head)
    if rest and all(len(group) == 3 for group in rest):
        readings.append(head + "".join(rest))
    if rest and all(len(group) == 3 for group in rest[:-1]):
        readings.append(head + "".join(rest[:-1]) + "." + rest[-1])
    for reading in readings:
        yield Decimal(f"{reading}e{exponent}" if exponent else reading)
