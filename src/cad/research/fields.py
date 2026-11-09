"""Nothing here parses a unit expression: a spelling that is not a key is refused."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

type Field = Literal[
    "density", "elastic_modulus", "poisson_ratio", "yield_strength", "tensile_strength"
]

MAX_QUOTE_LENGTH: Final = 500


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """`units` maps each accepted spelling to its factor into `canonical_unit`."""

    label: str
    canonical_unit: str
    low: float
    high: float
    units: Mapping[str, Decimal]
    unit_hint: str
    exclusive: bool = False

    def admits(self, value: Decimal) -> bool:
        if self.exclusive:
            return self.low < value < self.high
        return self.low <= value <= self.high

    @property
    def accepts(self) -> str:
        unit = "" if self.canonical_unit == "dimensionless" else f" {self.canonical_unit}"
        if self.exclusive:
            return f"more than {self.low:g} and less than {self.high:g}{unit}"
        return f"{self.low:g} to {self.high:g}{unit}"


_KILOGRAMS: Final = {
    "g": Decimal("0.001"),
    "kg": Decimal(1),
    "Mg": Decimal(1000),
    "t": Decimal(1000),
    "lb": Decimal("0.45359237"),
}
_CUBIC: Final = {
    "cm": Decimal("0.000001"),
    "dm": Decimal("0.001"),
    "m": Decimal(1),
    "in": Decimal("0.0254") ** 3,
    "ft": Decimal("0.3048") ** 3,
}
_VOLUMES: Final = {
    **{
        f"{length}{cube}": factor
        for length, factor in _CUBIC.items()
        for cube in ("^3", "3", "\u00b3")
    },
    "cc": Decimal("0.000001"),
    "mL": Decimal("0.000001"),
    "ml": Decimal("0.000001"),
    "L": Decimal("0.001"),
    "l": Decimal("0.001"),
}
_DENSITY_UNITS: Final = {
    f"{mass}/{volume}": kilograms / cubic
    for mass, kilograms in _KILOGRAMS.items()
    for volume, cubic in _VOLUMES.items()
}
_PRESSURE_UNITS: Final = {
    "Pa": Decimal("0.000001"),
    "kPa": Decimal("0.001"),
    "MPa": Decimal(1),
    "GPa": Decimal(1000),
    "psi": Decimal("0.006894757"),
    "ksi": Decimal("6.894757"),
    "N/mm2": Decimal(1),
    "N/mm^2": Decimal(1),
    "N/mm²": Decimal(1),
}
_UNITLESS: Final = {"": Decimal(1), "dimensionless": Decimal(1)}


def _strength(label: str) -> FieldSpec:
    return FieldSpec(label, "MPa", 0.1, 5000.0, _PRESSURE_UNITS, "MPa or GPa")


SPECS: Final[dict[Field, FieldSpec]] = {
    "density": FieldSpec("density", "kg/m^3", 500.0, 20000.0, _DENSITY_UNITS, "g/cm^3 or kg/m^3"),
    "elastic_modulus": FieldSpec(
        "elastic modulus", "MPa", 10.0, 500000.0, _PRESSURE_UNITS, "MPa or GPa"
    ),
    "poisson_ratio": FieldSpec(
        "Poisson's ratio",
        "dimensionless",
        0.0,
        0.5,
        _UNITLESS,
        "an empty string, since it has no unit",
        exclusive=True,
    ),
    "yield_strength": _strength("yield strength"),
    "tensile_strength": _strength("tensile strength"),
}
