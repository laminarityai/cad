"""The requests and answers of the person-only routes that add a file to a project and decline an
uploaded part (ADR-0012). `cad.server.uploads` serves them."""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.briefs.model import MAX_NOTE_CHARS
from cad.briefs.origins import MAX_FILE_NAME_CHARS
from cad.context_parts.ids import PART_ID_PATTERN
from cad.uploads.views import ContextPartView, DocumentView

UPLOAD_ROUTES: Final = frozenset(
    {
        ("add_file", "/v1/projects/{project_id}/files"),
        ("decline_part", "/v1/projects/{project_id}/parts/{part_id}/decline"),
    }
)
PATHS: Final = dict(UPLOAD_ROUTES)


class Added(BaseModel):
    kind: Literal["part", "document"]
    part: ContextPartView | None = None
    document: DocumentView | None = None


class AddFileInput(BaseModel):
    """`unit` is required for an STL, which holds no units, and ignored for any other file.
    `withheld` marks a PDF as a licensed standard that the agent never reads."""

    model_config = ConfigDict(extra="forbid")
    project_id: str
    name: Annotated[str, Field(min_length=1, max_length=MAX_FILE_NAME_CHARS, pattern=r"^[^/\\]+$")]
    unit: Literal["mm", "in"] | None = None
    withheld: bool = False


class DeclineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    part_id: Annotated[str, Field(pattern=PART_ID_PATTERN)]
    note: Annotated[str, Field(max_length=MAX_NOTE_CHARS)] = ""


class Declined(BaseModel):
    part_id: str
    declined: bool
