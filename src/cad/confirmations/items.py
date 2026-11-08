"""What can wait on the person, and how the confirmation page shows it.

Each kind of item is one `ItemKind` in the registry (`cad.confirmations.registry`). The page code
asks the registry and never branches on a kind's name.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from cad.confirmations.answers import Edit, ItemKindName, ItemRef
from cad.projects.model import ProjectId


@dataclass(frozen=True, slots=True)
class Row:
    headline: str
    quote: str
    """The person's own words the row came from."""
    decides: str


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    context: str
    """What the rows are about, shown above them: for requirements, the brief text."""
    rows: tuple[Row, ...]


class ItemKind(Protocol):
    @property
    def name(self) -> ItemKindName: ...

    def pending(self, project: ProjectId) -> tuple[ItemRef, ...]:
        """Every item of this kind waiting on the person in the project, oldest first."""
        ...

    def section(self, ref: ItemRef) -> Section:
        """The item as the page shows it. Raises when its record no longer hashes to ref."""
        ...

    def edit(self, ref: ItemRef, edits: Sequence[Edit]) -> str | None:
        """A message for the person refusing the edits, or None to accept them."""
        ...


type Kinds = Mapping[ItemKindName, ItemKind]


def pending(kinds: Kinds, project: ProjectId) -> tuple[ItemRef, ...]:
    """Everything waiting on the person in the project, in page order: kind by kind."""
    return tuple(ref for kind in kinds.values() for ref in kind.pending(project))
