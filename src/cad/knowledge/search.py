"""Keyword search over the knowledge corpus.

Each file is about one subject. List the names that mean exactly that subject under aliases; a
branded file's aliases each carry its maker or product line, so "PLA" names only a family file.
A search must name one alias, or it finds nothing; the section's names then choose the unit.

In full, a search has two steps and no score.

1. Identity. The query is cut into words (`cad.knowledge.text`). A subject is named when one of
   its aliases is a run of those words. A name inside a longer name is ignored, so "PETG HF"
   beats "PETG". If the longest names left belong to two subjects, or to none, the search finds
   nothing. Unit text never takes part: a unit that mentions ABS is not about ABS.
2. Section. The query's other words, minus stopwords, must equal one of a unit's names: its
   heading, or a key it declares in a `<!-- keys: ... -->` comment, each read the same way with
   the subject's own aliases and stopwords taken out. Equal, not contained: "PLA density" is not
   "Density of PLA-CF", and "PolyLite ASA density" is not "ABS density for comparison". The
   loader refuses two units of one subject with an equal name, so a search finds at most one
   unit. The source title, the unit's prose and its quotes never take part: a quote that
   mentions "mineral", "CF" or "95A" does not make the unit about mineral water, a CF grade or a
   95A hardness.

A hit is a pointer to a source, page and section, never a value for a check. Its text is cut at
MAX_TEXT_CHARS. Equality costs recall: a plural, a missing word or a word only the quote has
gives no hit unless the author declared it as a key, and the agent asks again.
"""

from dataclasses import dataclass
from typing import Final

from cad.knowledge.corpus import Corpus, Pointer, Unit
from cad.knowledge.sections import Name, section_words
from cad.knowledge.text import tokens

MAX_TEXT_CHARS: Final = 2000

type Span = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Hit:
    pointer: Pointer
    text: str


class Index:
    def __init__(self, corpus: Corpus) -> None:
        self._corpus = corpus
        self._units: dict[tuple[str, Name], Unit] = {
            (unit.subject, name): unit for unit in corpus.units.values() for name in unit.names
        }

    def search(self, query: str) -> tuple[Hit, ...]:
        words = tokens(query)
        subjects = {subject for subject, _ in self._named(words)}
        if len(subjects) != 1:
            return ()
        unit = self._units.get((subjects.pop(), section_words(words, self._corpus.aliases)))
        return (Hit(unit.pointer, unit.text[:MAX_TEXT_CHARS]),) if unit else ()

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
