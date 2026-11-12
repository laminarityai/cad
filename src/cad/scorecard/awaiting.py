"""What a scorecard says about a stated target that waits for the person's Confirm.

A target the person stated has no verdict until they confirm it. `AwaitingRow` has no verdict,
mark or comparison field, and `cad.scorecard.score` never imports this module, so no check
version, no requirement judgment and no Auto standing reads it. A row shows the value the person
stated beside what the deciding check measured, and a person reads the two. After Confirm the
same stored check results are judged against the confirmed set, with no rebuild.
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from cad.briefs.model import Requirement, deciding_check, limits
from cad.briefs.words import NO_NAMES, describe
from cad.checks.result import CheckResult, Measured
from cad.frozen import Frozen
from cad.scorecard.requirements import instance, result_of
from cad.scorecard.unjudged import MeasureOnly, Reported


class AwaitingValue(Frozen):
    measure: str
    proposed: Measured
    measured: Measured | None


class AwaitingRow(Frozen):
    """The person stated this target and has not confirmed it, so it is not judged. `instance`
    names the result of `check_id` that read its load, which the card reports as a `MeasureOnly`
    with no verdict."""

    kind: Literal["awaiting"] = "awaiting"
    label: Literal["waiting for your Confirm, no verdict"] = "waiting for your Confirm, no verdict"
    requirement_id: str
    statement: str
    check_id: str
    instance: str
    values: tuple[AwaitingValue, ...]


def rows(
    waiting: Sequence[Requirement],
    results: Sequence[Reported],
    names: Mapping[str, str] = NO_NAMES,
) -> tuple[AwaitingRow, ...]:
    return tuple(
        _row(one, check_id, results, names)
        for one in waiting
        if (check_id := deciding_check(one.target)) is not None
    )


def _row(
    requirement: Requirement,
    check_id: str,
    results: Sequence[Reported],
    names: Mapping[str, str],
) -> AwaitingRow:
    target = requirement.target
    reads = instance(target)
    result = result_of(results, check_id, reads)
    measures = result.measured if isinstance(result, CheckResult | MeasureOnly) else ()
    found = {one.name: one.value for one in measures}
    return AwaitingRow(
        requirement_id=requirement.id,
        statement=describe(requirement, names),
        check_id=check_id,
        instance=reads,
        values=tuple(
            AwaitingValue(
                measure=one.measure, proposed=one.quantity, measured=found.get(one.measure)
            )
            for one in limits(target)
        ),
    )
