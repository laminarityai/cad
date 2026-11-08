from dataclasses import dataclass
from typing import Final, Literal

from cad.sources.units import Unit, density_unit

type Field = Literal["density"]

MAX_QUOTE_LENGTH: Final = 500


@dataclass(frozen=True, slots=True)
class FieldSpec:
    label: str
    canonical_unit: str
    low: float
    high: float
    units: dict[tuple[str, str], Unit]


SPECS: Final[dict[Field, FieldSpec]] = {
    "density": FieldSpec(
        "density",
        "kg/m^3",
        500.0,
        20000.0,
        {
            pair: density_unit(*pair)
            for pair in (
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
            )
        },
    ),
}
