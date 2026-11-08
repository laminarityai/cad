from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import pint

type Field = Literal["density"]


class Reason(StrEnum):
    NO_QUANTITY = "no_quantity"
    SEVERAL_QUANTITIES = "several_quantities"
    RANGE = "range"
    MISSING_UNIT = "missing_unit"
    WRONG_DIMENSION = "wrong_dimension"
    OUT_OF_BAND = "out_of_band"


@dataclass(frozen=True, slots=True)
class Refusal:
    reason: Reason
    detail: str
    needed: str


def one_quantity(quote: str, field: Field) -> pint.Quantity | Refusal:
    return Refusal(Reason.NO_QUANTITY, "", "")
