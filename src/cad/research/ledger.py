import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import pydantic
from pydantic import PositiveInt, ValidationError

from cad.frozen import Frozen
from cad.projects.model import ProjectBusy, ProjectId
from cad.records import signed
from cad.records.roots import project_store
from cad.tables.fields import Field

RESEARCH: Final = "research"
_OPERATOR: Final = "the operator must delete the project's research directory"
LOG = logging.getLogger(__name__)


class ResearchedRecord(Frozen):
    project: str
    key: str
    field: Field
    magnitude: float
    unit: str
    url: str
    title: str
    quote: str
    retrieved: date
    sha256: str
    # The page of a PDF the quote is on, counted from 1. A web page has none.
    page: PositiveInt | None = pydantic.Field(default=None, exclude_if=lambda one: one is None)


@dataclass(frozen=True, slots=True)
class Ledger:
    records: tuple[ResearchedRecord, ...]
    problem: str | None = None


@dataclass(frozen=True, slots=True)
class Stored:
    number: int


@dataclass(frozen=True, slots=True)
class AlreadyStored:
    number: int


@dataclass(frozen=True, slots=True)
class Turned:
    reason: str
    other_source_could_answer: bool = True


type Admit = Callable[[tuple[ResearchedRecord, ...]], AlreadyStored | Turned | None]


def read_ledger(projects: Path, project: ProjectId) -> Ledger:
    directory = projects / project / RESEARCH
    raw = signed.read_numbered(project_store(projects), directory, _slot_of(project))
    records = None if raw is None else _parse_all(raw, project)
    if records is None:
        LOG.error("%s holds a record this store did not sign or cannot read", directory)
        return Ledger((), f"project {project}'s research records cannot be read; {_OPERATOR}")
    return Ledger(records)


def append_record(
    projects: Path, project: ProjectId, record: ResearchedRecord, admit: Admit
) -> Stored | AlreadyStored | Turned:
    if record.project != project:
        raise ValueError(f"a record for project {record.project} cannot go in {project}")
    directory = projects / project / RESEARCH
    store = project_store(projects)
    decided: list[AlreadyStored | Turned] = []

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        decided.clear()
        records = _parse_all(existing, project)
        if records is None:
            raise signed.Tampered
        verdict = admit(records)
        if verdict is not None:
            decided.append(verdict)
            return None
        return record.model_dump_json().encode()

    try:
        stored = signed.append(store, directory, _slot_of(project), record_for)
    except signed.Tampered:
        return Turned(
            f"project {project}'s research records cannot be read; {_OPERATOR}",
            other_source_could_answer=False,
        )
    except signed.Contended as error:
        raise ProjectBusy(
            f"project {project} is being researched concurrently; try again"
        ) from error
    if isinstance(stored, signed.Appended):
        return Stored(stored.number)
    return decided[0] if decided else Turned("the record was not stored")


def _parse_all(raw: tuple[bytes, ...], project: ProjectId) -> tuple[ResearchedRecord, ...] | None:
    try:
        records = tuple(ResearchedRecord.model_validate_json(one) for one in raw)
    except ValidationError:
        return None
    return None if any(one.project != project for one in records) else records


def _slot_of(project: ProjectId) -> Callable[[int], str]:
    return lambda number: f"{project}/research/{number}"
