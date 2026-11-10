import hashlib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from cad.accounts.principal import AccountId
from cad.briefs.model import MAX_NOTE_CHARS
from cad.projects.model import ProjectBusy, ProjectId, TamperedProject
from cad.records import signed
from cad.records.roots import project_store
from cad.variants import key

type ItemKindName = Literal["requirements", "context_part"]
MAX_EDIT_CHARS: Final = 200
ANSWERS: Final = "answers"
LOG = logging.getLogger(__name__)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ItemRef(_Frozen):
    kind: ItemKindName
    slot: str
    sha256: str


class Edit(_Frozen):
    row: str
    text: Annotated[str, Field(max_length=MAX_EDIT_CHARS)]


class ItemAnswer(_Frozen):
    item: ItemRef
    verdict: Literal["confirmed", "declined"]
    edits: tuple[Edit, ...] = ()


class PageAnswer(_Frozen):
    project: str
    answers: Annotated[tuple[ItemAnswer, ...], Field(min_length=1)]
    note: Annotated[str, Field(max_length=MAX_NOTE_CHARS)] = ""
    decided_at: datetime
    # None only on an answer stored before the page moved into the signed-in app.
    account: AccountId | None = None
    session_id: str | None = None

    @model_validator(mode="after")
    def _each_item_once(self) -> Self:
        items = [a.item for a in self.answers]
        if any(item in items[:index] for index, item in enumerate(items)):
            raise ValueError("a page lists each item once")
        return self


@dataclass(frozen=True, slots=True)
class Found:
    sha256: str
    page: PageAnswer
    item: ItemAnswer


@dataclass(frozen=True, slots=True)
class Ledger:
    answers: tuple[tuple[str, PageAnswer], ...]

    def of(self, ref: ItemRef) -> Found | None:
        for sha256, page in self.answers:
            for item in page.answers:
                if item.item == ref:
                    return Found(sha256, page, item)
        return None


def read_ledger(projects: Path, project: ProjectId) -> Ledger:
    directory = projects / project / ANSWERS
    if not os.path.lexists(directory):
        return Ledger(())
    store = project_store(projects)
    _require_key(store, directory, project)
    records = signed.read_numbered(store, directory, _slot_of(project))
    if records is None:
        raise TamperedProject(_report(projects, project))
    return Ledger(
        tuple((hashlib.sha256(r).hexdigest(), _parse(projects, project, r)) for r in records)
    )


def append_answer(projects: Path, project: ProjectId, answer: PageAnswer) -> bool:
    if answer.project != project:
        raise ValueError(f"an answer for project {answer.project} cannot go in {project}")
    directory = projects / project / ANSWERS
    store = project_store(projects)
    _require_key(store, directory, project)
    directory.mkdir(parents=True, exist_ok=True)
    listed = tuple(a.item for a in answer.answers)

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        for record in existing:
            if any(a.item in listed for a in _parse(projects, project, record).answers):
                return None
        return answer.model_dump_json().encode()

    try:
        stored = signed.append(store, directory, _slot_of(project), record_for)
    except signed.Tampered as error:
        raise TamperedProject(_report(projects, project)) from error
    except signed.Contended as error:
        LOG.warning("%s: %s", directory, error)
        raise ProjectBusy(f"project {project} is being answered concurrently; try again") from error
    return isinstance(stored, signed.Appended)


def _require_key(store: signed.Store, directory: Path, project: ProjectId) -> None:
    if store.key_exists() or not os.path.lexists(directory):
        return
    if signed.is_directory(directory) and all(p.name.startswith(".") for p in directory.iterdir()):
        return
    raise TamperedProject(_report(store.root, project))


def _parse(projects: Path, project: ProjectId, record: bytes) -> PageAnswer:
    try:
        page = PageAnswer.model_validate_json(record)
    except ValidationError as error:
        raise TamperedProject(_report(projects, project)) from error
    if page.project != project:
        raise TamperedProject(_report(projects, project))
    return page


def _slot_of(project: ProjectId) -> Callable[[int], str]:
    return lambda number: f"{project}/answer/{number}"


def _report(projects: Path, project: ProjectId) -> str:
    LOG.error(
        "%s holds an answer that %s did not sign or that cannot be read",
        projects / project / ANSWERS,
        key.key_path(projects),
    )
    return (
        f"project {project} has an answer this store did not sign or cannot read; "
        "the operator must delete the project's answers from the project store"
    )
