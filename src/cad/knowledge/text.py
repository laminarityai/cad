"""How the knowledge base reads text: one normal form for a unit, a code and a query.

Text is NFKC-normalized, typographic dashes become "-", and "PLA +" or "PLA plus" becomes "PLA+".
FTS5's default unicode61 tokenizer would cut "PLA+" to "pla" and "5.5" to "5" and "5", so
`tokens` cuts the text itself and keeps inner dots, slashes and hyphens and a trailing plus:
M5x0.8, 5.5, 1/4-20, PETG-CF, PLA+.
"""

import re
import unicodedata
from typing import Final

TOKEN: Final = re.compile(r"[A-Za-z0-9]+(?:[./-][A-Za-z0-9]+)*\+?")
DASHES: Final = {code: "-" for code in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)}
SPELLED_PLUS: Final = re.compile(r"\b([A-Za-z]{2,8})\s+(?:\+|plus\b)", re.IGNORECASE)
SHOUTED: Final = re.compile(r"[A-Z][A-Z0-9]*(?:[./-][A-Z0-9]+)*\+?")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(DASHES)
    return SPELLED_PLUS.sub(r"\1+", text)


def tokens(text: str) -> list[str]:
    return TOKEN.findall(normalize(text))


def has_code_shape(token: str) -> bool:
    """A token that must be declared as a code: it has a letter and a digit or a plus."""
    return any(c.isalpha() for c in token) and (
        any(c.isdigit() for c in token) or token.endswith("+")
    )


def looks_like_a_code(token: str) -> bool:
    """A title or section that holds this token needs a `codes:` entry in its front matter."""
    return has_code_shape(token) or (len(token) >= 2 and SHOUTED.fullmatch(token) is not None)
