"""What a brief, a requirement, a proposal and a decision are.

No type here has a status field. The store derives status from which signed decision records
exist, so there is no stored "confirmed" for anyone to edit.
"""

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Final, Literal, NewType, assert_never

import pint
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidatorFunctionWrapHandler,
    WithJsonSchema,
    WrapValidator,
    field_validator,
    model_validator,
)

from cad.briefs.bindable import BINDABLE
from cad.checks.result import Comparator, Measured
from cad.loads.model import LoadCase
from cad.loads.words import describe_case
from cad.projects.model import NEW_PROJECT_ID, NewProjectId, ProjectId, legacy_project
from cad.tables.materials import KEY_PATTERN, PROJECT_PREFIX, UNITS

BriefId = NewType("BriefId", str)
RequirementId = NewType("RequirementId", str)
CheckId = NewType("CheckId", str)
MAX_BRIEF_CHARS: Final = 64 * 1024
MAX_REQUIREMENTS: Final = 64
MAX_STATEMENT_CHARS: Final = 500
MAX_NOTE_CHARS: Final = 2000
MAX_MATERIAL_KEY_CHARS: Final = 64
QUANTITY_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {"magnitude": {"type": "number"}, "unit": {"type": "string"}},
    "required": ["magnitude", "unit"],
    "additionalProperties": False,
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


def _magnitude(quantity: pint.Quantity) -> float:
    # Pint's annotations leave quantities partly untyped, as in cad.tables.materials.
    return float(quantity.magnitude)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _parsed(raw: object, handler: ValidatorFunctionWrapHandler) -> pint.Quantity:
    try:
        return handler(raw)
    except pint.PintError as error:
        raise ValueError(f"not a unit: {error}") from error


def _positive(dimension: str) -> Callable[[object, ValidatorFunctionWrapHandler], pint.Quantity]:
    def validate(raw: object, handler: ValidatorFunctionWrapHandler) -> pint.Quantity:
        quantity = _parsed(raw, handler)
        if not quantity.check(dimension):  # pyright: ignore[reportUnknownMemberType]
            raise ValueError(f"expected a {dimension} quantity, got {quantity.units}")
        magnitude = _magnitude(quantity)
        if not math.isfinite(magnitude) or magnitude <= 0:
            raise ValueError("the magnitude must be a finite number above zero")
        return quantity

    return validate


type Mass = Annotated[Measured, WrapValidator(_positive("[mass]")), WithJsonSchema(QUANTITY_SCHEMA)]
type Length = Annotated[
    Measured, WrapValidator(_positive("[length]")), WithJsonSchema(QUANTITY_SCHEMA)
]


class Kind(StrEnum):
    CLOSED_SOLID = "closed_solid"
    MAX_MASS = "max_mass"
    MIN_MASS = "min_mass"
    ENVELOPE = "envelope"
    MEASURE_LIMIT = "measure_limit"
    UNCHECKED = "unchecked"
    MADE_OF = "made_of"
    MIN_SAFETY_FACTOR = "min_safety_factor"
    MAX_DEFLECTION = "max_deflection"


class ClosedSolid(_Frozen):
    kind: Literal[Kind.CLOSED_SOLID] = Kind.CLOSED_SOLID


class MaxMass(_Frozen):
    kind: Literal[Kind.MAX_MASS] = Kind.MAX_MASS
    mass: Mass


class MinMass(_Frozen):
    kind: Literal[Kind.MIN_MASS] = Kind.MIN_MASS
    mass: Mass


def _millimetres(length: pint.Quantity) -> float:
    # Pint's annotations leave conversions partly untyped, as in cad.tables.materials.
    return float(length.m_as("mm"))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


class Envelope(_Frozen):
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
        longest, middle, shortest = sorted(edges, key=_millimetres, reverse=True)
        return longest, middle, shortest


class MeasureLimit(_Frozen):
    """One team measure held to a limit the person confirms, such as the volume at most 30 cm^3.

    Only a measure in BINDABLE can be named, and the limit must be in that measure's dimension.
    """

    kind: Literal[Kind.MEASURE_LIMIT] = Kind.MEASURE_LIMIT
    check_id: CheckId
    measure: str
    comparator: Comparator
    limit: Annotated[Measured, WrapValidator(_parsed), WithJsonSchema(QUANTITY_SCHEMA)]

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
        magnitude = _magnitude(self.limit)
        if not math.isfinite(magnitude) or magnitude <= 0:
            raise ValueError("the limit must be a finite number above zero")
        return self


class Unchecked(_Frozen):
    """A requirement no reviewed check decides. A scorecard lists it as unverified."""

    kind: Literal[Kind.UNCHECKED] = Kind.UNCHECKED
    statement: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class MadeOf(_Frozen):
    """The brief names the material. A confirmed one pins the `material_key` that scoring accepts.

    The key is an exact key of the materials table, or, for a material the table lacks, a key of
    your own that names it. The server stores that material as the project's own row, `project-`
    and your key, and its values are researched.
    """

    kind: Literal[Kind.MADE_OF] = Kind.MADE_OF
    material: Annotated[
        str, Field(pattern=f"^{KEY_PATTERN.pattern}$", max_length=MAX_MATERIAL_KEY_CHARS)
    ]


class MinSafetyFactor(_Frozen):
    """The yield strength over the largest von Mises stress under the load case."""

    kind: Literal[Kind.MIN_SAFETY_FACTOR] = Kind.MIN_SAFETY_FACTOR
    load: LoadCase
    factor: Annotated[float, Field(ge=1, allow_inf_nan=False)]


class MaxDeflection(_Frozen):
    """The largest displacement of any point under the load case."""

    kind: Literal[Kind.MAX_DEFLECTION] = Kind.MAX_DEFLECTION
    load: LoadCase
    deflection: Length


type Loaded = MinSafetyFactor | MaxDeflection
type Target = Annotated[
    ClosedSolid
    | MaxMass
    | MinMass
    | Envelope
    | MeasureLimit
    | Unchecked
    | MadeOf
    | MinSafetyFactor
    | MaxDeflection,
    Field(discriminator="kind"),
]


def deciding_check(target: Target) -> CheckId | None:
    """The one table from a requirement to the check that decides it. None is unverified."""
    match target:
        case ClosedSolid():
            return CheckId("closed_solid")
        case MaxMass() | MinMass():
            return CheckId("mass")
        case Envelope():
            return CheckId("extents")
        case MeasureLimit():
            return target.check_id
        case Unchecked() | MadeOf():
            return None
        case MinSafetyFactor() | MaxDeflection():
            return CheckId("fea")
        case _:
            assert_never(target)


@dataclass(frozen=True, slots=True)
class Limit:
    measure: str
    comparator: Comparator
    quantity: pint.Quantity


def limits(target: Target) -> tuple[Limit, ...]:
    match target:
        case ClosedSolid() | Unchecked() | MadeOf():
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
        case _:
            assert_never(target)


class BriefSpan(_Frozen):
    """Characters [start, end) of the brief text, resolved by the store from a verbatim quote."""

    kind: Literal["brief_text"] = "brief_text"
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]


class Brief(_Frozen):
    id: BriefId
    text: Annotated[str, Field(min_length=1, max_length=MAX_BRIEF_CHARS)]
    created_at: datetime
    project_id: Annotated[NewProjectId, Field(pattern=NEW_PROJECT_ID.pattern)] | None = None

    @property
    def project(self) -> ProjectId:
        """A brief stored before projects has no project_id and is alone in pb-<brief_id>."""
        return legacy_project(self.id) if self.project_id is None else self.project_id


class Requirement(_Frozen):
    id: RequirementId
    brief_id: BriefId
    target: Target
    origin: BriefSpan


def requirement_id(brief_id: BriefId, target: Target, origin: BriefSpan) -> RequirementId:
    """The id of a requirement: the same brief, target and span always give the same id."""
    identity = json.dumps(
        [brief_id, target.model_dump(mode="json"), origin.model_dump(mode="json")],
        sort_keys=True,
    )
    return RequirementId(hashlib.sha256(identity.encode()).hexdigest()[:16])


class Proposal(_Frozen):
    """One whole numbered set of requirements for a brief. Never edited once stored."""

    brief_id: BriefId
    number: Annotated[int, Field(ge=1)]
    requirements: tuple[Requirement, ...]
    created_at: datetime


class Confirmed(_Frozen):
    verdict: Literal["confirmed"] = "confirmed"


class Declined(_Frozen):
    verdict: Literal["declined"] = "declined"
    note: Annotated[str, Field(max_length=MAX_NOTE_CHARS)]


type Answer = Annotated[Confirmed | Declined, Field(discriminator="verdict")]


class Decision(_Frozen):
    """What a person answered on the page for one proposal, bound to the bytes they were shown."""

    proposal: Annotated[int, Field(ge=1)]
    brief_sha256: str
    proposal_sha256: str
    answer: Answer
    decided_at: datetime


def amount(quantity: pint.Quantity) -> str:
    return f"{_magnitude(quantity):g} {quantity.units:~P}"


def measure_limit_words(target: MeasureLimit) -> str:
    words = BINDABLE[(target.check_id, target.measure)].words
    bound = "at most" if target.comparator is Comparator.AT_MOST else "at least"
    return f"{words[0].upper()}{words[1:]} is {bound} {amount(target.limit)}"


def describe(requirement: Requirement) -> str:
    """The plain words the page shows a person and the tools show the agent."""
    target = requirement.target
    match target:
        case ClosedSolid():
            return "The part is one closed solid"
        case MaxMass():
            return f"Mass at most {amount(target.mass)}"
        case MinMass():
            return f"Mass at least {amount(target.mass)}"
        case Envelope():
            return "Fits inside a box of " + " x ".join(amount(edge) for edge in target.edges)
        case MeasureLimit():
            return measure_limit_words(target)
        case Unchecked():
            return target.statement
        case MadeOf():
            return f"Made of {target.material.removeprefix(PROJECT_PREFIX)}"
        case MinSafetyFactor():
            return f"Safety factor against yield at least {target.factor:g} with " + describe_case(
                target.load
            )
        case MaxDeflection():
            return f"Deflects at most {amount(target.deflection)} with {describe_case(target.load)}"
        case _:
            assert_never(target)
