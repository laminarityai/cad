from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from cad.briefs.origins import YOUR_WORDS
from cad.confirmations.answers import Edit, ItemKindName, ItemRef
from cad.projects.model import ProjectId


@dataclass(frozen=True, slots=True)
class Editable:
    """The row's number can be changed on the page: `row` names it in an Edit."""

    row: str
    placeholder: str


@dataclass(frozen=True, slots=True)
class Refused:
    """Edits the page will not record, with what the person should type instead."""

    message: str


type Changes = tuple[str, ...]
"""One plain sentence for each number the edits change, for the page that says what it recorded."""


@dataclass(frozen=True, slots=True)
class Row:
    headline: str
    quote: str
    decides: str
    editable: Editable | None = None
    source: str = YOUR_WORDS
    note: str = ""


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    brief_id: str
    context: str
    rows: tuple[Row, ...]


class ItemKind(Protocol):
    @property
    def name(self) -> ItemKindName: ...

    def pending(self, project: ProjectId) -> tuple[ItemRef, ...]: ...

    def section(self, ref: ItemRef) -> Section: ...

    def edit(self, ref: ItemRef, edits: Sequence[Edit]) -> Refused | Changes: ...


type Kinds = Mapping[ItemKindName, ItemKind]


def pending(kinds: Kinds, project: ProjectId) -> tuple[ItemRef, ...]:
    return tuple(ref for kind in kinds.values() for ref in kind.pending(project))
