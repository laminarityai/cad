"""Keyword search over the knowledge corpus.

Each file is about one subject. List the names that mean exactly that subject under aliases; a
branded file's aliases each carry its maker or product line, so "PLA" names only a family file.
A search must name one alias, or it finds nothing; the section heading then chooses the unit.

In full, a search has two steps and no score.

1. Identity. The query is cut into words (`cad.knowledge.text`). A subject is named when one of
   its aliases is a run of those words. A name inside a longer name is ignored, so "PETG HF"
   beats "PETG". If the longest names left belong to two subjects, or to none, the search finds
   nothing. Unit text never takes part: a unit that mentions ABS is not about ABS.
2. Section. Within the named subject's units, every other query word that is not a stopword must
   be a word of the unit's section heading. At least one such word is needed to choose. The source
   title, the unit's prose and its quotes never take part: a quote that mentions "mineral", "CF"
   or "95A" does not make the unit about mineral water, a CF grade or a 95A hardness.

A hit is a pointer to a source, page and section, never a value for a check. Hits come back in unit
id order, at most MAX_HITS, each with its text cut at MAX_TEXT_CHARS. Requiring every word costs
recall: a plural, a missing word or a word only the quote has gives no hit and the agent asks
again.
"""

from dataclasses import dataclass
from typing import Final

from cad.knowledge.corpus import Corpus, Pointer
from cad.knowledge.text import STOPWORDS, tokens

MAX_HITS: Final = 5
MAX_TEXT_CHARS: Final = 2000

type Span = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Hit:
    pointer: Pointer
    text: str


class Index:
    def __init__(self, corpus: Corpus) -> None:
        self._corpus = corpus
        self._words = {
            unit.pointer.id: frozenset(tokens(unit.pointer.section))
            for unit in corpus.units.values()
        }

    def search(self, query: str) -> tuple[Hit, ...]:
        words = tokens(query)
        spans = self._named(words)
        if len({subject for subject, _ in spans}) != 1:
            return ()
        named = {i for _, (start, end) in spans for i in range(start, end)}
        rest = {w for i, w in enumerate(words) if i not in named and w not in STOPWORDS}
        subject = spans[0][0]
        if not rest:
            return ()
        hits = sorted(
            (
                unit
                for unit in self._corpus.units.values()
                if unit.subject == subject and rest <= self._words[unit.pointer.id]
            ),
            key=lambda unit: unit.pointer.id,
        )
        return tuple(Hit(u.pointer, u.text[:MAX_TEXT_CHARS]) for u in hits[:MAX_HITS])

    def _named(self, words: tuple[str, ...]) -> list[tuple[str, Span]]:
        """Each alias found in the query as (subject, span), minus names inside longer names."""
        found = [
            (subject, (start, start + len(alias)))
            for alias, subject in self._corpus.aliases.items()
            for start in range(len(words) - len(alias) + 1)
            if words[start : start + len(alias)] == alias
        ]
        return [
            (subject, span)
            for subject, span in found
            if not any(
                other != span and other[0] <= span[0] and span[1] <= other[1] for _, other in found
            )
        ]
