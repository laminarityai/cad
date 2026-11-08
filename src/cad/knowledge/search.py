from dataclasses import dataclass

from cad.knowledge.corpus import Corpus, Pointer


@dataclass(frozen=True, slots=True)
class Hit:
    pointer: Pointer
    text: str


class Index:
    def __init__(self, corpus: Corpus) -> None:
        raise NotImplementedError

    def search(self, query: str) -> tuple[Hit, ...]:
        raise NotImplementedError
