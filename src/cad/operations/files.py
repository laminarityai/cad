from typing import Annotated, Final

from pydantic import BaseModel, Field

from cad.briefs.origins import FILE_ID_PATTERN
from cad.context_parts.ingest import Facts
from cad.context_parts.store import newest_parts
from cad.operations.guidance import WITHHELD_REFUSAL
from cad.operations.model import Audience, Input, Tenant, operation
from cad.projects.membership import project_briefs
from cad.projects.model import (
    PROJECT_ID,
    PROJECT_ID_CHARS,
    ProjectId,
    UnknownProject,
    parse_project_id,
)
from cad.uploads import store
from cad.uploads.model import TEXT, Withheld
from cad.uploads.views import ContextPartView, DocumentView, document_view, part_view

MAX_TEXT_CHARS: Final = 100_000
LIST_FILES: Final = (
    "List what the person added to a project: the parts and the documents. A part is a STEP or "
    "STL file they uploaded, or a variant proposed with propose_context_part. Uploading confirms "
    "a part, so a part with outcome confirmed is ready. Each part comes with its facts in mm, "
    "in its own frame: the box, the solids, the holes with their diameters, centres and axes, "
    "the largest flats, the names in the file and how much of the file could not be read. They "
    "help you design with the part, and no check reads them. A part the new part must fit with "
    "stays where it is: model the new part in that part's frame, and propose fits_with, "
    "min_clearance or max_clearance on its part_id so the fit check measures against it. A "
    "document is a source: read it with read_file, unless it is withheld. A document with "
    "withheld true is a licensed standard the person kept from you: you see its name, read_file "
    "refuses it, and you may quote it only with words the person typed."
)
READ_FILE: Final = (
    "Read a document the person added to the project, by its file_id from list_files. A "
    "Markdown or text file comes back as text. A PDF or an image is attached for you to read in "
    "the web app's chat; another client gets only its name. A withheld document is refused. A "
    "requirement may quote a document: pass the file_id and the words. What you read is a "
    "source, never a measurement: a number from it reaches a check only as a requirement the "
    "person confirms."
)


class ProjectFilesInput(Input):
    project_id: Annotated[str, Field(max_length=PROJECT_ID_CHARS, pattern=PROJECT_ID.pattern)]


class PartFacts(BaseModel):
    part: ContextPartView
    facts: Facts


class ProjectFiles(BaseModel):
    project_id: str
    parts: tuple[PartFacts, ...]
    documents: tuple[DocumentView, ...]


class ReadFileInput(ProjectFilesInput):
    file_id: Annotated[str, Field(pattern=FILE_ID_PATTERN)]


class FileRead(BaseModel):
    """`attachments` names the files the chat attaches to this result for the model to read."""

    document: DocumentView
    text: str | None
    attachments: tuple[str, ...]


def list_files(tenant: Tenant, arguments: ProjectFilesInput) -> ProjectFiles:
    project = _known(tenant, arguments.project_id)
    projects = tenant.roots.projects
    return ProjectFiles(
        project_id=project,
        parts=tuple(
            PartFacts(part=part_view(one), facts=one.record.facts)
            for one in newest_parts(projects, project)
        ),
        documents=tuple(document_view(one) for one in store.documents(projects, project)),
    )


def read_file(tenant: Tenant, arguments: ReadFileInput) -> FileRead:
    project = _known(tenant, arguments.project_id)
    found, data = store.document(tenant.roots.projects, project, arguments.file_id)
    if found.withheld:
        raise Withheld(WITHHELD_REFUSAL.format(name=found.name))
    view = document_view(found)
    if found.media_type not in TEXT:
        return FileRead(document=view, text=None, attachments=(found.id,))
    text = data.decode("utf-8")
    if len(text) > MAX_TEXT_CHARS:
        text = f"{text[:MAX_TEXT_CHARS]}\n[cut: {len(text) - MAX_TEXT_CHARS} more characters]"
    return FileRead(document=view, text=text, attachments=())


def _known(tenant: Tenant, raw: str) -> ProjectId:
    project = parse_project_id(raw)
    if not project_briefs(tenant.roots, project):
        raise UnknownProject(f"no project {project} is stored")
    return project


OPERATIONS: Final = (
    operation(
        name="list_files",
        audience=Audience.AGENT,
        description=LIST_FILES,
        input=ProjectFilesInput,
        output=ProjectFiles,
        run=list_files,
    ),
    operation(
        name="read_file",
        audience=Audience.AGENT,
        description=READ_FILE,
        input=ReadFileInput,
        output=FileRead,
        run=read_file,
    ),
)
