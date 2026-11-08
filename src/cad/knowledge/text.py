"""The one normal form for a name, a query and a unit's text.

Unicode format characters (zero-width spaces, soft hyphens, joiners, byte order marks) are
dropped, the text is NFKC-normalized and case-folded, typographic dashes become "-", and "PLA +"
or "PLA plus" becomes "PLA+". Any "word plus" joins, so "water plus salt" reads "water+ salt";
that only costs recall, because no name is "water+".

`tokens` cuts the normal form into words. A word keeps inner dots and slashes and a trailing
plus, so "5.5", "m5x0.8", "g/cm3" and "pla+" are each one word. A hyphen separates words, so
"PETG-HF" and "PETG HF" are the same name. Only quiet punctuation is dropped: commas, periods,
semicolons, colons, question marks, quotes, brackets and dashes. Any other character (a heavy
plus, a degree sign, "!", "*", "%", "#", "&") is a word of its own, so a spelling the normal form
does not know is a word no unit has, and the search finds nothing instead of dropping the
character and answering a different question.
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
    return SPELLED_PLUS.sub(r"\1+", text).casefold()


def _is_quiet(char: str) -> bool:
    return char in QUIET_PUNCTUATION or unicodedata.category(char) in QUIET_CATEGORIES


def tokens(text: str) -> tuple[str, ...]:
    return tuple(
        word for word in TOKEN.findall(normalize(text)) if word[0].isalnum() or not _is_quiet(word)
    )
