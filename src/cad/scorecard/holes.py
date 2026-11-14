"""Judge a holes requirement against the holes check, on the host.

A hole counts toward the requirement when its measured diameter lies in a band. A fastener size's
band comes from the fasteners table by exact key, narrowed to one diameter when the person states a
series. A plain hole's band is the stated diameter with the tolerance on the requirement: a length
the person confirmed, or a class of the tolerances table by exact key. No number comes from the
agent. The check measures every round hole in the part, so the matching holes are counted here,
from `hole_diameter:i`.

The card carries the band as two comparisons on `hole_diameter`, the lower and then the upper
limit, so each number on it is a quantity a reader can trace. Each comparison passes when enough
holes meet its own bound: the confirmed count, or one hole when no count was stated. Only the
requirement's verdict counts the holes that meet both. A reason holds no digit, as the other
reasons hold none.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from cad.briefs.holes import ByClass, FastenerHoles, HoleFit, PlainHoles, PlusMinus
from cad.briefs.model import Requirement
from cad.checks.result import CheckResult, Comparator, Measure, Measured, Verdict
from cad.sandbox.on_body import per_body
from cad.scorecard.model import Checked, Comparison
from cad.tables.fasteners import load_fasteners
from cad.tables.materials import UNITS, Source, magnitude
from cad.tables.tolerances import load_tolerances

MEASURE: Final = "hole_diameter"
OPENINGS: Final = "unclassified_openings"
DIAMETER_NOISE_MM: Final = 1e-4
"""A cylinder's diameter in the part is exact to float and STEP rounding, far below 1e-4 mm, so a
hole drawn at the table's own number matches it. Nothing wider is allowed on a table band."""
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
    """The diameters a hole may have, inclusive, in mm, and the table rows they were read from."""

    low: float
    high: float
    sources: tuple[Source, ...] = ()


def band(target: FastenerHoles | PlainHoles) -> Band:
    """The band the confirmed target names. A plain hole's tolerance is on the requirement, either
    a plus-or-minus length the person confirmed or a class read by its exact key and the diameter's
    size range. A fastener's band is its table row, or the one diameter of its series."""
    if isinstance(target, PlainHoles):
        wanted = magnitude(target.diameter, "mm")
        match target.tolerance:
            case PlusMinus(within=within):
                around = magnitude(within, "mm")
                return Band(wanted - around, wanted + around)
            case ByClass(key=key):
                limits = load_tolerances().limits(key, wanted)
                return Band(limits.low_mm, limits.high_mm, (limits.source,))
    row = load_fasteners().get(target.size)
    if target.fit is HoleFit.TAPPED:
        return Band(row.tapped.minor_min_mm, row.tapped.minor_max_mm, (row.tapped.source,))
    cited = (row.clearance.source,)
    if target.series is not None:
        one = row.clearance.diameter_mm(target.series)
        return Band(one, one, cited)
    return Band(row.clearance.close_mm, row.clearance.coarse_mm, cited)


def judged(requirement: Requirement, statement: str, result: CheckResult) -> Checked:
    target = requirement.target
    if not isinstance(target, FastenerHoles | PlainHoles):
        raise TypeError(f"{type(target).__name__} is not a holes requirement")
    wanted = band(target)
    low, high = wanted.low - DIAMETER_NOISE_MM, wanted.high + DIAMETER_NOISE_MM
    sizes = [magnitude(one, "mm") for one in diameters(result.measured, target.body)]
    matching = sum(low <= size <= high for size in sizes)
    complete = _all_counted(result, target.body)
    verdict, reason = _verdict(complete, matching, target.count)
    limits = (
        (Comparator.AT_LEAST, wanted.low, sum(size >= low for size in sizes)),
        (Comparator.AT_MOST, wanted.high, sum(size <= high for size in sizes)),
    )
    return Checked(
        requirement_id=requirement.id,
        statement=statement,
        check_id=result.check_id,
        verdict=verdict,
        reason=reason,
        comparisons=tuple(
            Comparison(
                measure=per_body(MEASURE, target.body),
                comparator=comparator,
                limit=UNITS.Quantity(limit, "mm"),
                verdict=_bound(complete, meeting, target.count),
            )
            for comparator, limit, meeting in limits
        ),
        sources=wanted.sources,
    )


def diameters(measured: Sequence[Measure], body: str | None) -> tuple[Measured, ...]:
    """The diameters the check lists for the whole variant, or for the one body named."""
    listed = re.compile(re.escape(per_body(MEASURE, body)) + r":\d+")
    return tuple(one.value for one in measured if listed.fullmatch(one.name))


def _all_counted(result: CheckResult, body: str | None) -> bool:
    if body is None:
        return result.verdict is Verdict.PASS
    left = next(
        (one.value for one in result.measured if one.name == per_body(OPENINGS, body)), None
    )
    return left is not None and magnitude(left, "dimensionless") == 0


def _bound(complete: bool, meeting: int, count: int | None) -> Verdict:
    """A bound waits for a full count, as every other kind's comparison waits for a measured
    result."""
    if not complete:
        return Verdict.UNKNOWN
    return Verdict.PASS if meeting >= (1 if count is None else count) else Verdict.FAIL


def _verdict(complete: bool, matching: int, count: int | None) -> tuple[Verdict, str]:
    """Too many holes fail even when the check is unknown, since an opening it could not classify
    cannot remove a hole that already matches. Every other shortfall waits for a full count."""
    if count is not None and matching > count:
        return Verdict.FAIL, TOO_MANY
    if not complete:
        return Verdict.UNKNOWN, UNMEASURED
    if count is None:
        return (Verdict.PASS, ENOUGH) if matching >= 1 else (Verdict.FAIL, NONE)
    if matching == count:
        return Verdict.PASS, EXACT
    return Verdict.FAIL, TOO_FEW
