"""The quantity types a brief and a load state their numbers in. Each parses a unit with pint and
refuses an unknown one; all but `Quantity` also require a finite magnitude above zero in one
dimension."""

import math
import re
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Final, cast

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


_MAX_UNIT_CHARS: Final = 64
_NAME: Final = r"(?:[^\W\d_]|[°%])+\d{0,2}"
_POWER: Final = r"(?:(?:\^|\*\*)(?:-?\d{1,2}|\(-?\d{1,2}\))|⁻?[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,2})"
_FACTOR: Final = rf"{_NAME}{_POWER}?"
_BETWEEN: Final = r"(?:\s*[*/·⋅]\s*|\s+)"
# Pint evaluates a unit string as arithmetic, so `10**10**10` runs for minutes.
_PLAIN_UNIT: Final = re.compile(rf"\s*(?:1|(?:1\s*/\s*)?{_FACTOR}(?:{_BETWEEN}{_FACTOR})*)?\s*")


def _plain_unit(raw: object) -> None:
    if not isinstance(raw, Mapping):
        return
    unit = cast(Mapping[str, object], raw).get("unit")
    if not isinstance(unit, str):
        return
    if len(unit) > _MAX_UNIT_CHARS or not _PLAIN_UNIT.fullmatch(unit):
        raise ValueError(
            "not a unit: write unit names joined by * or / with small powers, such as mm, "
            f"cm^3 or g/cm^3, in at most {_MAX_UNIT_CHARS} characters"
        )


def _parsed(raw: object, handler: ValidatorFunctionWrapHandler) -> pint.Quantity:
    _plain_unit(raw)
    try:
        return handler(raw)
    except pint.PintError as error:
        raise ValueError(f"not a unit: {error}") from error
    except OverflowError as error:
        raise ValueError("the magnitude is too large to be a number") from error


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
