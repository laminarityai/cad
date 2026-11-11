from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import Field

from cad.briefs.model import BriefId, BriefSpan
from cad.context_parts.ids import PART_ID_PATTERN, ContextPartId, part_id
from cad.context_parts.ingest import Facts
from cad.frozen import Frozen
from cad.projects.model import ProjectId

MAX_NAME_CHARS: Final = 80
UPDATE_PART: Final = (
    "the checks still measure the geometry the user confirmed. Propose that variant with "
    "propose_context_part to update the part: it keeps its part_id, so the requirements on it "
    "carry over, and the user confirms the new geometry with one click."
)
type Outcome = Literal["waiting", "confirmed", "declined"]


class FromVariant(Frozen):
    kind: Literal["variant"] = "variant"
    variant_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


type PartOrigin = Annotated[FromVariant, Field(discriminator="kind")]


class ContextPartRecord(Frozen):
    project: ProjectId
    brief_id: BriefId
    name: Annotated[str, Field(min_length=1, max_length=MAX_NAME_CHARS)]
    origin: BriefSpan
    source: PartOrigin
    brep_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    facts: Facts
    proposed_at: datetime
    replaces: Annotated[str, Field(pattern=PART_ID_PATTERN)] | None = None
    """The part this record gives newer geometry: its source variant is an earlier revision of the
    slot this record's variant came from. The part keeps that id, so requirements on it carry
    over, and checks measure this geometry once the person confirms it."""

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
