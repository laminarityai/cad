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
)

from cad.checks.result import Comparator, Measured
from cad.projects.model import NEW_PROJECT_ID, NewProjectId, ProjectId, legacy_project
from cad.tables.materials import KEY_PATTERN

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


def _positive(dimension: str) -> Callable[[object, ValidatorFunctionWrapHandler], pint.Quantity]:
    def validate(raw: object, handler: ValidatorFunctionWrapHandler) -> pint.Quantity:
        try:
            quantity: pint.Quantity = handler(raw)
        except pint.PintError as error:
            raise ValueError(f"not a unit: {error}") from error
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
    UNCHECKED = "unchecked"
    MADE_OF = "made_of"


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


class Unchecked(_Frozen):
    """A requirement no reviewed check decides. A scorecard lists it as unverified."""

    kind: Literal[Kind.UNCHECKED] = Kind.UNCHECKED
    statement: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class MadeOf(_Frozen):
    """The brief names the material. A confirmed one pins the `material_key` that scoring accepts.

    The key is an exact key of the materials table: propose_requirements refuses a proposal whose
    key is not in it.
    """

    kind: Literal[Kind.MADE_OF] = Kind.MADE_OF
    material: Annotated[
        str, Field(pattern=f"^{KEY_PATTERN.pattern}$", max_length=MAX_MATERIAL_KEY_CHARS)
    ]


type Target = Annotated[
    ClosedSolid | MaxMass | MinMass | Envelope | Unchecked | MadeOf, Field(discriminator="kind")
]


def deciding_check(kind: Kind) -> CheckId | None:
    """The one table from requirement kind to the check that decides it. None is unverified."""
    match kind:
        case Kind.CLOSED_SOLID:
            return CheckId("closed_solid")
        case Kind.MAX_MASS | Kind.MIN_MASS:
            return CheckId("mass")
        case Kind.ENVELOPE:
            return CheckId("extents")
        case Kind.UNCHECKED | Kind.MADE_OF:
            return None
        case _:
            assert_never(kind)


@dataclass(frozen=True, slots=True)
class Limit:
    measure: str
    comparator: Comparator
    quantity: pint.Quantity


def limits(
    target: ClosedSolid | MaxMass | MinMass | Envelope | Unchecked | MadeOf,
) -> tuple[Limit, ...]:
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
        case Unchecked():
            return target.statement
        case MadeOf():
            return f"Made of {target.material}"
        case _:
            assert_never(target)
