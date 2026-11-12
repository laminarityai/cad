from datetime import datetime
from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from cad.briefs.model import BriefId
from cad.briefs.origins import MAX_FILE_NAME_CHARS, BriefSpan
from cad.context_parts.ids import PART_ID_PATTERN, ContextPartId, part_id
from cad.context_parts.ingest import Facts
from cad.frozen import Frozen
from cad.projects.model import ProjectId

MAX_NAME_CHARS: Final = 80
SHA256: Final = r"^[0-9a-f]{64}$"
UPDATE_PART: Final = (
    "the checks still measure the geometry the user confirmed. Propose that variant with "
    "propose_context_part to update the part: it keeps its part_id, so the requirements on it "
    "carry over, and the user confirms the new geometry with one click."
)
type Outcome = Literal["waiting", "confirmed", "declined"]


class FromVariant(Frozen):
    kind: Literal["variant"] = "variant"
    variant_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


class StepRead(Frozen):
    format: Literal["step"] = "step"


class StlRead(Frozen):
    """An STL holds no units, so the person names them on every upload."""

    format: Literal["stl"] = "stl"
    unit: Literal["mm", "in"]


class FromUpload(Frozen):
    """A file the person sent from the workspace. Only the person-only upload handler writes this
    origin, with the person's account and session, so the record is the person's confirmation
    (ADR-0012)."""

    kind: Literal["upload"] = "upload"
    file_name: Annotated[str, Field(min_length=1, max_length=MAX_FILE_NAME_CHARS)]
    file_sha256: Annotated[str, Field(pattern=SHA256)]
    read_as: Annotated[StepRead | StlRead, Field(discriminator="format")]
    account: str
    session_id: str


type PartOrigin = Annotated[FromVariant | FromUpload, Field(discriminator="kind")]


class ContextPartRecord(Frozen):
    """`brief_id` and `origin` say which brief a variant was proposed for and the words that ask
    for the fit. An upload belongs to the project, not to one brief, so it has neither."""

    project: ProjectId
    brief_id: BriefId | None = None
    name: Annotated[str, Field(min_length=1, max_length=MAX_NAME_CHARS)]
    origin: BriefSpan | None = None
    source: PartOrigin
    brep_sha256: Annotated[str, Field(pattern=SHA256)]
    facts: Facts
    proposed_at: datetime
    replaces: Annotated[str, Field(pattern=PART_ID_PATTERN)] | None = None
    """The part this record gives newer geometry: its source variant is an earlier revision of the
    slot this record's variant came from. The part keeps that id, so requirements on it carry
    over, and checks measure this geometry once the person confirms it."""

    @model_validator(mode="after")
    def _brief_only_for_a_variant(self) -> Self:
        proposed = self.brief_id is not None and self.origin is not None
        if isinstance(self.source, FromVariant) != proposed:
            raise ValueError("a variant is proposed for a brief, quoting it; an upload is not")
        return self

    @property
    def id(self) -> ContextPartId:
        if self.replaces is not None:
            return ContextPartId(self.replaces)
        return part_id(self.brep_sha256)


class NewerRevision(Frozen):
    """The slot a confirmed part came from now shows this newer variant."""

    brief_id: BriefId
    slot: int
    variant_id: str
