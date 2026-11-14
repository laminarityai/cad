"""The holes a person states: a metric fastener's holes, or holes of a stated diameter.

A plain hole carries the tolerance the person confirms. It is one of two things, and no other
state can be written: a plus-or-minus length, or the exact key of a class of the tolerances table.
A person who states no tolerance gets `DEFAULT_TOLERANCE`, so the card shows the number a check
reads. The agent copies what the person wrote and never picks a class or a number of its own.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from cad.briefs.kind import Kind
from cad.checks.units import Length, number
from cad.frozen import Frozen
from cad.sandbox.bodies import BodyName
from cad.sandbox.on_body import on_body
from cad.tables.fasteners import (
    MAX_SIZE_CHARS,
    SIZE_PATTERN,
    ClearanceSeries,
    UnknownFastener,
    load_fasteners,
)
from cad.tables.materials import UNITS, magnitude
from cad.tables.tolerances import (
    CLASS_PATTERN,
    MAX_CLASS_CHARS,
    OutsideClass,
    UnknownClass,
    load_tolerances,
)


class HoleFit(StrEnum):
    """What a hole is for: a bolt passes through it, or a thread is cut in it."""

    CLEARANCE = "clearance"
    TAPPED = "tapped"


type RequiredCount = Annotated[int, Field(ge=1, le=256)]


class FastenerHoles(Frozen):
    """Holes for a metric size, such as 2 that fit an M5 bolt or are tapped for M4. `size` is an
    exact key of the fasteners table. With no `count` one such hole is enough, else exactly that.
    A clearance hole takes a `series` when the person states one, such as a close fit; with none,
    any hole from the close to the coarse series fits."""

    kind: Literal[Kind.FASTENER_HOLES] = Kind.FASTENER_HOLES
    size: Annotated[str, Field(pattern=f"^{SIZE_PATTERN.pattern}$", max_length=MAX_SIZE_CHARS)]
    fit: HoleFit
    count: RequiredCount | None = None
    series: ClearanceSeries | None = None
    body: BodyName | None = on_body()

    @field_validator("size")
    @classmethod
    def _in_the_table(cls, size: str) -> str:
        try:
            load_fasteners().get(size)
        except UnknownFastener as error:
            raise ValueError(str(error)) from error
        return size

    @model_validator(mode="after")
    def _series_is_for_clearance(self) -> "FastenerHoles":
        if self.series is not None and self.fit is not HoleFit.CLEARANCE:
            raise ValueError("a series names a clearance hole, and a tapped hole has none")
        return self


class PlusMinus(Frozen):
    """The diameter may be this much over or under the stated one."""

    kind: Literal["plus_minus"] = "plus_minus"
    within: Length


class ByClass(Frozen):
    """The diameter lies in the band of a class of the tolerances table, by its exact key, such as
    H7 or ISO 2768-m."""

    kind: Literal["class"] = "class"
    key: Annotated[str, Field(pattern=f"^{CLASS_PATTERN.pattern}$", max_length=MAX_CLASS_CHARS)]


type HoleTolerance = Annotated[PlusMinus | ByClass, Field(discriminator="kind")]

DEFAULT_TOLERANCE = PlusMinus(within=UNITS.Quantity(0.05, "mm"))
"""What a plain hole is held to when the person states no tolerance: 0.05 mm over or under."""


class PlainHoles(Frozen):
    """Holes of a stated diameter, such as an 8 mm hole for a shaft. `count` works as above. A
    stored requirement with no `tolerance` reads as the default."""

    kind: Literal[Kind.PLAIN_HOLES] = Kind.PLAIN_HOLES
    diameter: Length
    count: RequiredCount | None = None
    tolerance: HoleTolerance = DEFAULT_TOLERANCE
    body: BodyName | None = on_body()

    @model_validator(mode="after")
    def _the_band_exists(self) -> "PlainHoles":
        wanted = magnitude(self.diameter, "mm")
        match self.tolerance:
            case PlusMinus(within=within):
                if magnitude(within, "mm") >= wanted:
                    raise ValueError(
                        f"a tolerance of {number(within):g} {within.units:~P} leaves no hole"
                        f" of {number(self.diameter):g} {self.diameter.units:~P}"
                    )
            case ByClass(key=key):
                try:
                    load_tolerances().limits(key, wanted)
                except (UnknownClass, OutsideClass) as error:
                    raise ValueError(str(error)) from error
        return self
