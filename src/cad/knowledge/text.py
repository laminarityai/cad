"""The one normal form for a name, a query and a unit's text.

Unicode format characters (zero-width spaces, soft hyphens, joiners, byte order marks) are
dropped, the text is NFKC-normalized, typographic dashes become "-", and "PLA +" or "PLA plus"
becomes "PLA+". Any "word plus" joins, so "water plus salt" reads "water+ salt"; that only costs
recall, because no name is "water+".

`tokens` cuts the normal form into words. A word keeps inner dots and slashes and a trailing
plus, so "5.5", "m5x0.8", "g/cm3" and "pla+" are each one word. A hyphen or an underscore
separates words, so "PETG-HF", "PETG_HF" and "PETG HF" are the same name. Only quiet punctuation
is dropped: commas, periods, semicolons, colons, question marks, quotes, brackets and dashes. Any
other character (a heavy plus, a degree sign, "!", "*", "%", "#", "&") is a word of its own, so a
spelling the normal form does not know is a word no unit has, and the search finds nothing
instead of dropping the character and answering a different question.

Each word is case-folded unless its case can carry meaning: a word with a digit or a "/"
("Mg/m3", "M8", "85A"), or a word with a capital after its first letter and a small letter
("MPa", "mPa", "kN", "PolyTerra"). Such a word matches only in its own case, so "mg/m3" is not
"Mg/m3" and "mPa" is not "MPa". A bare symbol whose only capital is its first letter ("Mg",
"Pa") folds like any word.
"""

import re
import unicodedata
from typing import Final

TOKEN: Final = re.compile(r"[^\W_]+(?:[./][^\W_]+)*\+?|[^\w\s]")
DASHES: Final = {code: "-" for code in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)}
SPELLED_PLUS: Final = re.compile(r"\b([a-z][a-z0-9]{1,7})\s+(?:\+(?=\s|$)|plus\b)", re.IGNORECASE)


STOPWORDS: Final = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how"}
    | {"in", "is", "it", "of", "on", "or", "the", "to", "what", "which", "with"}
)
QUIET_PUNCTUATION: Final = frozenset(",.;:?'\"…")
QUIET_CATEGORIES: Final = frozenset({"Pd", "Ps", "Pe", "Pi", "Pf"})


def normalize(text: str) -> str:
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = unicodedata.normalize("NFKC", text).translate(DASHES)
    return SPELLED_PLUS.sub(r"\1+", text)


def _is_quiet(char: str) -> bool:
    return char in QUIET_PUNCTUATION or unicodedata.category(char) in QUIET_CATEGORIES


def _fold(word: str) -> str:
    if "/" in word or any(c.isdigit() for c in word):
        return word
    if any(c.isupper() for c in word[1:]) and any(c.islower() for c in word):
        return word
    return word.casefold()


def tokens(text: str) -> tuple[str, ...]:
    return tuple(
        _fold(word)
        for word in TOKEN.findall(normalize(text))
        if word[0].isalnum() or not _is_quiet(word)
    )
