"""What a person may add to a project, told apart by the file name's extension."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import Field

from cad.accounts.principal import AccountId
from cad.briefs.origins import MAX_FILE_NAME_CHARS
from cad.context_parts.model import SHA256
from cad.errors import NotFound
from cad.frozen import Frozen
from cad.projects.model import ProjectId, ProjectRefused

type MediaType = Literal[
    "application/pdf", "text/markdown", "text/plain", "image/png", "image/jpeg"
]
type CadFormat = Literal["step", "stl"]

CAD: Final[dict[str, CadFormat]] = {".step": "step", ".stp": "step", ".stl": "stl"}
DOCUMENTS: Final[dict[str, MediaType]] = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
TEXT: Final[frozenset[MediaType]] = frozenset({"text/markdown", "text/plain"})
ACCEPTED: Final = ", ".join(sorted({*CAD, *DOCUMENTS}))


class BadUpload(ProjectRefused):
    pass


class UnknownFile(ProjectRefused, NotFound):
    pass


class Document(Frozen):
    """A file the person added as a source: the chat agent reads it and a requirement may quote
    it. No check reads it."""

    project: ProjectId
    name: Annotated[str, Field(min_length=1, max_length=MAX_FILE_NAME_CHARS)]
    media_type: MediaType
    sha256: Annotated[str, Field(pattern=SHA256)]
    size: Annotated[int, Field(ge=0)]
    added_at: datetime
    account: AccountId
    session_id: str

    @property
    def id(self) -> str:
        return file_id(self.sha256)


def file_id(sha256: str) -> str:
    return f"file-{sha256[:16]}"


@dataclass(frozen=True, slots=True)
class Kind:
    """What the extension says the file is."""

    cad: CadFormat | None
    document: MediaType | None


def kind_of(name: str) -> Kind:
    dot = name.rfind(".")
    extension = name[dot:].lower() if dot > 0 else ""
    if extension in CAD:
        return Kind(CAD[extension], None)
    if extension in DOCUMENTS:
        return Kind(None, DOCUMENTS[extension])
    raise BadUpload(f"{name} is not a file this project takes; send one of {ACCEPTED}")
