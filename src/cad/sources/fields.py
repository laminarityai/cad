from dataclasses import dataclass
from typing import Final, Literal

type Field = Literal["density"]

MAX_QUOTE_LENGTH: Final = 500


@dataclass(frozen=True, slots=True)
class FieldSpec:
    label: str
    canonical_unit: str
    low: float
    high: float
    units: frozenset[tuple[str, str]]


SPECS: Final[dict[Field, FieldSpec]] = {
    "density": FieldSpec(
        "density",
        "kg/m^3",
        500.0,
        20000.0,
        frozenset(
            {
                ("g", "cm"),
                ("g", "cc"),
                ("g", "ml"),
                ("kg", "m"),
                ("kg", "l"),
                ("kg", "dm"),
                ("Mg", "m"),
                ("t", "m"),
                ("lb", "in"),
                ("lb", "ft"),
            }
        ),
    ),
}
