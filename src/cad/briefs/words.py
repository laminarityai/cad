from typing import assert_never

from cad.briefs.bindable import BINDABLE
from cad.briefs.model import (
    ClosedSolid,
    Envelope,
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


def measure_limit_words(target: MeasureLimit) -> str:
    words = BINDABLE[(target.check_id, target.measure)].words
    bound = "at most" if target.comparator is Comparator.AT_MOST else "at least"
    return f"{words[0].upper()}{words[1:]} is {bound} {amount(target.limit)}"


def describe(requirement: Requirement) -> str:
    """The plain words the page shows a person and the tools show the agent."""
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
            return f"Made of {target.material.removeprefix(PROJECT_PREFIX)}"
        case MinSafetyFactor():
            return f"Safety factor against yield at least {target.factor:g} with " + describe_case(
                target.load
            )
        case MaxDeflection():
            return f"Deflects at most {amount(target.deflection)} with {describe_case(target.load)}"
        case MinClearance():
            return f"At least {amount(target.clearance)} clear of context part {target.part}"
        case MaxClearance():
            return f"At most {amount(target.clearance)} clear of context part {target.part}"
        case _:
            assert_never(target)
