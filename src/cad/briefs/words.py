from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, assert_never

from cad.briefs.bindable import BINDABLE
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
    Unchecked,
    amount,
)
from cad.checks.result import Comparator
from cad.loads.words import describe_case
from cad.tables.materials import PROJECT_PREFIX

NO_NAMES: Final[Mapping[str, str]] = MappingProxyType({})


def measure_limit_words(target: MeasureLimit) -> str:
    words = BINDABLE[(target.check_id, target.measure)].words
    bound = "at most" if target.comparator is Comparator.AT_MOST else "at least"
    return f"{words[0].upper()}{words[1:]} is {bound} {amount(target.limit)}"


def describe(requirement: Requirement, names: Mapping[str, str] = NO_NAMES) -> str:
    """The plain words the tools show the agent. The page shows a person the same words with
    `names`, which maps a context part's id and a material's key to the name a person reads."""
    target = requirement.target
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
        case _:
            assert_never(target)


def _clearance(clearance: Length, part: str, names: Mapping[str, str]) -> str:
    name = names.get(part)
    if name is None:
        return f"{amount(clearance)} clear of context part {part}"
    return f"{amount(clearance)} gap to {name}"
