from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cad.projects.model import ProjectId
from cad.research.fetch import FetchFailed, Page, fetch
from cad.research.ledger import (
    AlreadyStored,
    Ledger,
    ResearchedRecord,
    Turned,
    append_record,
    read_ledger,
)
from cad.research.overlay import fill, overlay
from cad.research.requests import ResearchRequest, request_for
from cad.sources.fields import SPECS, Field
from cad.sources.quantities import Refusal, one_quantity
from cad.sources.tokens import fold
from cad.tables.materials import FromResearch, Known, MaterialsTable


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ResearchAccepted(_Frozen):
    """The server read `value`, in `unit`, from `quote` on the page at `url`. Checks that read
    this field for this project now read it, labelled researched."""

    kind: Literal["accepted"] = "accepted"
    key: str
    field: Field
    value: float
    unit: str
    url: str
    quote: str
    record: int


class ResearchRefused(_Frozen):
    """No value was stored. `request`, when present, asks again for this field."""

    kind: Literal["refused"] = "refused"
    key: str
    field: Field
    reason: str
    request: ResearchRequest | None = None


type ResearchAnswer = ResearchAccepted | ResearchRefused
type Fetch = Callable[[str], Page | FetchFailed]


@dataclass(frozen=True, slots=True)
class Question:
    brief_id: str
    project: ProjectId
    key: str
    field: Field
    url: str
    quote: str


def submit(
    git: MaterialsTable,
    projects: Path,
    question: Question,
    *,
    fetcher: Fetch = fetch,
    today: Callable[[], date] = date.today,
) -> ResearchAnswer:
    ask = _Asker(question)
    current = overlay(git, question.project, read_ledger(projects, question.project)).table
    material = current.materials.get(question.key)
    if material is None:
        return ask(
            f"no row in the materials table has the key {question.key!r}",
            other_source_could_answer=False,
        )
    held = material.value(question.field)
    if isinstance(held, Known):
        again = _already_answered(question, held)
        if again is not None:
            return again
        kind = "researched" if isinstance(held.basis, FromResearch) else "cited"
        return ask(
            f"{question.key} already has a {kind} {question.field}, which research never "
            "replaces; score the variant again",
            other_source_could_answer=False,
        )
    page = fetcher(question.url)
    if isinstance(page, FetchFailed):
        return ask(page.reason)
    if _plain(question.quote) not in _plain(page.text):
        return ask(
            f"the quote does not appear word for word on {page.url}; copy it exactly from the "
            "page as the server fetched it, without the page's markup"
        )
    read = one_quantity(question.quote, question.field)
    if isinstance(read, Refusal):
        return ask(f"the quote cannot be read: {read.detail}; the server needs {read.needed}")
    record = ResearchedRecord(
        project=question.project,
        key=question.key,
        field=question.field,
        magnitude=read.canonical,
        unit=SPECS[question.field].canonical_unit,
        url=page.url,
        title=page.title,
        quote=question.quote,
        retrieved=today(),
        sha256=page.sha256,
    )
    stored = append_record(
        projects, question.project, record, _admit_at_append(git, question.project, record)
    )
    if isinstance(stored, Turned):
        return ask(stored.reason)
    return ResearchAccepted(
        key=question.key,
        field=question.field,
        value=record.magnitude,
        unit=record.unit,
        url=record.url,
        quote=record.quote,
        record=stored.number,
    )


def _admit_at_append(
    git: MaterialsTable, project: ProjectId, record: ResearchedRecord
) -> Callable[[tuple[ResearchedRecord, ...]], AlreadyStored | Turned | None]:
    def admit(records: tuple[ResearchedRecord, ...]) -> AlreadyStored | Turned | None:
        materials = dict(overlay(git, project, Ledger(records)).table.materials)
        for number, one in enumerate(records, start=1):
            if (one.key, one.field, one.url, one.quote) == (
                record.key,
                record.field,
                record.url,
                record.quote,
            ):
                return AlreadyStored(number)
        filled = fill(materials, record, len(records) + 1)
        if isinstance(filled, list):
            return Turned("the value breaks the table's rules: " + "; ".join(filled))
        return None

    return admit


@dataclass(frozen=True, slots=True)
class _Asker:
    question: Question

    def __call__(self, reason: str, *, other_source_could_answer: bool = True) -> ResearchRefused:
        one = self.question
        request = (
            request_for(one.brief_id, one.key, one.field, (reason,))
            if other_source_could_answer
            else None
        )
        return ResearchRefused(key=one.key, field=one.field, reason=reason, request=request)


def _already_answered(question: Question, held: Known) -> ResearchAccepted | None:
    same = (held.source.url, held.source.quote) == (question.url, question.quote)
    if not same or not isinstance(held.basis, FromResearch):
        return None
    unit = SPECS[question.field].canonical_unit
    return ResearchAccepted(
        key=question.key,
        field=question.field,
        value=held.magnitude_in(unit),
        unit=unit,
        url=held.source.url,
        quote=held.source.quote,
        record=held.basis.record,
    )


def _plain(text: str) -> str:
    return fold(text).replace("\u2019", "'")
