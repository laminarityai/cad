"""How the knowledge base reads text: one normal form for a unit, a code and a query.

Text loses its Unicode format characters (zero-width spaces, soft hyphens, joiners, byte order
marks), is NFKC-normalized, typographic dashes become "-", and "PLA +" or "PLA plus" becomes
"PLA+". A "word plus" join also fires on ordinary words ("water plus salt" reads "water+ salt"),
which only costs recall: no unit declares "water+", so the query finds nothing.
FTS5's default unicode61 tokenizer would cut "PLA+" to "pla" and "5.5" to "5" and "5", so
`tokens` cuts the text itself and keeps inner dots, slashes and hyphens and a trailing plus:
M5x0.8, 5.5, 1/4-20, PETG-CF, PLA+.

A plus or plus-like symbol that is left outside every token (a heavy plus, "(+)", "+/-") is a
spelling the normal form does not know, so `has_stray_plus` lets a search refuse the query
instead of dropping the symbol and answering a different question.
"""

import re
import unicodedata
from typing import Final

TOKEN: Final = re.compile(r"[A-Za-z0-9]+(?:[./-][A-Za-z0-9]+)*\+?")
DASHES: Final = {code: "-" for code in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)}
SPELLED_PLUS: Final = re.compile(
    r"\b([A-Za-z][A-Za-z0-9]{1,7})\s+(?:\+(?=\s|$)|plus\b)", re.IGNORECASE
)
SHOUTED: Final = re.compile(r"[A-Z][A-Z0-9]*(?:[./-][A-Z0-9]+)*\+?")


def normalize(text: str) -> str:
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    text = unicodedata.normalize("NFKC", text).translate(DASHES)
    return SPELLED_PLUS.sub(r"\1+", text)


def tokens(text: str) -> list[str]:
    return TOKEN.findall(normalize(text))


def has_stray_plus(text: str) -> bool:
    rest = TOKEN.sub(" ", normalize(text))
    return any(
        c == "+" or unicodedata.category(c) in ("Sm", "So") or "PLUS" in unicodedata.name(c, "")
        for c in rest
    )


def has_code_shape(token: str) -> bool:
    """A token that starts with a letter and has a digit or a trailing plus: M5x0.8, PLA+."""
    return token[:1].isalpha() and (any(c.isdigit() for c in token) or token.endswith("+"))


def looks_like_a_code(token: str) -> bool:
    """A token a unit must declare under `codes:` or `mentions:` when its text holds it."""
    return (has_code_shape(token) and token[0].isupper()) or (
        len(token) >= 2 and SHOUTED.fullmatch(token) is not None
    )
