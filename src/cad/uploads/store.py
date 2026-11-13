"""The files a person adds to a project. Every file as sent is kept under its SHA-256 in the
project's `sources`. A STEP or STL file becomes a context part that the upload confirms; any other
file is a `Document` the chat agent reads."""

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.accounts.principal import PersonSession
from cad.confirmations.answers import ItemAnswer, PageAnswer, append_answer
from cad.context_parts.ids import ContextPartId
from cad.context_parts.ingest import Ingest, NotAPart, StepFile, StlFile
from cad.context_parts.model import MAX_NAME_CHARS, FromUpload, StepRead, StlRead
from cad.context_parts.store import BadContextPart, Stored, add_upload, newest_parts, write_content
from cad.projects.model import ProjectBusy, ProjectId, TamperedProject
from cad.records import files, signed
from cad.records.roots import project_store
from cad.uploads.model import TEXT, BadUpload, Document, Kind, UnknownFile
from cad.variants import entry

SOURCES: Final = "sources"
DOCUMENTS: Final = "documents"
MAX_TEXT_CHARS: Final = 200_000
LOG = logging.getLogger(__name__)


def keep(projects: Path, project: ProjectId, data: bytes) -> str:
    sha256 = hashlib.sha256(data).hexdigest()
    write_content(projects / project / SOURCES / sha256, data, sha256)
    return sha256


def add_part(
    projects: Path,
    project: ProjectId,
    name: str,
    kind: Kind,
    unit: str | None,
    data: bytes,
    person: PersonSession,
    ingest: Ingest,
) -> Stored:
    match kind.cad:
        case "step":
            read_as: StepRead | StlRead = StepRead()
            source: StepFile | StlFile = StepFile(data)
        case "stl":
            if unit not in ("mm", "in"):
                raise BadUpload("an STL file holds no units: say whether it is in mm or in")
            read_as, source = StlRead(unit=unit), StlFile(data, unit)
        case None:
            raise BadUpload(f"{name} is not a STEP or STL file")
    read = ingest(source)
    if isinstance(read, NotAPart):
        raise BadContextPart(f"{name} cannot be a part: {read.reason}")
    upload = FromUpload(
        file_name=name,
        file_sha256=keep(projects, project, data),
        read_as=read_as,
        account=person.account,
        session_id=person.session_id,
    )
    return add_upload(projects, project, _part_name(name), upload, read)


def decline_part(
    projects: Path, project: ProjectId, part: ContextPartId, note: str, person: PersonSession
) -> bool:
    """Writes a page answer that declines the uploaded part, so no check measures against it. False
    when the part is already declined."""
    found = next((one for one in newest_parts(projects, project) if one.record.id == part), None)
    if found is None or not isinstance(found.record.source, FromUpload):
        raise UnknownFile(f"project {project} has no uploaded part {part}")
    if found.outcome == "declined":
        return False
    answer = PageAnswer(
        project=project,
        answers=(ItemAnswer(item=found.ref, verdict="declined"),),
        note=note,
        decided_at=datetime.now(UTC),
        account=person.account,
        session_id=person.session_id,
    )
    return append_answer(projects, project, answer)


def add_document(
    projects: Path,
    project: ProjectId,
    name: str,
    kind: Kind,
    data: bytes,
    person: PersonSession,
    withheld: bool = False,
) -> Document:
    """Idempotent: the same bytes and the same choice in the same project return the document
    already stored. Adding the same bytes again with the other choice stores the new choice, and
    the newest record of a file is the one that counts."""
    if kind.document is None:
        raise BadUpload(f"{name} is not a document")
    if withheld and kind.document != "application/pdf":
        raise BadUpload(f"{name} is not a PDF: only a PDF can be kept from the agent as a standard")
    if kind.document in TEXT:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise BadUpload(f"{name} is not UTF-8 text") from error
    sha256 = keep(projects, project, data)
    record = Document(
        project=project,
        name=name,
        media_type=kind.document,
        sha256=sha256,
        size=len(data),
        added_at=datetime.now(UTC),
        account=person.account,
        session_id=person.session_id,
        withheld=withheld,
    )
    directory = projects / project / DOCUMENTS
    found: list[Document] = []

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        found[:] = [one for one in _parsed(project, existing) if one.sha256 == sha256]
        if found and found[0].withheld == withheld:
            return None
        found.clear()
        return record.model_dump_json().encode()

    try:
        signed.append(project_store(projects), directory, _slot_of(project), record_for)
    except signed.Tampered as error:
        raise TamperedProject(_report(project)) from error
    except signed.Contended as error:
        raise ProjectBusy(f"project {project} is being given a file concurrently") from error
    return found[0] if found else record


def documents(projects: Path, project: ProjectId) -> tuple[Document, ...]:
    directory = projects / project / DOCUMENTS
    raw = signed.read_numbered(project_store(projects), directory, _slot_of(project))
    if raw is None:
        raise TamperedProject(_report(project))
    return _parsed(project, raw)


def document(projects: Path, project: ProjectId, wanted: str) -> tuple[Document, bytes]:
    found = next((one for one in documents(projects, project) if one.id == wanted), None)
    if found is None:
        raise UnknownFile(f"project {project} has no file {wanted}; list_files names them")
    path = projects / project / SOURCES / found.sha256
    data = files.read_regular(path, entry.MAX_FILE_BYTES)
    if data is None or hashlib.sha256(data).hexdigest() != found.sha256:
        LOG.error("%s is missing or does not match its SHA-256", path)
        raise TamperedProject(
            f"file {wanted} of project {project} has lost its bytes; add the file again"
        )
    return found, data


def _part_name(file_name: str) -> str:
    stem = file_name.rsplit(".", 1)[0].strip() or file_name
    return stem[:MAX_NAME_CHARS]


def _parsed(project: ProjectId, raw: tuple[bytes, ...]) -> tuple[Document, ...]:
    try:
        held = tuple(Document.model_validate_json(one) for one in raw)
    except ValidationError as error:
        raise TamperedProject(_report(project)) from error
    if any(one.project != project for one in held):
        raise TamperedProject(_report(project))
    newest = {one.sha256: one for one in held}
    return tuple(newest.values())


def _slot_of(project: ProjectId) -> Callable[[int], str]:
    return lambda number: f"{project}/document/{number}"


def _report(project: ProjectId) -> str:
    return (
        f"project {project}'s file records failed the server's integrity check, so the project "
        "cannot use its files; start a new project and add the files there"
    )
