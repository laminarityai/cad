"""Ranked keyword search over the knowledge corpus.

A search returns the k units that best match the query's words, best first, and nothing when no
word matches. It does not decide which unit is about what the user means: the caller reads each
hit's subject and quote and chooses. A hit is a pointer to a source, page and section, never a
value for a check.

The score is BM25F over three fields of a unit: a name, its heading (the section title and its
keys), and its text. A unit's names are its subject and each alias, and it scores with the name
that fits the query best, so a family file's long chemical name does not dilute its short one.
A word in the name or the heading counts FIELD_WEIGHTS times a word in the text, so "ABS density"
ranks the ABS density section above a PLA section whose text mentions ABS. Both sides read words
through `cad.knowledge.text`, so case, dashes, Unicode forms and the spellings of "PLA+" match.
"""

import math
from collections import Counter
from dataclasses import dataclass
from typing import Final

from cad.knowledge.corpus import Corpus, Pointer, Unit
from cad.knowledge.text import words

MAX_TEXT_CHARS: Final = 2000
CUT_MARK: Final = " […]"
NAME_WEIGHT: Final = 3.0
HEADING_WEIGHT: Final = 3.0
TEXT_WEIGHT: Final = 1.0
K1: Final = 1.2
B: Final = 0.75


@dataclass(frozen=True, slots=True)
class Hit:
    pointer: Pointer
    subject: str
    text: str
    """The unit's text, cut to at most MAX_TEXT_CHARS and ending in CUT_MARK when cut."""


@dataclass(frozen=True, slots=True)
class _Terms:
    unit: Unit
    names: tuple[Counter[str], ...]
    heading: Counter[str]
    text: Counter[str]


def _terms(unit: Unit) -> _Terms:
    names = (unit.subject.replace("-", " "), *unit.aliases)
    return _Terms(
        unit,
        tuple(Counter(words(name)) for name in names),
        Counter(words(" ".join((unit.pointer.section, *unit.keys)))),
        Counter(words(unit.text)),
    )


def _mean(lengths: list[int]) -> float:
    return max(1.0, sum(lengths) / max(1, len(lengths)))


def _bounded(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[: MAX_TEXT_CHARS - len(CUT_MARK)].rstrip() + CUT_MARK


class Index:
    def __init__(self, corpus: Corpus) -> None:
        self._terms = [_terms(u) for u in sorted(corpus.units.values(), key=lambda u: u.pointer.id)]
        self._name_length = _mean([n.total() for t in self._terms for n in t.names])
        self._heading_length = _mean([t.heading.total() for t in self._terms])
        self._text_length = _mean([t.text.total() for t in self._terms])
        found = Counter(
            word
            for t in self._terms
            for word in {*t.heading, *t.text}.union(*(set(n) for n in t.names))
        )
        units = len(self._terms)
        self._idf = {w: math.log(1 + (units - df + 0.5) / (df + 0.5)) for w, df in found.items()}

    def search(self, query: str, k: int = 5) -> tuple[Hit, ...]:
        asked = set(words(query)) & self._idf.keys()
        scored = [
            (max(self._score(t, name, asked) for name in t.names), t.unit) for t in self._terms
        ]
        best = sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: -pair[0])[:k]
        return tuple(Hit(unit.pointer, unit.subject, _bounded(unit.text)) for _, unit in best)

    def _score(self, terms: _Terms, name: Counter[str], asked: set[str]) -> float:
        fields = (
            (NAME_WEIGHT, name, self._name_length),
            (HEADING_WEIGHT, terms.heading, self._heading_length),
            (TEXT_WEIGHT, terms.text, self._text_length),
        )
        score = 0.0
        for word in asked:
            tf = sum(
                weight * field[word] / (1 - B + B * field.total() / mean)
                for weight, field, mean in fields
            )
            score += self._idf[word] * tf / (K1 + tf)
        return score
