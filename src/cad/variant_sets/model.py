import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, StringConstraints

from cad.briefs.model import BriefId
from cad.errors import Refused
from cad.frozen import Frozen
from cad.projects.model import ProjectId
from cad.sandbox.bodies import Bodies, BodyName
from cad.variants.entry import VariantId, variant_id
from cad.variants.store import BuildResult

MAX_MEMBERS: Final = 5
# Not a `type` statement, so a client sees the bounds inline instead of in $defs.
Slot = Annotated[int, Field(strict=True, ge=1, le=MAX_MEMBERS)]


class SetRefused(Refused):
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


class SlotRefused(SetRefused):
    pass


class MaterialMissing(SetRefused):
    pass


class BodyMaterialsRefused(SetRefused):
    pass


class BodiesMissing(SetRefused):
    pass


type Reason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\n\r]+$"),
]


class MaterialChoice(Frozen):
    """The material the agent chose for a slot when no confirmed made_of names one. A design
    choice like the code: not a requirement, not a verdict. `key` is a materials table row, or
    project- and a key of the agent's own for a material it researched."""

    key: str
    reason: Reason


type Label = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40, pattern=r"^[^\n\r]+$"),
]
type Differs = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160, pattern=r"^[^\n\r]+$"),
]


class Option(Frozen):
    """What the agent calls a slot and how it differs from the set's other slots. A design note
    like the material choice: never a requirement or a verdict."""

    label: Label
    differs: Differs


class BodyChoice(Frozen):
    """The material the agent chose for one named body of a slot, when no confirmed made_of
    names one."""

    body: BodyName
    key: str
    reason: Reason


@dataclass(frozen=True, slots=True)
class Chosen:
    """What a revision records: one choice for a variant of one unnamed body, one per named body,
    or neither when the person's made_of sets the material of every body."""

    material: MaterialChoice | None = None
    materials: tuple[BodyChoice, ...] = ()


type Resolve = Callable[[Revision | None, Bodies | None], Chosen]
"""Given the slot's latest revision and the bodies the code built, None before it is built, what
the new revision records. Refuses when the build may not go ahead."""


class Revision(Frozen):
    """One signed record of the set's log: this code became what `slot` shows."""

    slot: int = Field(ge=1, le=MAX_MEMBERS)
    code: str
    code_sha256: str
    built_as: VariantId
    joined_at: datetime
    material: MaterialChoice | None = None
    option: Option | None = None
    materials: tuple[BodyChoice, ...] = Field(default=(), exclude_if=lambda each: not each)

    def live_id(self, image_tag: str) -> VariantId:
        return variant_id(self.code, image_tag)


class Member(Frozen):
    """A slot and every revision it has had, oldest first. The last one is what the set shows."""

    slot: int
    revisions: tuple[Revision, ...] = Field(min_length=1)

    @property
    def latest(self) -> Revision:
        return self.revisions[-1]


def group(log: tuple[Revision, ...]) -> tuple[Member, ...]:
    by_slot: dict[int, list[Revision]] = {}
    for revision in log:
        by_slot.setdefault(revision.slot, []).append(revision)
    return tuple(Member(slot=slot, revisions=tuple(by_slot[slot])) for slot in sorted(by_slot))


class Joined(BaseModel):
    kind: Literal["joined"] = "joined"
    slot: int
    revision: int
    limit: int = MAX_MEMBERS
    already_member: bool


class NotJoined(BaseModel):
    kind: Literal["not_joined"] = "not_joined"
    reason: str = "only a built variant joins the set; fix the code and build it again"


class SetBuildResult(BuildResult):
    variant_set: Annotated[Joined | NotJoined, Field(discriminator="kind")] | None = None
    context_parts_out_of_date: tuple[str, ...] = ()
    """Confirmed context parts that came from an earlier revision of the slot this build joined."""


def code_sha256(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()
