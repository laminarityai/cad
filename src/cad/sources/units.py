"""The unit spellings the reader knows, as exact keys. Nothing here parses a unit expression."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final


@dataclass(frozen=True, slots=True)
class Unit:
    symbol: str
    to_canonical: Decimal


_KILOGRAMS: Final = {
    "g": ("g", Decimal("0.001")),
    "kg": ("kg", Decimal(1)),
    "Mg": ("Mg", Decimal(1000)),
    "t": ("t", Decimal(1000)),
    "lb": ("lb", Decimal("0.45359237")),
}
_CUBIC_METRES: Final = {
    "cm": ("cm^3", Decimal("0.000001")),
    "cc": ("cm^3", Decimal("0.000001")),
    "ml": ("mL", Decimal("0.000001")),
    "l": ("L", Decimal("0.001")),
    "dm": ("dm^3", Decimal("0.001")),
    "m": ("m^3", Decimal(1)),
    "in": ("in^3", Decimal("0.0254") ** 3),
    "ft": ("ft^3", Decimal("0.3048") ** 3),
}


def density_unit(mass: str, volume: str) -> Unit:
    mass_symbol, kilograms = _KILOGRAMS[mass]
    volume_symbol, cubic_metres = _CUBIC_METRES[volume]
    return Unit(f"{mass_symbol}/{volume_symbol}", kilograms / cubic_metres)


_MPA: Final = {
    "Pa": Decimal("0.000001"),
    "kPa": Decimal("0.001"),
    "MPa": Decimal(1),
    "Mpa": Decimal(1),
    "MPA": Decimal(1),
    "GPa": Decimal(1000),
    "Gpa": Decimal(1000),
    "GPA": Decimal(1000),
    "psi": Decimal("0.006894757"),
    "ksi": Decimal("6.894757"),
    "N/mm2": Decimal(1),
    "N/mm^2": Decimal(1),
}
PRESSURE_UNITS: Final = {spelling: Unit(spelling, factor) for spelling, factor in _MPA.items()}


_MASSES: Final = ("g", "kg", "mg", "lb", "lbs", "t", "oz")
_LENGTHS: Final = ("mm", "cm", "dm", "m", "in", "ft", "um", "μm")
_PRESSURES: Final = ("pa", "kpa", "mpa", "gpa", "psi", "ksi", "bar")

_DIMENSIONS: Final[dict[str, str]] = {
    **dict.fromkeys(_MASSES, "mass"),
    **dict.fromkeys(_LENGTHS, "length"),
    **dict.fromkeys(_PRESSURES, "pressure"),
    **{f"{mass}/{length}": "mass per length" for mass in _MASSES for length in _LENGTHS},
    **{f"{mass}/{length}2": "mass per area" for mass in _MASSES for length in _LENGTHS},
}


def dimension(spelling: str) -> str | None:
    """The dimension of a known unit spelling, or None. An unknown spelling is never guessed."""
    key = spelling.casefold().replace(".", "").replace("^", "").replace(" ", "")
    return _DIMENSIONS.get(key)
