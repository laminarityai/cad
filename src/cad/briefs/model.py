"""What a brief, a requirement, a proposal and a decision are.

No type here has a status field. The store derives status from which signed decision records
exist, so there is no stored "confirmed" for anyone to edit.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, Literal, NewType, assert_never

import pint
from pydantic import (
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from cad.briefs.bindable import BINDABLE
from cad.briefs.holes import FastenerHoles, PlainHoles
from cad.briefs.kind import Kind
from cad.briefs.origins import Origin
from cad.checks.container import closed_solid, extents, fea, fit, holes, mass
from cad.checks.result import Comparator
from cad.checks.units import AnyQuantity, Length, Mass, number
from cad.context_parts.ids import PART_ID_PATTERN, ContextPartId
from cad.frozen import Frozen
from cad.loads.model import LoadCase
from cad.projects.model import NEW_PROJECT_ID, NewProjectId, ProjectId, legacy_project
from cad.tables.materials import KEY_PATTERN, UNITS, magnitude

BriefId = NewType("BriefId", str)
RequirementId = NewType("RequirementId", str)
CheckId = NewType("CheckId", str)
MAX_BRIEF_CHARS: Final = 64 * 1024
type PartName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40, pattern=r"^[^\n\r]+$"),
]
SAID_SEPARATOR: Final = "\n\n"
MAX_REQUIREMENTS: Final = 64
MAX_STATEMENT_CHARS: Final = 500
MAX_NOTE_CHARS: Final = 2000
MAX_MATERIAL_KEY_CHARS: Final = 64


class ClosedSolid(Frozen):
    kind: Literal[Kind.CLOSED_SOLID] = Kind.CLOSED_SOLID


class MaxMass(Frozen):
    kind: Literal[Kind.MAX_MASS] = Kind.MAX_MASS
    mass: Mass


class MinMass(Frozen):
    kind: Literal[Kind.MIN_MASS] = Kind.MIN_MASS
    mass: Mass


class Envelope(Frozen):
    """The variant fits inside a box of these three edge lengths, in any orientation.

    Stored longest first, so one box given in any order is one target with one id.
    """

    kind: Literal[Kind.ENVELOPE] = Kind.ENVELOPE
    edges: tuple[Length, Length, Length]

    @field_validator("edges")
    @classmethod
    def _longest_first(
        cls, edges: tuple[pint.Quantity, pint.Quantity, pint.Quantity]
    ) -> tuple[pint.Quantity, pint.Quantity, pint.Quantity]:
        longest, middle, shortest = sorted(
            edges, key=lambda edge: magnitude(edge, "mm"), reverse=True
        )
        return longest, middle, shortest


class MeasureLimit(Frozen):
    """One team measure held to a limit the person confirms, such as the volume at most 30 cm^3.

    Only a measure in BINDABLE can be named, and the limit must be in that measure's dimension.
    """

    kind: Literal[Kind.MEASURE_LIMIT] = Kind.MEASURE_LIMIT
    check_id: CheckId
    measure: str
    comparator: Comparator
    limit: AnyQuantity

    @model_validator(mode="after")
    def _bindable(self) -> "MeasureLimit":
        bound = BINDABLE.get((self.check_id, self.measure))
        if bound is None:
            offered = ", ".join(f"{check}:{name}" for check, name in BINDABLE)
            raise ValueError(
                f"no limit can bind to {self.check_id}:{self.measure}; the measures are {offered}"
            )
        dimension = UNITS.Quantity(1, bound.unit).dimensionality
        if not self.limit.check(dimension):  # pyright: ignore[reportUnknownMemberType]
            raise ValueError(
                f"the limit must be in {bound.unit} or a unit of its kind, not {self.limit.units}"
            )
        value = number(self.limit)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("the limit must be a finite number above zero")
        return self


class Unchecked(Frozen):
    """A requirement no reviewed check decides. A scorecard lists it as unverified."""

    kind: Literal[Kind.UNCHECKED] = Kind.UNCHECKED
    statement: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class MadeOf(Frozen):
    """The brief names the material. A confirmed one pins the `material_key` that scoring accepts.

    The key is an exact key of the materials table, or, for a material the table lacks, a key of
    your own that names it. The server stores that material as the project's own row, `project-`
    and your key, and its values are researched.
    """

    kind: Literal[Kind.MADE_OF] = Kind.MADE_OF
    material: Annotated[
        str, Field(pattern=f"^{KEY_PATTERN.pattern}$", max_length=MAX_MATERIAL_KEY_CHARS)
    ]


class MinSafetyFactor(Frozen):
    """The yield strength over the largest von Mises stress under the load case."""

    kind: Literal[Kind.MIN_SAFETY_FACTOR] = Kind.MIN_SAFETY_FACTOR
    load: LoadCase
    factor: Annotated[float, Field(ge=1, allow_inf_nan=False)]


class MaxDeflection(Frozen):
    """The largest displacement of any point under the load case."""

    kind: Literal[Kind.MAX_DEFLECTION] = Kind.MAX_DEFLECTION
    load: LoadCase
    deflection: Length


type PartId = Annotated[ContextPartId, Field(pattern=PART_ID_PATTERN)]


class MinClearance(Frozen):
    """The variant, built in the context part's frame, stays at least this far from it."""

    kind: Literal[Kind.MIN_CLEARANCE] = Kind.MIN_CLEARANCE
    part: PartId
    clearance: Length


class MaxClearance(Frozen):
    """The variant comes no further than this from the context part, so it cannot pass by
    sitting far away."""

    kind: Literal[Kind.MAX_CLEARANCE] = Kind.MAX_CLEARANCE
    part: PartId
    clearance: Length


class FitsWith(Frozen):
    """The variant, built in the context part's frame, does not overlap it."""

    kind: Literal[Kind.FITS_WITH] = Kind.FITS_WITH
    part: PartId


ON_PART: Final = (MinClearance, MaxClearance, FitsWith)
"""The targets that name a context part, which the fit check decides against that part."""


type Target = Annotated[
    ClosedSolid
    | MaxMass
    | MinMass
    | Envelope
    | MeasureLimit
    | Unchecked
    | MadeOf
    | MinSafetyFactor
    | MaxDeflection
    | MinClearance
    | MaxClearance
    | FastenerHoles
    | PlainHoles
    | FitsWith,
    Field(discriminator="kind"),
]


def deciding_check(target: Target) -> CheckId | None:
    """The one table from a requirement to the check that decides it. None is unverified."""
    match target:
        case ClosedSolid():
            return CheckId(closed_solid.ID)
        case MaxMass() | MinMass():
            return CheckId(mass.ID)
        case Envelope():
            return CheckId(extents.ID)
        case MeasureLimit():
            return target.check_id
        case Unchecked() | MadeOf():
            return None
        case MinSafetyFactor() | MaxDeflection():
            return CheckId(fea.ID)
        case MinClearance() | MaxClearance() | FitsWith():
            return CheckId(fit.ID)
        case FastenerHoles() | PlainHoles():
            return CheckId(holes.ID)
        case _:
            assert_never(target)


def load_of(target: Target) -> LoadCase | None:
    match target:
        case MinSafetyFactor() | MaxDeflection():
            return target.load
        case (
            ClosedSolid()
            | MaxMass()
            | MinMass()
            | Envelope()
            | MeasureLimit()
            | Unchecked()
            | MadeOf()
            | MinClearance()
            | MaxClearance()
            | FastenerHoles()
            | PlainHoles()
            | FitsWith()
        ):
            return None
        case _:
            assert_never(target)


@dataclass(frozen=True, slots=True)
class Limit:
    measure: str
    comparator: Comparator
    quantity: pint.Quantity


def limits(target: Target) -> tuple[Limit, ...]:
    match target:
        case ClosedSolid() | Unchecked() | MadeOf() | FastenerHoles() | PlainHoles() | FitsWith():
            return ()
        case MaxMass():
            return (Limit("mass", Comparator.AT_MOST, target.mass),)
        case MinMass():
            return (Limit("mass", Comparator.AT_LEAST, target.mass),)
        case Envelope():
            return tuple(
                Limit(f"sorted_extent:{name}", Comparator.AT_MOST, edge)
                for name, edge in zip(("largest", "middle", "smallest"), target.edges, strict=True)
            )
        case MinSafetyFactor():
            factor = UNITS.Quantity(target.factor, "dimensionless")
            return (Limit("safety_factor", Comparator.AT_LEAST, factor),)
        case MaxDeflection():
            return (Limit("max_displacement", Comparator.AT_MOST, target.deflection),)
        case MeasureLimit():
            return (Limit(target.measure, target.comparator, target.limit),)
        case MinClearance():
            return (Limit("min_clearance", Comparator.AT_LEAST, target.clearance),)
        case MaxClearance():
            return (Limit("min_clearance", Comparator.AT_MOST, target.clearance),)
        case _:
            assert_never(target)


class Brief(Frozen):
    id: BriefId
    text: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)]
    created_at: datetime
    project_id: Annotated[NewProjectId, Field(pattern=NEW_PROJECT_ID.pattern)] | None = None
    transcript_seq: int | None = None
    name: PartName | None = None

    @property
    def project(self) -> ProjectId:
        """A brief stored before projects has no project_id and is alone in pb-<brief_id>."""
        return legacy_project(self.id) if self.project_id is None else self.project_id


class Said(Frozen):
    brief_id: BriefId
    number: Annotated[int, Field(ge=1)]
    text: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)]
    transcript_seq: int | None
    said_at: datetime


class Requirement(Frozen):
    id: RequirementId
    brief_id: BriefId
    target: Target
    origin: Origin


def requirement_id(brief_id: BriefId, target: Target, origin: Origin) -> RequirementId:
    """The id of a requirement: the same brief, target and origin always give the same id."""
    identity = json.dumps(
        [brief_id, target.model_dump(mode="json"), origin.model_dump(mode="json")],
        sort_keys=True,
    )
    return RequirementId(hashlib.sha256(identity.encode()).hexdigest()[:16])


class Proposal(Frozen):
    """One whole numbered set of requirements for a brief. Never edited once stored."""

    brief_id: BriefId
    number: Annotated[int, Field(ge=1)]
    requirements: tuple[Requirement, ...]
    created_at: datetime


class Confirmed(Frozen):
    verdict: Literal["confirmed"] = "confirmed"


class Declined(Frozen):
    verdict: Literal["declined"] = "declined"
    note: Annotated[str, Field(max_length=MAX_NOTE_CHARS)]


type Answer = Annotated[Confirmed | Declined, Field(discriminator="verdict")]


class Decision(Frozen):
    """What a person answered on the page for one proposal, bound to the bytes they were shown."""

    proposal: Annotated[int, Field(ge=1)]
    brief_sha256: str
    proposal_sha256: str
    answer: Answer
    decided_at: datetime


def amount(quantity: pint.Quantity) -> str:
    return f"{number(quantity):g} {quantity.units:~P}".rstrip()
