"""Keyword search over the knowledge corpus, on stdlib sqlite FTS5.

Text, codes and queries share one normal form and one tokenizer, `cad.knowledge.text`, so that
"PLA+" stays one token, "5.5" stays one token, and "PLA plus" or "PETG\u2014HF" read as PLA+ and
PETG-HF.

A query token is a code when it starts with a letter and has a digit or a trailing "+" (M5x0.8,
PLA+), or when it is an all-caps or code-shaped token that any unit declares, mentions in its
text or names in its title (PLA, PETG, ABS, HF). A query that holds a plus symbol outside a
token returns nothing.

A hit is confident when all of these hold. There is no score and no threshold.

1. Every code in the query is one of the unit's declared codes. A code that the unit merely
   mentions in its text, or lists under `mentions:`, does not count. A unit about PLA that says
   "lower than ABS" is not about ABS, and one about PLA+ that says "than ordinary PLA" is not
   about PLA.
2. Every other token of the query that is not a stopword is a token of the unit's title, section
   or text, ignoring case.
3. The query holds a code, or at least two other tokens.
4. Hits that declare different codes return nothing, whether or not the query has a code:
   "PolyTerra density" fits PLA and PLA+ equally, and "PETG density" fits PETG and PETG HF, so the
   search does not pick. "PETG HF density" resolves because only one unit declares HF.

Otherwise the search returns nothing. Requiring every word keeps "petg basic density" off a
PETG HF unit; the cost is that a missing word or a plural gives no hit. A hit is a pointer to a
source, page and section, never a value for a check. Hits come back in unit id order, at most
MAX_HITS, each with its text cut at MAX_TEXT_CHARS.
"""

import sqlite3
from dataclasses import dataclass
from typing import Final

from cad.knowledge.corpus import Corpus, Pointer
from cad.knowledge.text import has_code_shape, has_stray_plus, looks_like_a_code, tokens

MAX_HITS: Final = 5
MAX_TEXT_CHARS: Final = 2000
STOPWORDS: Final = frozenset(
    {"a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how"}
    | {"in", "is", "it", "of", "on", "or", "the", "to", "what", "which", "with"}
)


@dataclass(frozen=True, slots=True)
class Hit:
    pointer: Pointer
    text: str


class Index:
    def __init__(self, corpus: Corpus) -> None:
        self._units = list(corpus.units.values())
        self._vocabulary = frozenset(
            token.casefold()
            for unit in self._units
            for token in tokens(f"{unit.pointer.title} {unit.pointer.section} {unit.text}")
            if looks_like_a_code(token)
        ) | frozenset(code for unit in self._units for code in unit.codes | unit.mentions)
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
        if has_stray_plus(query):
            return ()
        terms = list(dict.fromkeys(t.casefold() for t in tokens(query)))
        terms = [t for t in terms if t not in STOPWORDS]
        codes = [t for t in terms if has_code_shape(t) or t in self._vocabulary]
        words = [t for t in terms if t not in codes]
        if not codes and len(words) < 2:
            return ()
        rows = self._rows(words) if words else range(len(self._units))
        found = [u for i in rows if (u := self._units[i]).codes.issuperset(codes)]
        if len({u.codes for u in found}) > 1:
            return ()
        hits = sorted(found, key=lambda unit: unit.pointer.id)
        return tuple(Hit(u.pointer, u.text[:MAX_TEXT_CHARS]) for u in hits[:MAX_HITS])

    def _rows(self, words: list[str]) -> list[int]:
        match = " AND ".join(f'"{w}"' for w in words)
        rows: list[tuple[int]] = self._db.execute(
            "SELECT rowid FROM unit WHERE unit MATCH ?", (match,)
        ).fetchall()
        return [row[0] for row in rows]
