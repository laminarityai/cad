"""The chain behind one number on a card: the steps that place it, or why no rule does."""

from dataclasses import dataclass
from typing import Literal

from cad.tables.materials import Source


@dataclass(frozen=True, slots=True)
class CheckStep:
    check_id: str
    version: str


@dataclass(frozen=True, slots=True)
class TableStep:
    material_key: str
    field: str
    source: Source


@dataclass(frozen=True, slots=True)
class ResearchedStep:
    """A value the server read from a quote on a page it fetched, signed in the project's
    research ledger as record `record`."""

    material_key: str
    field: str
    source: Source
    record: int


@dataclass(frozen=True, slots=True)
class ConfirmedStep:
    """A limit a person confirmed on the page, in the decision the card names."""

    brief_id: str
    decision_sha256: str
    requirement_id: str
    statement: str


@dataclass(frozen=True, slots=True)
class BoundStep:
    """A bound of a research request: the server accepts a researched `field` only in it."""

    field: str
    bound: Literal["low", "high"]


type Step = CheckStep | TableStep | ResearchedStep | ConfirmedStep | BoundStep


@dataclass(frozen=True, slots=True)
class Resolved:
    steps: tuple[Step, ...]


@dataclass(frozen=True, slots=True)
class Stale:
    reason: str


@dataclass(frozen=True, slots=True)
class Unresolved:
    reason: str


@dataclass(frozen=True, slots=True)
class NotVerified:
    """The agent's own measurement: information that no check made and nothing grades."""

    reason: str = "agent's own measurement"


@dataclass(frozen=True, slots=True)
class AgentCheckedNumber:
    """A number an approved agent-written check produced or read. Our team has not reviewed it."""

    reason: str = "agent-written check you approved, not reviewed by our team"


type Outcome = Resolved | Stale | Unresolved | NotVerified | AgentCheckedNumber
