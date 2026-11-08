from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from cad.sources.units import PRESSURE_UNITS, Unit, density_unit

type Field = Literal[
    "density", "elastic_modulus", "poisson_ratio", "yield_strength", "tensile_strength"
]

MAX_QUOTE_LENGTH: Final = 500
UNITLESS: Final = Unit("", Decimal(1))
GENERIC_LABELS: Final = ("typical", "nominal", "value")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """`exclusive` keeps `low` and `high` themselves out, as the materials table's rules do."""

    label: str
    canonical_unit: str
    low: float
    high: float
    units: Mapping[str, Unit]
    unit_hint: str
    labels: tuple[str, ...]
    needs_label: bool = True
    exclusive: bool = False

    def admits(self, value: Decimal) -> bool:
        if self.exclusive:
            return self.low < value < self.high
        return self.low <= value <= self.high

    @property
    def accepts(self) -> str:
        """The accepted range, in words: "0.1 to 5000 MPa" or "more than 0 and less than 0.5"."""
        unit = "" if self.unitless else f" {self.canonical_unit}"
        if self.exclusive:
            return f"more than {self.low:g} and less than {self.high:g}{unit}"
        return f"{self.low:g} to {self.high:g}{unit}"

    @property
    def unitless(self) -> bool:
        return not self.units

    @property
    def per_volume(self) -> bool:
        return self.canonical_unit == "kg/m^3"


_DENSITY_UNITS: Final = {
    f"{mass}/{volume}": density_unit(mass, volume)
    for mass, volume in (
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
}


def _strength(label: str, low: float, labels: tuple[str, ...]) -> FieldSpec:
    return FieldSpec(label, "MPa", low, 5000.0, PRESSURE_UNITS, "MPa", labels)


SPECS: Final[dict[Field, FieldSpec]] = {
    "density": FieldSpec(
        "density",
        "kg/m^3",
        500.0,
        20000.0,
        _DENSITY_UNITS,
        "g/cm3 or kg/m3",
        ("mass density", "density", "densidad", "dichte", "densité", "\u03c1"),
        needs_label=False,
    ),
    "elastic_modulus": FieldSpec(
        "elastic modulus",
        "MPa",
        10.0,
        500000.0,
        PRESSURE_UNITS,
        "MPa or GPa",
        (
            "elastic modulus",
            "modulus of elasticity",
            "young's modulus",
            "youngs modulus",
            "young modulus",
            "tensile modulus",
            "e-modulus",
        ),
    ),
    "poisson_ratio": FieldSpec(
        "Poisson's ratio",
        "dimensionless",
        0.0,
        0.5,
        {},
        "a number with no unit",
        ("poisson's ratio", "poissons ratio", "poisson ratio"),
        exclusive=True,
    ),
    "yield_strength": _strength(
        "yield strength",
        0.1,
        (
            "yield strength",
            "tensile yield strength",
            "tensile strength at yield",
            "tensile stress at yield",
            "stress at yield",
            "yield stress",
        ),
    ),
    "tensile_strength": _strength(
        "tensile strength",
        0.1,
        (
            "tensile strength",
            "ultimate tensile strength",
            "tensile strength at break",
            "tensile stress at break",
        ),
    ),
}
ALL_LABELS: Final = (*GENERIC_LABELS, *(label for spec in SPECS.values() for label in spec.labels))


def label_key(text: str) -> str:
    return " ".join(text.replace("\u2019", "'").casefold().split())
