from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, TypedDict, cast

import pint
from pydantic import Field, NonNegativeInt, PlainSerializer, PlainValidator

from cad.frozen import Frozen
from cad.tables.materials import UNITS, Source


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class Comparator(StrEnum):
    AT_MOST = "at_most"
    AT_LEAST = "at_least"


class QuantityJson(TypedDict):
    magnitude: float
    unit: str


def _to_quantity(raw: object) -> pint.Quantity:
    if isinstance(raw, pint.Quantity):
        return cast(pint.Quantity, raw)
    if isinstance(raw, dict):
        fields = cast(Mapping[str, object], raw)
        if set(fields) == {"magnitude", "unit"}:
            return UNITS.Quantity(float(cast(float, fields["magnitude"])), str(fields["unit"]))
    raise ValueError("a measured value is a quantity or {'magnitude', 'unit'}")


def _to_json(quantity: pint.Quantity) -> QuantityJson:
    unit = f"{quantity.units:~P}" or "dimensionless"
    # Pint's annotations leave conversions partly untyped, as in cad.tables.materials.
    magnitude = float(quantity.m_as(quantity.units))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return {"magnitude": magnitude, "unit": unit}


type Measured = Annotated[
    pint.Quantity, PlainValidator(_to_quantity), PlainSerializer(_to_json, return_type=QuantityJson)
]


class Measure(Frozen):
    name: str
    value: Measured


class ReadCited(Frozen):
    """The check read a value that a reviewed row in git cites; `sources` names the row's source."""

    kind: Literal["cited"] = "cited"
    field: str


class ReadResearched(Frozen):
    """The check read a value the server fetched and read from `quote` on the page at `url`
    (ADR-0009). `sha256` hashes the page as fetched. A result that rests on it is researched."""

    kind: Literal["researched"] = "researched"
    field: str
    url: str
    quote: str
    sha256: str


class ReadMissing(Frozen):
    """The table has no value for the field, so the check read none."""

    kind: Literal["missing"] = "missing"
    field: str
    reason: str


type Read = Annotated[ReadCited | ReadResearched | ReadMissing, Field(discriminator="kind")]


class Faces(Frozen):
    """Faces of the variant that the `fea` check fixed (`support`) and pressed on (`load`), as
    indices in the kernel's explorer order of the BREP the check read. The 3D view numbers the
    faces of the same BREP the same way. The check finds them and the agent never names one
    (ADR-0007)."""

    support: tuple[NonNegativeInt, ...]
    load: tuple[NonNegativeInt, ...]


class Where(Faces):
    """`support` and `load` are the faces of the candidates that decided the stress. `displacement`
    holds the faces of the candidates that decided the displacement, when they are others. A
    candidate within the check's stated error of the worst is shown with it, since the check cannot
    tell them apart."""

    displacement: Faces | None = Field(default=None, exclude_if=lambda faces: faces is None)


class CheckResult(Frozen):
    check_id: str
    verdict: Verdict
    measured: tuple[Measure, ...]
    formula: str
    reason: str
    sources: tuple[Source, ...]
    version: str
    instance: str = Field(default="", exclude_if=lambda instance: not instance)
    reads: tuple[Read, ...] = Field(default=(), exclude_if=lambda reads: not reads)
    where: Where | None = Field(default=None, exclude_if=lambda where: where is None)

    def value(self, name: str) -> pint.Quantity:
        for measure in self.measured:
            if measure.name == name:
                return measure.value
        raise KeyError(f"{self.check_id} did not measure {name!r}")

    def number(self, name: str, unit: str) -> float:
        # Pint's annotations leave conversions partly untyped, as in cad.tables.materials.
        return float(self.value(name).m_as(unit))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


class StepStored(Frozen):
    kind: Literal["stored"] = "stored"
    sha256: str


class StepMissing(Frozen):
    kind: Literal["missing"] = "missing"
    reason: str


type Step = Annotated[StepStored | StepMissing, Field(discriminator="kind")]


class CheckRun(Frozen):
    """One `run_checks` call. Holds the hashes that make "checks measured what the user gets"
    auditable: `step` is the STEP derived from the BREP whose hash is `brep_sha256`, or why there is
    none, and `check_image_digest` is the analysis image the check container ran, whatever
    `check_image_tag` points to later."""

    variant_id: str
    material_key: str
    table_version: str
    check_image_tag: str
    check_image_digest: str
    brep_sha256: str
    step: Step
    results: tuple[CheckResult, ...]
    timed_out: bool

    def result(self, check_id: str) -> CheckResult:
        for result in self.results:
            if result.check_id == check_id:
                return result
        raise KeyError(f"no check called {check_id!r} ran")
