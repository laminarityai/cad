"""Keyword search over the knowledge corpus, on stdlib sqlite FTS5.

FTS5's default unicode61 tokenizer treats every non-alphanumeric character as a separator, so
"PLA+" indexes as "pla" and "5.5" as "5" and "5": PLA would find PLA+, and 5 mm would find 5.5 mm.
Declaring "+./-" as tokenchars fixes that but keeps sentence punctuation ("density." is one token),
so the text is first cut by `TOKEN`, which keeps inner dots, slashes and hyphens and a trailing
plus: M5x0.8, 5.5, 1/4-20, PETG-CF, PLA+. A part or material code then matches only itself.

A hit is confident when all of these hold. There is no score and no threshold.

1. Every token of the query that is not a stopword is a token of the unit's title, section or
   text, ignoring case.
2. The query holds an identifier, or at least two such tokens. An identifier is a token with a
   digit, a trailing "+", or two or more capital letters and nothing else (PLA, PETG, HF).

Otherwise the search returns nothing. Requiring every word keeps "petg basic density" off a
PETG HF unit; the cost is that a missing word or a plural gives no hit. A hit is a pointer to a
source, page and section, never a value for a check. Hits come back in unit id order, at most
MAX_HITS, each with its text cut at MAX_TEXT_CHARS.
"""

import re
import sqlite3
from dataclasses import dataclass
from typing import Final

from cad.knowledge.corpus import Corpus, Pointer

MAX_HITS: Final = 5
MAX_TEXT_CHARS: Final = 2000
TOKEN: Final = re.compile(r"[A-Za-z0-9]+(?:[./-][A-Za-z0-9]+)*\+?")
SHOUTED: Final = re.compile(r"[A-Z]{2,}")
STOPWORDS: Final = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how"}
    | {"in", "is", "it", "of", "on", "or", "the", "to", "what", "which", "with"}
)


@dataclass(frozen=True, slots=True)
class Hit:
    pointer: Pointer
    text: str


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text)


def is_identifier(token: str) -> bool:
    return (
        any(c.isdigit() for c in token)
        or token.endswith("+")
        or SHOUTED.fullmatch(token) is not None
    )


class Index:
    def __init__(self, corpus: Corpus) -> None:
        self._units = list(corpus.units.values())
        self._db = sqlite3.connect(":memory:")
        self._db.execute(
            "CREATE VIRTUAL TABLE unit USING fts5(body, tokenize=\"unicode61 tokenchars '+./-'\")"
        )
        self._db.executemany(
            "INSERT INTO unit (rowid, body) VALUES (?, ?)",
            [
                (i, " ".join(tokens(f"{u.pointer.title} {u.pointer.section} {u.text}")))
                for i, u in enumerate(self._units)
            ],
        )

    def search(self, query: str) -> tuple[Hit, ...]:
        terms = list(dict.fromkeys(t for t in tokens(query) if t.casefold() not in STOPWORDS))
        if not any(is_identifier(t) for t in terms) and len(terms) < 2:
            return ()
        match = " AND ".join(f'"{t.casefold()}"' for t in terms)
        rows: list[tuple[int]] = self._db.execute(
            "SELECT rowid FROM unit WHERE unit MATCH ?", (match,)
        ).fetchall()
        hits = sorted((self._units[row[0]] for row in rows), key=lambda unit: unit.pointer.id)
        return tuple(Hit(u.pointer, u.text[:MAX_TEXT_CHARS]) for u in hits[:MAX_HITS])
