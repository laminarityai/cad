"""`cad.scorecard.score` must never import this module: check versions hash what it imports."""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from cad.briefs.model import MadeOf, Requirement, body_of
from cad.briefs.store import ConfirmedSet
from cad.briefs.words import describe
from cad.checks.result import BodyMaterial, Materials
from cad.errors import Refused
from cad.frozen import Frozen
from cad.research.requests import ResearchRequest
from cad.sandbox.bodies import Bodies, BodyName
from cad.scorecard.assumed import AssumedRow
from cad.scorecard.awaiting import AwaitingRow
from cad.scorecard.model import Scorecard
from cad.scorecard.unjudged import Reported
from cad.tables.materials import PROJECT_PREFIX, MaterialsTable
from cad.variant_sets.model import (
    BodyChoice,
    BodyMaterialsRefused,
    MaterialChoice,
    MaterialMissing,
    Revision,
)

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


class BodyMaterialUse(MaterialUse):
    """What one named body is made of, the name a person reads for it, and what set it."""

    body: BodyName
    name: str


class ReportedScorecard(Scorecard):
    """A scorecard as the server returns it: the card, what set its material, and a research
    request for each material value a check needed that the table lacks. `research_problem`
    says why the project's researched values cannot be read; while it is set, no request is
    made, because no answer could be stored. `assumptions` lists the values the agent filled in,
    each beside its measure and none with a verdict. `awaiting` lists each stated target that waits
    for the person's Confirm, beside its measure and with no verdict. A result under a load that
    only those read, and no confirmed target, is in `results` as a `MeasureOnly`, with no
    verdict."""

    # The card is frozen, so widening its results cannot put a MeasureOnly into a stored card.
    results: tuple[Reported, ...]  # pyright: ignore[reportIncompatibleVariableOverride]
    material: MaterialUse | None = Field(default=None, exclude_if=lambda one: one is None)
    body_materials: tuple[BodyMaterialUse, ...] = Field(
        default=(), exclude_if=lambda each: not each
    )
    assumptions: tuple[AssumedRow, ...] = Field(default=(), exclude_if=lambda one: not one)
    awaiting: tuple[AwaitingRow, ...] = Field(default=(), exclude_if=lambda one: not one)
    research: tuple[ResearchRequest, ...] = Field(default=(), exclude_if=lambda one: not one)
    research_problem: str | None = Field(default=None, exclude_if=lambda one: one is None)

    @model_validator(mode="after")
    def _names_the_scored_material(self) -> Self:
        if (None if self.material is None else self.material.key) != self.material_key:
            raise ValueError("material.key must be the key the card was scored with")
        used = [(one.body, one.key) for one in self.body_materials]
        if used != [(one.body, one.key) for one in self.materials]:
            raise ValueError("body_materials must name each body's key the card was scored with")
        return self


class ScorecardSnapshot(ReportedScorecard):
    etag: str


def snapshot(card: ReportedScorecard) -> ScorecardSnapshot:
    etag = hashlib.sha256(card.model_dump_json(by_alias=True).encode()).hexdigest()
    return ScorecardSnapshot(**dict(card), etag=etag)


type Pins = Mapping[str | None, str]
"""The key each confirmed made_of fixes, by the body it names, None for one that names no body and
so pins every body."""


def pinned_by(confirmed: ConfirmedSet | None, body: str | None = None) -> Requirement | None:
    """The made_of that fixes the body's material: the one naming it, else one naming no body."""
    made: Sequence[Requirement] = () if confirmed is None else confirmed.requirements
    pins = [r for r in made if isinstance(r.target, MadeOf)]
    named = next((r for r in pins if body is not None and body_of(r.target) == body), None)
    return named or next((r for r in pins if body_of(r.target) is None), None)


def pins(confirmed: ConfirmedSet | None, table: MaterialsTable) -> Pins:
    made = () if confirmed is None else confirmed.requirements
    return {
        r.target.body: table.row_key(r.target.material)
        for r in made
        if isinstance(r.target, MadeOf)
    }


def pin_for(pinned: Pins, body: str | None) -> str | None:
    named = None if body is None else pinned.get(body)
    return named or pinned.get(None)


def refuse_other_material(
    pinned: Pins, body: str | None, material_key: str, table: MaterialsTable
) -> None:
    pin = pin_for(pinned, body)
    if pin is None or table.row_key(material_key) == pin:
        return
    raise MaterialPinned(
        f"material_key {material_key!r} differs from the material the user confirmed, "
        f"{pin!r}, {_which(pinned, body)}. Call score_variant again with that material, or with "
        "no material_key and no materials. No variant was scored."
    )


def _which(pinned: Pins, body: str | None) -> str:
    if body is not None and body in pinned:
        return f"which the {body} is made of"
    return "which every body is made of"


type MaterialsOf = Callable[[Bodies], Materials]


def made_of(
    bodies: Bodies,
    single: str | None,
    asked: Mapping[str, str],
    pinned: Pins,
    revision: Revision | None,
) -> Materials:
    """One key for a variant of one unnamed body. For a variant of named bodies, each body's key:
    the person's made_of that names it or names no body, else its entry in `asked`, else the
    choice the slot recorded for a body of that name."""
    if not bodies:
        if asked:
            raise BodyMaterialsRefused(
                "this variant is one unnamed body: score it with material_key, not materials"
            )
        chose = None if revision is None or revision.material is None else revision.material.key
        key = single or pinned.get(None) or chose
        if key is None:
            raise MaterialMissing(NO_MATERIAL)
        return key
    names = [body.name for body in bodies]
    built = f"the variant holds the bodies {', '.join(names)}"
    if single is not None and len(names) > 1:
        raise BodyMaterialsRefused(
            f"{built}, and material_key names the material of a variant of one body: pass "
            "materials, one entry for each body, or none to use the materials its slot records"
        )
    stray = [name for name in asked if name not in names]
    if stray:
        raise BodyMaterialsRefused(f"materials names {', '.join(stray)}, but {built}")
    given = dict(asked) if single is None else {names[0]: single}
    kept = {} if revision is None else {one.body: one.key for one in revision.materials}
    if len(names) == 1 and revision is not None and revision.material is not None:
        kept = {names[0]: revision.material.key}
    keys = {name: pin_for(pinned, name) or given.get(name) or kept.get(name) for name in names}
    missing = [name for name, key in keys.items() if key is None]
    if missing:
        raise MaterialMissing(
            f"no material is known for the bodies {', '.join(missing)}: pass materials with an "
            "entry for each, or pass the brief_id of a brief whose confirmed made_of names the "
            "material, or whose variant set records the material the agent chose for each body"
        )
    return tuple(BodyMaterial(body=name, key=str(keys[name])) for name in names)


NO_MATERIAL: Final = (
    "no material is known for this variant: pass material_key, or pass the brief_id of a brief "
    "whose confirmed made_of names it, or whose variant set records the material the agent chose "
    "for this variant's slot"
)


def used(
    key: str,
    confirmed: ConfirmedSet | None,
    choice: MaterialChoice | BodyChoice | None,
    body: str | None = None,
) -> MaterialUse:
    """What set `key` for the body: the requirement the person confirmed, else the agent, with its
    reason when `choice` records this key."""
    pin = pinned_by(confirmed, body)
    if pin is not None:
        return MaterialUse(
            key=key,
            set_by=SetByRequirement(requirement_id=pin.id, statement=_statement(pin, key)),
        )
    reason = choice.reason if choice is not None and choice.key == key else None
    return MaterialUse(key=key, set_by=SetByAgent(reason=reason))


def reported(
    card: Scorecard,
    confirmed: ConfirmedSet | None,
    table: MaterialsTable,
    revision: Revision | None = None,
) -> ReportedScorecard:
    """The card with what set each material: the person's made_of, else the agent, with the
    reason its slot recorded."""
    choice = None if revision is None else revision.material
    kept = {} if revision is None else {one.body: one for one in revision.materials}
    each = tuple(
        BodyMaterialUse(
            body=one.body,
            name=table.name_of(one.key),
            **dict(used(one.key, confirmed, kept.get(one.body), one.body)),
        )
        for one in card.materials
    )
    single = None if card.material_key is None else used(card.material_key, confirmed, choice)
    return ReportedScorecard(**dict(card), material=single, body_materials=each)


def _statement(pin: Requirement, scored: str) -> str:
    said = describe(pin)
    if not isinstance(pin.target, MadeOf) or pin.target.material != PROJECT_PREFIX + scored:
        return said
    return (
        f"{said}. The materials table had no {scored} when the person confirmed this; it has "
        "one now, so the checks read the table's values, not researched ones."
    )
