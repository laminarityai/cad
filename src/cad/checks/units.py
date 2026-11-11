"""The quantity types a brief and a load state their numbers in. Each parses a unit with pint and
refuses an unknown one; all but `Quantity` also require a finite magnitude above zero in one
dimension."""

import math
from collections.abc import Callable
from typing import Annotated, Any, Final

import pint
from pydantic import ValidatorFunctionWrapHandler, WithJsonSchema, WrapValidator

from cad.checks.result import Measured

_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {"magnitude": {"type": "number"}, "unit": {"type": "string"}},
    "required": ["magnitude", "unit"],
    "additionalProperties": False,
}


def number(quantity: pint.Quantity) -> float:
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
        magnitude = number(quantity)
        if not math.isfinite(magnitude) or magnitude <= 0:
            raise ValueError("the magnitude must be a finite number above zero")
        return quantity

    return validate


# Not a `type` statement: that would give the schema a $defs entry where it is inline today.
AnyQuantity = Annotated[Measured, WrapValidator(_parsed), WithJsonSchema(_SCHEMA)]
type Mass = Annotated[Measured, WrapValidator(_positive("[mass]")), WithJsonSchema(_SCHEMA)]
type Length = Annotated[Measured, WrapValidator(_positive("[length]")), WithJsonSchema(_SCHEMA)]
type Force = Annotated[Measured, WrapValidator(_positive("[force]")), WithJsonSchema(_SCHEMA)]
