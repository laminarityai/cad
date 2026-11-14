"""Ranked keyword search over the knowledge corpus.

A search returns the k units that best match the query's words, best first, and nothing when no
word matches. It does not decide which unit is about what the user means: the caller reads each
hit's subject and quote and chooses. A hit is a pointer to a source, page and section, never a
value for a check.

The score is BM25F over four fields of a unit: a name, its source's title, its heading (the
section title and its keys), and its text. A unit's names are its subject and each alias, and it
scores with the name that fits the query best, so a family file's long chemical name does not
dilute its short one. A word in the name or the heading counts three times a word in the text or
the title, so "ABS density" ranks the ABS density section above a PLA section whose text mentions
ABS. Both sides read words through `cad.knowledge.text`, so case, dashes, Unicode forms and the
spellings of "PLA+" match.
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
TITLE_WEIGHT: Final = 1.0
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
class _Field:
    words: Counter[str]
    scale: float
    """The field's weight over BM25F's length norm, so a word counts `words[word] * scale`."""


@dataclass(frozen=True, slots=True)
class _Terms:
    unit: Unit
    names: tuple[Counter[str], ...]
    others: tuple[tuple[float, Counter[str]], ...]
    """The weighted fields that every name of the unit scores with: title, heading and text."""


def _terms(unit: Unit) -> _Terms:
    names = (unit.subject.replace("-", " "), *unit.aliases)
    return _Terms(
        unit,
        tuple(Counter(words(name)) for name in names),
        (
            (TITLE_WEIGHT, Counter(words(unit.pointer.title))),
            (HEADING_WEIGHT, Counter(words(" ".join((unit.pointer.section, *unit.keys))))),
            (TEXT_WEIGHT, Counter(words(unit.text))),
        ),
    )


def _mean(lengths: list[int]) -> float:
    return max(1.0, sum(lengths) / max(1, len(lengths)))


def _field(weight: float, words: Counter[str], mean: float) -> _Field:
    return _Field(words, weight / (1 - B + B * words.total() / mean))


def _bounded(text: str) -> str:
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[: MAX_TEXT_CHARS - len(CUT_MARK)].rstrip() + CUT_MARK


class Index:
    def __init__(self, corpus: Corpus) -> None:
        terms = [_terms(u) for u in sorted(corpus.units.values(), key=lambda u: u.pointer.id)]
        name_length = _mean([n.total() for t in terms for n in t.names])
        means = [_mean([t.others[i][1].total() for t in terms]) for i in range(3)]
        self._units = [
            (
                t.unit,
                tuple(_field(NAME_WEIGHT, name, name_length) for name in t.names),
                tuple(_field(w, f, mean) for (w, f), mean in zip(t.others, means, strict=True)),
            )
            for t in terms
        ]
        found = Counter(
            word
            for t in terms
            for word in set[str]().union(*t.names, *(field for _, field in t.others))
        )
        units = len(terms)
        self._idf = {w: math.log(1 + (units - df + 0.5) / (df + 0.5)) for w, df in found.items()}

    def search(self, query: str, k: int = 5) -> tuple[Hit, ...]:
        if k < 1:
            raise ValueError(f"k must be at least 1, not {k}")
        asked = set(words(query)) & self._idf.keys()
        scored = [
            (max(self._score((name, *others), asked) for name in names), unit)
            for unit, names, others in self._units
        ]
        best = sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: -pair[0])[:k]
        return tuple(Hit(unit.pointer, unit.subject, _bounded(unit.text)) for _, unit in best)

    def _score(self, fields: tuple[_Field, ...], asked: set[str]) -> float:
        score = 0.0
        for word in asked:
            tf = sum(field.words[word] * field.scale for field in fields)
            score += self._idf[word] * tf / (K1 + tf)
        return score
