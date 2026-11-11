"""What a scorecard says about the agent's assumptions.

An assumption has no verdict, by structure: `AssumedRow` has no verdict, mark or comparison
field, and `cad.scorecard.score` never imports this module, so no check version, no requirement
judgment and no Auto standing reads it. A row shows the value the agent assumed beside what the
deciding check measured, and a person reads the two.
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from cad.briefs.assumptions import Assumption
from cad.briefs.model import deciding_check, limits
from cad.briefs.words import NO_NAMES, describe_target
from cad.checks.result import CheckResult, Measured
from cad.frozen import Frozen
from cad.scorecard.model import PendingCheck
from cad.scorecard.requirements import instance, result_of


class AssumedValue(Frozen):
    measure: str
    assumed: Measured
    measured: Measured | None


class AssumedRow(Frozen):
    """The agent filled in this value. The measure of the deciding check is beside it, and it is
    never graded."""

    kind: Literal["assumed"] = "assumed"
    label: Literal["assumed by the agent, no verdict"] = "assumed by the agent, no verdict"
    statement: str
    why: str
    check_id: str
    values: tuple[AssumedValue, ...]


def rows(
    assumptions: Sequence[Assumption],
    results: Sequence[CheckResult | PendingCheck],
    names: Mapping[str, str] = NO_NAMES,
) -> tuple[AssumedRow, ...]:
    return tuple(_row(one, results, names) for one in assumptions)


def _row(
    assumption: Assumption,
    results: Sequence[CheckResult | PendingCheck],
    names: Mapping[str, str],
) -> AssumedRow:
    target = assumption.target
    check_id = deciding_check(target)
    if check_id is None:
        raise ValueError("an assumption names a target that a check decides")
    result = result_of(results, check_id, instance(target))
    measures = result.measured if isinstance(result, CheckResult) else ()
    found = {one.name: one.value for one in measures}
    return AssumedRow(
        statement=describe_target(target, names),
        why=assumption.why,
        check_id=check_id,
        values=tuple(
            AssumedValue(measure=one.measure, assumed=one.quantity, measured=found.get(one.measure))
            for one in limits(target)
        ),
    )
