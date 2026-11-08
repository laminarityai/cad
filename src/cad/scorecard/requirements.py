"""Judge confirmed requirements against check results, on the host.

`cad.scorecard.score` never imports this module, so check versions do not hash it: judging a
requirement shapes no check result. The server passes its judgment in, and the tracer calls it
again to re-derive a stored card.
"""

from collections.abc import Sequence
from typing import Final

from cad.briefs.model import (
    Envelope,
    Limit,
    MadeOf,
    MaxDeflection,
    MinSafetyFactor,
    Requirement,
    Target,
    deciding_check,
    describe,
    limits,
)
from cad.briefs.store import ConfirmedSet
from cad.checks.jobs import Demand
from cad.checks.report import SPECS
from cad.checks.result import CheckResult, Comparator, Measured, Verdict
from cad.scorecard.model import (
    AgainstBrief,
    AwaitingConfirmation,
    Basis,
    Checked,
    Comparison,
    PendingCheck,
    RequirementResult,
    Unverified,
)
from cad.scorecard.score import Assess, Results
from cad.scorecard.waiting import Waiting
from cad.tables.materials import magnitude

UNIT_CONVERSION_NOISE: Final = 1e-9

MEETS: Final = "The measured value meets the confirmed limit."
MISSES: Final = "The measured value does not meet the confirmed limit."
CLOSED: Final = "The closed_solid check passed."
NOT_CLOSED: Final = "The closed_solid check failed; its reason says why."
UNDECIDED: Final = (
    "The deciding check did not pass, so there is no measure to compare; its reason says why."
)
NO_MEASURE: Final = "The deciding check passed but reported no measure to compare."
ROTATION: Final = (
    "The bounding box in the part's own axes is larger than the confirmed box. A rotated part "
    "might still fit, and no check measures the smallest box over all rotations."
)
WITHIN_ERROR: Final = "The measured value is within the check's stated error of the limit."
ERROR_BOUNDS: Final = {spec.id: spec.error_bounds for spec in SPECS}


def demand(confirmed: ConfirmedSet) -> Demand:
    return {
        one.target.load.id: one.target.load.wire()
        for one in confirmed.requirements
        if isinstance(one.target, MinSafetyFactor | MaxDeflection)
    }


def instance(target: Target) -> str:
    return target.load.id if isinstance(target, MinSafetyFactor | MaxDeflection) else ""


def against(confirmed: ConfirmedSet) -> Assess:
    def assess(results: Results) -> Basis:
        return assess_requirements(
            confirmed.brief_id, confirmed.decision_sha256, confirmed.requirements, results
        )

    return assess


def awaiting(brief_id: str) -> Assess:
    def assess(results: Results) -> Basis:
        del results
        return AwaitingConfirmation(brief_id=brief_id)

    return assess


def assess_requirements(
    brief_id: str,
    decision_sha256: str,
    confirmed: Sequence[Requirement],
    results: Sequence[CheckResult | PendingCheck],
) -> AgainstBrief:
    judged = tuple(
        judge(requirement, results)
        for requirement in confirmed
        if not isinstance(requirement.target, MadeOf)
    )
    return AgainstBrief(
        brief_id=brief_id,
        decision_sha256=decision_sha256,
        requirements=judged,
        unverified_requirements=tuple(
            one.requirement_id for one in judged if isinstance(one, Unverified)
        ),
    )


def judge(
    requirement: Requirement, results: Sequence[CheckResult | PendingCheck]
) -> RequirementResult:
    statement = describe(requirement)
    check_id = deciding_check(requirement.target)
    if check_id is None:
        return Unverified(requirement_id=requirement.id, statement=statement)
    result = _result_of(results, check_id, instance(requirement.target))
    if isinstance(result, PendingCheck):
        return Waiting(requirement_id=requirement.id, statement=statement, check_id=check_id)
    missed = Verdict.UNKNOWN if isinstance(requirement.target, Envelope) else Verdict.FAIL
    bounds = ERROR_BOUNDS.get(check_id, {})
    comparisons = tuple(
        _compare(result, limit, missed, bounds.get(limit.measure, 0.0))
        for limit in limits(requirement.target)
    )
    verdict = _fold(result, comparisons)
    return Checked(
        requirement_id=requirement.id,
        statement=statement,
        check_id=check_id,
        verdict=verdict,
        reason=_reason(result, comparisons, verdict, missed),
        comparisons=comparisons,
    )


def _result_of(
    results: Sequence[CheckResult | PendingCheck], check_id: str, wanted: str
) -> CheckResult | PendingCheck:
    for result in results:
        if result.check_id == check_id and result.instance == wanted:
            return result
    named = f" for load case {wanted}" if wanted else ""
    raise NoDecidingResult(f"no result for the deciding check {check_id}{named}")


def _compare(result: CheckResult, limit: Limit, missed: Verdict, error: float) -> Comparison:
    verdict = Verdict.UNKNOWN
    measured = _measured(result, limit.measure)
    if result.verdict is Verdict.PASS and measured is not None:
        if _holds(measured, limit, _worse(limit, error)):
            verdict = Verdict.PASS
        elif not _holds(measured, limit, _worse(limit, -error)):
            verdict = missed
    return Comparison(
        measure=limit.measure, comparator=limit.comparator, limit=limit.quantity, verdict=verdict
    )


class NoDecidingResult(Exception):
    pass


def _measured(result: CheckResult, name: str) -> Measured | None:
    for measure in result.measured:
        if measure.name == name:
            return measure.value
    return None


def _worse(limit: Limit, error: float) -> float:
    return 1 + error if limit.comparator is Comparator.AT_MOST else 1 - error


def _holds(measured: Measured, limit: Limit, factor: float = 1.0) -> bool:
    unit = str(limit.quantity.units)
    value = magnitude(measured, unit) * factor
    bound = magnitude(limit.quantity, unit)
    match limit.comparator:
        case Comparator.AT_MOST:
            return value <= bound * (1 + UNIT_CONVERSION_NOISE)
        case Comparator.AT_LEAST:
            return value >= bound * (1 - UNIT_CONVERSION_NOISE)


def _fold(result: CheckResult, comparisons: tuple[Comparison, ...]) -> Verdict:
    if not comparisons:
        return result.verdict
    verdicts = {one.verdict for one in comparisons}
    if Verdict.FAIL in verdicts:
        return Verdict.FAIL
    return Verdict.UNKNOWN if Verdict.UNKNOWN in verdicts else Verdict.PASS


def _reason(
    result: CheckResult, comparisons: tuple[Comparison, ...], verdict: Verdict, missed: Verdict
) -> str:
    if not comparisons:
        return {Verdict.PASS: CLOSED, Verdict.FAIL: NOT_CLOSED}.get(verdict, UNDECIDED)
    if result.verdict is not Verdict.PASS:
        return UNDECIDED
    if any(_measured(result, one.measure) is None for one in comparisons):
        return NO_MEASURE
    undecided = ROTATION if missed is Verdict.UNKNOWN else WITHIN_ERROR
    return {Verdict.PASS: MEETS, Verdict.FAIL: MISSES}.get(verdict, undecided)
