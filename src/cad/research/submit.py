from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cad.projects.model import ProjectId
from cad.research.fetch import FetchFailed, Page, fetch
from cad.research.fields import SPECS, Field
from cad.research.ledger import (
    AlreadyStored,
    Ledger,
    ResearchedRecord,
    Turned,
    append_record,
    read_ledger,
)
from cad.research.overlay import fill, overlay
from cad.research.quote import on_page, where_written, written_in
from cad.research.requests import ResearchRequest, request_for
from cad.tables.materials import FromResearch, Known, MaterialsTable


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ResearchAccepted(_Frozen):
    """The agent read `value` from `quote`, which the server found on the page at `url`; `value`
    is in the field's canonical `unit`. Checks that read this field for this project now read
    it, labelled researched."""

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
    value: float
    unit: str
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
    ledger = read_ledger(projects, question.project)
    if ledger.problem is not None:
        return ask(ledger.problem, other_source_could_answer=False)
    material = overlay(git, question.project, ledger).table.materials.get(question.key)
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
    magnitude = _canonical(question)
    if isinstance(magnitude, str):
        return ask(magnitude)
    page = fetcher(question.url)
    if isinstance(page, FetchFailed):
        return ask(page.reason)
    if not on_page(question.quote, page.text):
        return ask(_not_on_page(question, page.url, page.text))
    record = ResearchedRecord(
        project=question.project,
        key=question.key,
        field=question.field,
        magnitude=magnitude,
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
        return ask(stored.reason, other_source_could_answer=stored.other_source_could_answer)
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
            if (one.key, one.field, one.magnitude, one.url, one.quote) == (
                record.key,
                record.field,
                record.magnitude,
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
    unit = SPECS[question.field].canonical_unit
    same = (held.source.url, held.source.quote) == (question.url, question.quote)
    if not same or not isinstance(held.basis, FromResearch):
        return None
    if held.magnitude_in(unit) != _canonical(question):
        return None
    return ResearchAccepted(
        key=question.key,
        field=question.field,
        value=held.magnitude_in(unit),
        unit=unit,
        url=held.source.url,
        quote=held.source.quote,
        record=held.basis.record,
    )


def _canonical(question: Question) -> float | str:
    """The value in the field's canonical unit, or why the server cannot take it."""
    spec = SPECS[question.field]
    factor = spec.units.get(question.unit.strip())
    if factor is None:
        spellings = ", ".join(repr(one) for one in spec.units)
        return (
            f"the unit {question.unit!r} is not one the server converts for {spec.label}; "
            f"pass one of {spellings}"
        )
    written = Decimal(repr(question.value))
    if not written_in(written, question.quote):
        return (
            f"the value {written} is not written in the quote; pass the number exactly as the "
            "quote writes it, in the quote's unit, and a quote that contains it"
        )
    canonical = written * factor
    if not spec.admits(canonical):
        return f"{spec.label} {canonical:g} {spec.canonical_unit} is outside {spec.accepts}"
    return float(canonical)


def _not_on_page(question: Question, url: str, text: str) -> str:
    reason = (
        f"the quote does not appear on {url} as the server fetched it; copy its words and "
        "numbers in the page's order, and start and end it on whole numbers"
    )
    written = where_written(Decimal(repr(question.value)), text)
    if not written:
        return f"{reason}; the page does not write {question.value!r} anywhere"
    return f"{reason}; the page writes {question.value!r} here: " + " | ".join(
        repr(one) for one in written
    )
