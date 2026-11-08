"""Split a quote into tokens from a closed set of classes. Every character lands in a token.

    standard  = a spelling from the table in `standards`, ending at a space, the end of the
                quote, or a separator with no digit right after it
    unlisted_standard = ISO, ASTM, DIN, or GB/T and a number, when no listed spelling fits
    condition = "at" or "@" and a temperature or a pressure, or "% RH"
    unit      = a mass over a volume, such as g/cm3, kg/m^3 or lbs./in.3
    number    = digits with "." or "," marks, or digit groups split by single spaces
    tolerance = ±, +/- or +-
    percent   = %
    label     = density, typical, nominal, value, and the word for density in a few languages
    separator = , ; : ( ) = [ ]
    mark      = a dash, ~, / or "..." (only ever part of a range or a negative sign)
    word      = any other run of text that starts with a letter
    other     = any other single character

No class skips a character. A word, an other or a stray mark never belongs to a value, so
the reader refuses a quote that has one. The tokens do not include whitespace; instead each
token says whether whitespace comes before it.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Final, Literal

from cad.sources.standards import STANDARDS

type Kind = Literal[
    "standard",
    "unlisted_standard",
    "condition",
    "unit",
    "number",
    "tolerance",
    "percent",
    "label",
    "separator",
    "mark",
    "word",
    "other",
]


@dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    text: str
    start: int
    end: int
    spaced: bool


_PLAIN_NUMBER = r"\d+(?:[.,]\d+)*"
_LENGTH = r"(?:cm|dm|m|in|ft)"
UNIT_PATTERN: Final = (
    r"(?<![A-Za-z])(?i:(?P<mass>kg|mg|g|t|tonnes?|lbs?\.?)"
    rf"(?: ?/ ?(?P<volume>{_LENGTH}\.?\^?3|cc|ml|l)|[·* ]?(?P<negative>{_LENGTH})-3))"
    r"(?![A-Za-z0-9^/-])"
)
_UNNAMED_UNIT = re.sub(r"\(\?P<\w+>", "(?:", UNIT_PATTERN)

_SPELLINGS: Final = sorted(
    (spelling for spellings in STANDARDS.values() for spelling in spellings), key=len, reverse=True
)
_SOURCES: Final[tuple[tuple[Kind, str, int], ...]] = (
    (
        "standard",
        "(?:" + "|".join(map(re.escape, _SPELLINGS)) + r")(?=$| |[,;:()=\[\]](?!\d))",
        re.ASCII,
    ),
    (
        "unlisted_standard",
        r"(?:ISO ?\d{3,5}(?:-\d{1,2})?(?::\d{4})?|ASTM ?[A-Z]\d+(?:-\d{1,2})?"
        r"|DIN(?: ?EN)?(?: ?ISO)? ?\d+(?:-\d{1,2})?|GB/T ?\d+(?:-\d{1,2})?)",
        re.ASCII,
    ),
    (
        "condition",
        rf"(?<![A-Za-z])(?i:at|@) ?(?:-?{_PLAIN_NUMBER} ?(?:° ?)?[CF]"
        rf"|{_PLAIN_NUMBER} ?(?:K|bar|atm|kPa|MPa|Pa|psi))(?![A-Za-z])"
        rf"|{_PLAIN_NUMBER} ?% ?RH(?![A-Za-z])",
        re.ASCII,
    ),
    ("unit", _UNNAMED_UNIT, re.ASCII),
    ("number", rf"\d{{1,3}}(?: \d{{3}})+(?!\d)(?:[.,]\d+)?|{_PLAIN_NUMBER}", re.ASCII),
    ("tolerance", r"±|\+/-|\+-", re.ASCII),
    ("percent", r"%", re.ASCII),
    (
        "label",
        r"(?<![A-Za-z])(?i:mass density|density|typical|nominal|value|densidad|dichte"
        r"|densité)(?![A-Za-z])|\u03c1",
        re.ASCII,
    ),
    ("separator", r"[,;:()=\[\]]", re.ASCII),
    ("mark", r"\.{2,}|[-\u2010-―~/]", re.ASCII),
    ("word", r"[^\W\d_][^ ,;:()=\[\]]*", 0),
    ("other", r".", re.DOTALL),
)
_CLASSES: Final[tuple[tuple[Kind, re.Pattern[str]], ...]] = tuple(
    (kind, re.compile(pattern, flags)) for kind, pattern, flags in _SOURCES
)


def is_whitespace(char: str) -> bool:
    return char.isspace() or unicodedata.category(char) == "Cc"


def fold(text: str) -> str:
    """NFKC, then every whitespace or control character run becomes one space."""
    normal = unicodedata.normalize("NFKC", text).replace("\u2212", "-")
    folded: list[str] = []
    for char in normal:
        if not is_whitespace(char):
            folded.append(char)
        elif not folded or folded[-1] != " ":
            folded.append(" ")
    return "".join(folded)


def tokens(text: str) -> list[Token]:
    """The tokens of `text`, which must already be folded."""
    found: list[Token] = []
    position = 0
    spaced = False
    while position < len(text):
        if text[position] == " ":
            spaced = True
            position += 1
            continue
        kind, end = _token_at(text, position)
        found.append(Token(kind, text[position:end], position, end, spaced))
        spaced = False
        position = end
    return found


def _token_at(text: str, position: int) -> tuple[Kind, int]:
    for kind, pattern in _CLASSES:
        match = pattern.match(text, position)
        if match is not None and match.end() > position:
            return kind, match.end()
    raise AssertionError("the other class matches every character")
