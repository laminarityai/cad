from collections.abc import Mapping
from typing import Protocol

from cad.knowledge.corpus import Corpus
from cad.knowledge.search import Index


class MakeCorpus(Protocol):
    def __call__(
        self, files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None
    ) -> Corpus: ...


class MakeIndex(Protocol):
    def __call__(
        self, files: Mapping[str, str], aliases: Mapping[str, list[str]] | None = None
    ) -> Index: ...
