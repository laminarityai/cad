"""What a reported scorecard says about a check result under a load nobody confirmed.

A load the agent assumed, or one the person stated and has not confirmed, is not a target a
verdict may rest on. The check still runs under it, and its stored result keeps its own verdict,
so after Confirm the same stored result is judged with no rebuild. The card reports that result
as a `MeasureOnly`, which has no verdict field. `cad.scorecard.score` never imports this module,
so no check version, no requirement judgment and no Auto standing reads it.
"""

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import Field

from cad.briefs.model import MaxDeflection, MinSafetyFactor, Target, deciding_check
from cad.checks.result import CheckResult, Measure, Read, Source
from cad.frozen import Frozen
from cad.scorecard.model import PendingCheck


class MeasureOnly(Frozen):
    """A check result under a load nobody confirmed: its measures, formula and sources, and no
    verdict. The awaiting or assumed row with the same `check_id` and `instance` sets its measure
    beside the stated or assumed value."""

    kind: Literal["measure_only"] = "measure_only"
    label: Literal["measured under a load you have not confirmed, no verdict"] = (
        "measured under a load you have not confirmed, no verdict"
    )
    check_id: str
    measured: tuple[Measure, ...]
    formula: str
    reason: str
    sources: tuple[Source, ...]
    version: str
    instance: str = Field(default="", exclude_if=lambda instance: not instance)
    reads: tuple[Read, ...] = Field(default=(), exclude_if=lambda reads: not reads)


type Reported = CheckResult | PendingCheck | MeasureOnly


def unconfirmed_loads(
    unconfirmed: Iterable[Target], confirmed: Iterable[Target]
) -> frozenset[tuple[str, str]]:
    """The (check_id, load id) of each load a target in `unconfirmed` reads and no confirmed
    target reads."""
    return _loads(unconfirmed) - _loads(confirmed)


def without_verdicts(
    results: Sequence[Reported], loads: frozenset[tuple[str, str]]
) -> tuple[Reported, ...]:
    return tuple(
        _measure_only(one)
        if isinstance(one, CheckResult) and (one.check_id, one.instance) in loads
        else one
        for one in results
    )


def _loads(targets: Iterable[Target]) -> frozenset[tuple[str, str]]:
    return frozenset(
        (check_id, target.load.id)
        for target in targets
        if isinstance(target, MinSafetyFactor | MaxDeflection)
        and (check_id := deciding_check(target)) is not None
    )


def _measure_only(result: CheckResult) -> MeasureOnly:
    return MeasureOnly(
        check_id=result.check_id,
        measured=result.measured,
        formula=result.formula,
        reason=result.reason,
        sources=result.sources,
        version=result.version,
        instance=result.instance,
        reads=result.reads,
    )
