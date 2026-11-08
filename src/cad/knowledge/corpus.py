from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

CORPUS_PATH: Final = Path(__file__).resolve().parents[3] / "knowledge"


class InvalidCorpus(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Pointer:
    id: str
    title: str
    url: str
    page: str | None
    section: str
    retrieved: date


@dataclass(frozen=True, slots=True)
class Unit:
    pointer: Pointer
    text: str


@dataclass(frozen=True, slots=True)
class Corpus:
    version: str
    units: Mapping[str, Unit]


def load(path: Path = CORPUS_PATH) -> Corpus:
    raise NotImplementedError
