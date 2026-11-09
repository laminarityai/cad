from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.briefs.model import BriefId, BriefSpan
from cad.context_parts.ids import ContextPartId, part_id
from cad.context_parts.ingest import Facts
from cad.projects.model import ProjectId

MAX_NAME_CHARS: Final = 80
type Outcome = Literal["waiting", "confirmed", "declined"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FromVariant(_Frozen):
    kind: Literal["variant"] = "variant"
    variant_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


# One arm per way a part arrives. Later: an uploaded STEP file, then Onshape and Fusion (#60).
type PartOrigin = Annotated[FromVariant, Field(discriminator="kind")]


class ContextPartRecord(_Frozen):
    project: ProjectId
    brief_id: BriefId
    name: Annotated[str, Field(min_length=1, max_length=MAX_NAME_CHARS)]
    origin: BriefSpan
    source: PartOrigin
    brep_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    facts: Facts
    proposed_at: datetime

    @property
    def id(self) -> ContextPartId:
        return part_id(self.brep_sha256)
