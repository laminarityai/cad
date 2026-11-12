"""Judge a holes requirement against the holes check, on the host.

A hole counts toward the requirement when its measured diameter lies in a band. A fastener size's
band comes from the fasteners table by exact key, and a plain hole's band is the stated diameter
with a tolerance. No number comes from the agent. The check measures every round hole in the part,
so the matching holes are counted here, from `hole_diameter:i`.

The card carries the band as two comparisons on `hole_diameter`, the lower and then the upper
limit, so each number on it is a quantity a reader can trace. Both carry the requirement's verdict.
A reason holds no digit, as the other reasons hold none.
"""

from dataclasses import dataclass
from typing import Final

from cad.briefs.model import FastenerHoles, HoleFit, PlainHoles, Requirement
from cad.checks.result import CheckResult, Comparator, Verdict
from cad.scorecard.model import Checked, Comparison
from cad.tables.fasteners import load_fasteners
from cad.tables.materials import UNITS, magnitude

MEASURE: Final = "hole_diameter"
DIAMETER_NOISE_MM: Final = 1e-4
"""A cylinder's diameter in the part is exact to float and STEP rounding, far below 1e-4 mm, so a
hole drawn at the table's own number matches it. Nothing wider is allowed on a table band."""
PLAIN_TOLERANCE_MM: Final = 0.05
"""A plain hole matches its stated diameter within this. The person states one number and no
tolerance. This is the fine class of ISO 2768 linear tolerances for sizes up to 6 mm."""
UNMEASURED: Final = (
    "The holes check did not measure every opening, so the holes are not all counted; "
    "its reason says which."
)
TOO_MANY: Final = "More round holes lie in the confirmed range than the person confirmed."
TOO_FEW: Final = "Fewer round holes lie in the confirmed range than the person confirmed."
NONE: Final = "No round hole lies in the confirmed range."
ENOUGH: Final = "At least one round hole lies in the confirmed range."
EXACT: Final = "As many round holes lie in the confirmed range as the person confirmed."


@dataclass(frozen=True, slots=True)
class Band:
    """The diameters a hole may have, inclusive, in mm."""

    low: float
    high: float


def band(target: FastenerHoles | PlainHoles) -> Band:
    if isinstance(target, PlainHoles):
        wanted = magnitude(target.diameter, "mm")
        return Band(wanted - PLAIN_TOLERANCE_MM, wanted + PLAIN_TOLERANCE_MM)
    row = load_fasteners().get(target.size)
    if target.fit is HoleFit.TAPPED:
        return Band(row.tapped.minor_min_mm, row.tapped.minor_max_mm)
    return Band(row.clearance.close_mm, row.clearance.coarse_mm)


def judged(requirement: Requirement, statement: str, result: CheckResult) -> Checked:
    target = requirement.target
    if not isinstance(target, FastenerHoles | PlainHoles):
        raise TypeError(f"{type(target).__name__} is not a holes requirement")
    wanted = band(target)
    low, high = wanted.low - DIAMETER_NOISE_MM, wanted.high + DIAMETER_NOISE_MM
    matching = sum(low <= size <= high for size in _diameters(result))
    verdict, reason = _verdict(result, matching, target.count)
    limits = ((Comparator.AT_LEAST, wanted.low), (Comparator.AT_MOST, wanted.high))
    return Checked(
        requirement_id=requirement.id,
        statement=statement,
        check_id=result.check_id,
        verdict=verdict,
        reason=reason,
        comparisons=tuple(
            Comparison(
                measure=MEASURE,
                comparator=comparator,
                limit=UNITS.Quantity(limit, "mm"),
                verdict=verdict,
            )
            for comparator, limit in limits
        ),
    )


def _diameters(result: CheckResult) -> list[float]:
    named = (m for m in result.measured if m.name.startswith(f"{MEASURE}:"))
    return [magnitude(m.value, "mm") for m in named]


def _verdict(result: CheckResult, matching: int, count: int | None) -> tuple[Verdict, str]:
    """Too many holes fail even when the check is unknown, since an opening it could not classify
    cannot remove a hole that already matches. Every other shortfall waits for a full count."""
    if count is not None and matching > count:
        return Verdict.FAIL, TOO_MANY
    if result.verdict is not Verdict.PASS:
        return Verdict.UNKNOWN, UNMEASURED
    if count is None:
        return (Verdict.PASS, ENOUGH) if matching >= 1 else (Verdict.FAIL, NONE)
    if matching == count:
        return Verdict.PASS, EXACT
    return Verdict.FAIL, TOO_FEW
