import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.briefs.model import BriefId
from cad.projects.model import ProjectId
from cad.variants.entry import VariantId, variant_id
from cad.variants.store import BuildResult

MAX_MEMBERS: Final = 5


class SetRefused(Exception):
    pass


class NotConfirmed(SetRefused):
    pass


class SetFull(SetRefused):
    pass


class TamperedSet(SetRefused):
    pass


class SetBusy(SetRefused):
    pass


@dataclass(frozen=True, slots=True)
class SetKey:
    project: ProjectId
    brief_id: BriefId
    decision_sha256: str


class Member(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    code_sha256: str
    built_as: VariantId
    joined_at: datetime

    def live_id(self, image_tag: str) -> VariantId:
        return variant_id(self.code, image_tag)


class Joined(BaseModel):
    kind: Literal["joined"] = "joined"
    slot: int
    limit: int = MAX_MEMBERS
    already_member: bool


class NotJoined(BaseModel):
    kind: Literal["not_joined"] = "not_joined"
    reason: str = "only a built variant joins the set; fix the code and build it again"


class SetBuildResult(BuildResult):
    variant_set: Annotated[Joined | NotJoined, Field(discriminator="kind")] | None = None


def code_sha256(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()
