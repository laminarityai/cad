"""The one normal form for the corpus side and the query side of a search.

Unicode format characters (zero-width spaces, soft hyphens, joiners, byte order marks) are
dropped, the text is NFKC-normalized and case-folded, typographic dashes become "-", and
"PLA +" or "PLA plus" becomes "pla+".

`words` cuts the normal form into words. A word keeps inner dots and slashes and a trailing
plus, so "5.5", "m5x0.8", "g/cm3" and "pla+" are each one word, and "pla+" is not "pla". Any
other punctuation separates words, so "PETG-HF", "PETG_HF" and "PETG HF" are the same words.
Stopwords are dropped.
"""

import re
import unicodedata
from typing import Final

WORD: Final = re.compile(r"[^\W_]+(?:[./][^\W_]+)*\+?")
DASHES: Final = {code: "-" for code in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)}
SPELLED_PLUS: Final = re.compile(r"\b([a-z][a-z0-9]{1,7})\s+(?:\+(?=\s|$)|plus\b)")
STOPWORDS: Final = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how"}
    | {"in", "is", "it", "of", "on", "or", "the", "to", "what", "which", "with"}
)


def normalize(text: str) -> str:
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = unicodedata.normalize("NFKC", text).translate(DASHES).casefold()
    return SPELLED_PLUS.sub(r"\1+", text)


def words(text: str) -> tuple[str, ...]:
    return tuple(word for word in WORD.findall(normalize(text)) if word not in STOPWORDS)
