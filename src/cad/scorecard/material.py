"""`cad.scorecard.score` must never import this module: check versions hash what it imports."""

from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from cad.briefs.model import MadeOf, Requirement, describe
from cad.briefs.store import BriefRefused, ConfirmedSet
from cad.research.requests import ResearchRequest
from cad.scorecard.model import Scorecard

AGENT_CHOSE: Final = (
    "The agent chose this material. No requirement the person confirmed names it, so a result "
    "that depends on it rests on the agent's choice."
)


class MaterialPinned(BriefRefused):
    pass


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SetByRequirement(_Frozen):
    """The person confirmed a made_of requirement, and the card used its key."""

    kind: Literal["requirement"] = "requirement"
    requirement_id: str
    statement: str


class SetByAgent(_Frozen):
    kind: Literal["agent_argument"] = "agent_argument"
    statement: str = AGENT_CHOSE


type SetBy = Annotated[SetByRequirement | SetByAgent, Field(discriminator="kind")]


class MaterialUse(_Frozen):
    key: str
    set_by: SetBy


class ReportedScorecard(Scorecard):
    """A scorecard as the server returns it: the card, what set its material, and a research
    request for each material value a check needed that the table lacks."""

    material: MaterialUse
    research: tuple[ResearchRequest, ...] = Field(default=(), exclude_if=lambda one: not one)

    @model_validator(mode="after")
    def _names_the_scored_material(self) -> Self:
        if self.material.key != self.material_key:
            raise ValueError("material.key must be the key the card was scored with")
        return self


STORED: Final = TypeAdapter[ReportedScorecard | Scorecard](ReportedScorecard | Scorecard)


def pinned_by(confirmed: ConfirmedSet | None) -> Requirement | None:
    if confirmed is None:
        return None
    return next((r for r in confirmed.requirements if isinstance(r.target, MadeOf)), None)


def refuse_other_material(confirmed: ConfirmedSet | None, material_key: str) -> None:
    pin = pinned_by(confirmed)
    if pin is None or not isinstance(pin.target, MadeOf) or pin.target.material == material_key:
        return
    raise MaterialPinned(
        f"material_key {material_key!r} differs from the material the user confirmed, "
        f"{pin.target.material!r} (requirement {pin.id}). "
        f"Call score_variant again with material_key {pin.target.material!r}. "
        "No variant was scored."
    )


def reported(card: Scorecard, confirmed: ConfirmedSet | None) -> ReportedScorecard:
    pin = pinned_by(confirmed)
    set_by: SetBy = (
        SetByAgent()
        if pin is None
        else SetByRequirement(requirement_id=pin.id, statement=describe(pin))
    )
    return ReportedScorecard(
        **dict(card), material=MaterialUse(key=card.material_key, set_by=set_by)
    )
