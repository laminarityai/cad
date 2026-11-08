from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from cad.confirmations.answers import Edit, ItemKindName, ItemRef
from cad.projects.model import ProjectId


@dataclass(frozen=True, slots=True)
class Editable:
    """The row's number can be changed on the page: `row` names it in an Edit."""

    row: str
    placeholder: str


@dataclass(frozen=True, slots=True)
class Row:
    headline: str
    quote: str
    decides: str
    editable: Editable | None = None


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    context: str
    rows: tuple[Row, ...]


class ItemKind(Protocol):
    @property
    def name(self) -> ItemKindName: ...

    def pending(self, project: ProjectId) -> tuple[ItemRef, ...]: ...

    def section(self, ref: ItemRef) -> Section: ...

    def edit(self, ref: ItemRef, edits: Sequence[Edit]) -> str | None: ...


type Kinds = Mapping[ItemKindName, ItemKind]


def pending(kinds: Kinds, project: ProjectId) -> tuple[ItemRef, ...]:
    return tuple(ref for kind in kinds.values() for ref in kind.pending(project))
