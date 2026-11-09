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
    read = one_quantity(question.quote, question.field)
    if isinstance(read, Refusal):
        return ask(f"the quote cannot be read: {read.detail}; the server needs {read.needed}")
    page = fetcher(question.url)
    if isinstance(page, FetchFailed):
        return ask(page.reason)
    if not on_page(question.quote, page.text):
        return ask(
            f"the quote does not appear word for word on {page.url}, starting and ending where "
            "the page's words and numbers do; copy it exactly from the page as the server "
            "fetched it, without the page's markup"
        )
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


def on_page(quote: str, text: str) -> bool:
    """The quote must sit on boundaries in the page's text, so it never starts or ends partway
    through a number: "960 kg/m3" is not on a page that says "8960 kg/m3"."""
    needle, hay = _plain(quote).strip(), _plain(text)
    start = hay.find(needle) if needle else -1
    while start != -1:
        if _opens(hay, start) and _closes(hay, start + len(needle)):
            return True
        start = hay.find(needle, start + 1)
    return False


def _opens(text: str, at: int) -> bool:
    if at == 0:
        return True
    before = text[at - 1]
    in_number = before in ".," and (text[at].isdigit() or text[at - 2 : at - 1].isdigit())
    return not (before.isalnum() or in_number)


def _closes(text: str, at: int) -> bool:
    """A "." or "," after the quote ends it unless a digit follows, as in "0.35." at the end of
    a sentence; "0.3" is cut from "0.35"."""
    if at == len(text):
        return True
    after = text[at]
    return not (after.isalnum() or (after in ".," and text[at + 1 : at + 2].isdigit()))
