from dataclasses import dataclass
from enum import StrEnum


class Reason(StrEnum):
    NO_QUANTITY = "no_quantity"
    SEVERAL_QUANTITIES = "several_quantities"
    RANGE = "range"
    BOUND = "bound"
    MISSING_UNIT = "missing_unit"
    UNKNOWN_UNIT = "unknown_unit"
    WRONG_DIMENSION = "wrong_dimension"
    OUT_OF_BAND = "out_of_band"
    WIDE_TOLERANCE = "wide_tolerance"
    NEGATIVE = "negative_value"
    SCIENTIFIC_NOTATION = "scientific_notation"
    AMBIGUOUS_NUMBER = "ambiguous_number"
    TRAILING_DECIMAL = "trailing_decimal"
    TOO_LONG = "too_long"
    UNRECOGNISED_TEXT = "unrecognised_text"


@dataclass(frozen=True, slots=True)
class Refusal:
    reason: Reason
    detail: str
    needed: str
