"""`cad.scorecard.score` must never import this module: check versions hash what it imports."""

import hashlib
from typing import Annotated, Final, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from cad.briefs.model import MadeOf, Requirement
from cad.briefs.store import ConfirmedSet
from cad.briefs.words import describe
from cad.errors import Refused
from cad.frozen import Frozen
from cad.research.requests import ResearchRequest
from cad.scorecard.assumed import AssumedRow
from cad.scorecard.model import Scorecard
from cad.tables.materials import PROJECT_PREFIX, MaterialsTable
from cad.variant_sets.model import MaterialChoice

AGENT_CHOSE: Final = (
    "The agent chose this material. No requirement the person confirmed names it, so a result "
    "that depends on it rests on the agent's choice."
)


class MaterialPinned(Refused):
    pass


class SetByRequirement(Frozen):
    """The person confirmed a made_of requirement, and the card used its key."""

    kind: Literal["requirement"] = "requirement"
    requirement_id: str
    statement: str


class SetByAgent(Frozen):
    """The agent chose the material. `reason` is the one line it recorded with its choice, and is
    missing when the agent named a key that no slot of the variant set records."""

    kind: Literal["agent_argument"] = "agent_argument"
    statement: str = AGENT_CHOSE
    reason: str | None = Field(default=None, exclude_if=lambda one: one is None)


type SetBy = Annotated[SetByRequirement | SetByAgent, Field(discriminator="kind")]


class MaterialUse(Frozen):
    key: str
    set_by: SetBy


class ReportedScorecard(Scorecard):
    """A scorecard as the server returns it: the card, what set its material, and a research
    request for each material value a check needed that the table lacks. `research_problem`
    says why the project's researched values cannot be read; while it is set, no request is
    made, because no answer could be stored. `assumptions` lists the values the agent filled in,
    each beside its measure and none with a verdict."""

    material: MaterialUse
    assumptions: tuple[AssumedRow, ...] = Field(default=(), exclude_if=lambda one: not one)
    research: tuple[ResearchRequest, ...] = Field(default=(), exclude_if=lambda one: not one)
    research_problem: str | None = Field(default=None, exclude_if=lambda one: one is None)

    @model_validator(mode="after")
    def _names_the_scored_material(self) -> Self:
        if self.material.key != self.material_key:
            raise ValueError("material.key must be the key the card was scored with")
        return self


class ScorecardSnapshot(ReportedScorecard):
    etag: str


def snapshot(card: ReportedScorecard) -> ScorecardSnapshot:
    etag = hashlib.sha256(card.model_dump_json(by_alias=True).encode()).hexdigest()
    return ScorecardSnapshot(**dict(card), etag=etag)


def pinned_by(confirmed: ConfirmedSet | None) -> Requirement | None:
    if confirmed is None:
        return None
    return next((r for r in confirmed.requirements if isinstance(r.target, MadeOf)), None)


def refuse_other_material(
    confirmed: ConfirmedSet | None, material_key: str, table: MaterialsTable
) -> None:
    pin = pinned_by(confirmed)
    if pin is None or not isinstance(pin.target, MadeOf):
        return
    pinned = table.row_key(pin.target.material)
    if pinned == material_key:
        return
    raise MaterialPinned(
        f"material_key {material_key!r} differs from the material the user confirmed, "
        f"{pinned!r} (requirement {pin.id}). "
        f"Call score_variant again with material_key {pinned!r}. "
        "No variant was scored."
    )


def pinned_key(confirmed: ConfirmedSet | None, table: MaterialsTable) -> str | None:
    pin = pinned_by(confirmed)
    if pin is None or not isinstance(pin.target, MadeOf):
        return None
    return table.row_key(pin.target.material)


def used(key: str, confirmed: ConfirmedSet | None, choice: MaterialChoice | None) -> MaterialUse:
    """What set `key`: the requirement the person confirmed, else the agent, with its reason when
    `choice` records this key."""
    pin = pinned_by(confirmed)
    if pin is not None:
        return MaterialUse(
            key=key,
            set_by=SetByRequirement(requirement_id=pin.id, statement=_statement(pin, key)),
        )
    reason = choice.reason if choice is not None and choice.key == key else None
    return MaterialUse(key=key, set_by=SetByAgent(reason=reason))


def reported(
    card: Scorecard, confirmed: ConfirmedSet | None, choice: MaterialChoice | None = None
) -> ReportedScorecard:
    return ReportedScorecard(**dict(card), material=used(card.material_key, confirmed, choice))


def _statement(pin: Requirement, scored: str) -> str:
    said = describe(pin)
    if not isinstance(pin.target, MadeOf) or pin.target.material != PROJECT_PREFIX + scored:
        return said
    return (
        f"{said}. The materials table had no {scored} when the person confirmed this; it has "
        "one now, so the checks read the table's values, not researched ones."
    )


STORED: Final = TypeAdapter[ReportedScorecard | Scorecard](ReportedScorecard | Scorecard)
"""A stored card. Cards stored before the server reported the material have no `material`."""
