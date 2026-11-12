from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, assert_never

from cad.briefs.bindable import BINDABLE
from cad.briefs.holes import ByClass, FastenerHoles, HoleFit, PlainHoles, PlusMinus
from cad.briefs.model import (
    ClosedSolid,
    Envelope,
    Length,
    MadeOf,
    MaxClearance,
    MaxDeflection,
    MaxMass,
    MeasureLimit,
    MinClearance,
    MinMass,
    MinSafetyFactor,
    Requirement,
    Target,
    Unchecked,
    amount,
)
from cad.checks.result import Comparator
from cad.loads.words import describe_case
from cad.tables.fasteners import load_fasteners
from cad.tables.materials import PROJECT_PREFIX, magnitude
from cad.tables.tolerances import load_tolerances

NO_NAMES: Final[Mapping[str, str]] = MappingProxyType({})


def measure_limit_words(target: MeasureLimit) -> str:
    words = BINDABLE[(target.check_id, target.measure)].words
    bound = "at most" if target.comparator is Comparator.AT_MOST else "at least"
    return f"{words[0].upper()}{words[1:]} is {bound} {amount(target.limit)}"


def describe(requirement: Requirement, names: Mapping[str, str] = NO_NAMES) -> str:
    return describe_target(requirement.target, names)


def describe_target(target: Target, names: Mapping[str, str] = NO_NAMES) -> str:
    match target:
        case ClosedSolid():
            return "The part is one closed solid"
        case MaxMass():
            return f"Mass at most {amount(target.mass)}"
        case MinMass():
            return f"Mass at least {amount(target.mass)}"
        case Envelope():
            return "Fits inside a box of " + " x ".join(amount(edge) for edge in target.edges)
        case MeasureLimit():
            return measure_limit_words(target)
        case Unchecked():
            return target.statement
        case MadeOf():
            key = target.material
            return f"Made of {names.get(key) or key.removeprefix(PROJECT_PREFIX)}"
        case MinSafetyFactor():
            return f"Safety factor against yield at least {target.factor:g} with " + describe_case(
                target.load
            )
        case MaxDeflection():
            return f"Deflects at most {amount(target.deflection)} with {describe_case(target.load)}"
        case MinClearance():
            return f"At least {_clearance(target.clearance, target.part, names)}"
        case MaxClearance():
            return f"At most {_clearance(target.clearance, target.part, names)}"
        case FastenerHoles():
            return _holes(target.count, _for_a_bolt(target))
        case PlainHoles():
            return _holes(target.count, _of_a_diameter(target))
        case _:
            assert_never(target)


def _holes(count: int | None, what: str) -> str:
    """ "2 holes that fit an M5 bolt", or "A hole that fits an M5 bolt" when no count is stated."""
    plural = count is not None and count != 1
    noun = f"{count} holes" if plural else ("A hole" if count is None else "1 hole")
    return f"{noun} {what.replace('{s}', '' if plural else 's')}"


def _for_a_bolt(target: FastenerHoles) -> str:
    if target.fit is HoleFit.TAPPED:
        return f"tapped for {target.size}"
    fits = f"that fit{{s}} an {target.size} bolt"
    if target.series is None:
        return fits
    diameter = load_fasteners().get(target.size).clearance.diameter_mm(target.series)
    return f"{fits}, {target.series.value} series ({diameter:g} mm)"


def _of_a_diameter(target: PlainHoles) -> str:
    """ "of 8 mm, H7 (8.000 to 8.015 mm)", or "of 8 mm, within ±0.05 mm"."""
    match target.tolerance:
        case PlusMinus(within=within):
            return f"of {amount(target.diameter)}, within \u00b1{amount(within)}"
        case ByClass(key=key):
            band = load_tolerances().limits(key, magnitude(target.diameter, "mm"))
            return (
                f"of {amount(target.diameter)}, {key} ({band.low_mm:.3f} to {band.high_mm:.3f} mm)"
            )


def _clearance(clearance: Length, part: str, names: Mapping[str, str]) -> str:
    name = names.get(part)
    if name is None:
        return f"{amount(clearance)} clear of context part {part}"
    return f"{amount(clearance)} gap to {name}"
