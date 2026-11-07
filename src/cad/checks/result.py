from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, TypedDict, cast

import pint
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, PlainValidator

from cad.tables.materials import UNITS, Source


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


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


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


class Measure(_Frozen):
    name: str
    value: Measured


class CheckResult(_Frozen):
    check_id: str
    verdict: Verdict
    measured: tuple[Measure, ...]
    formula: str
    reason: str
    sources: tuple[Source, ...]
    version: str

    def value(self, name: str) -> pint.Quantity:
        for measure in self.measured:
            if measure.name == name:
                return measure.value
        raise KeyError(f"{self.check_id} did not measure {name!r}")

    def number(self, name: str, unit: str) -> float:
        # Pint's annotations leave conversions partly untyped, as in cad.tables.materials.
        return float(self.value(name).m_as(unit))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


class StepStored(_Frozen):
    kind: Literal["stored"] = "stored"
    sha256: str


class StepMissing(_Frozen):
    kind: Literal["missing"] = "missing"
    reason: str


type Step = Annotated[StepStored | StepMissing, Field(discriminator="kind")]


class CheckRun(_Frozen):
    """One `run_checks` call. Holds the hashes that make "checks measured what the user gets"
    auditable: `step` is the STEP derived from the BREP whose hash is `brep_sha256`, or why there is
    none, and `image_digest` is the image the check container ran, whatever `image_tag` points to
    later."""

    variant_id: str
    material_key: str
    table_version: str
    image_tag: str
    image_digest: str
    brep_sha256: str
    step: Step
    results: tuple[CheckResult, ...]

    def result(self, check_id: str) -> CheckResult:
        for result in self.results:
            if result.check_id == check_id:
                return result
        raise KeyError(f"no check called {check_id!r} ran")
