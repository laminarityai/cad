from typing import Any

from cad.briefs.model import MinSafetyFactor
from cad.checks.result import CheckResult, Verdict
from cad.scorecard import awaiting, requirements, unjudged
from cad.scorecard.unjudged import MeasureOnly
from cad.tables.materials import UNITS
from tests.support.scorecard import checked, quantity, requirement, result, suite

LOAD: dict[str, Any] = {
    "support": {"kind": "flat_end"},
    "load": {"kind": "far_end", "force": quantity(20, "N"), "direction": {"kind": "any"}},
}
HOLDS = requirement({"kind": "min_safety_factor", "load": LOAD, "factor": 2})
TARGET = MinSafetyFactor.model_validate({"kind": "min_safety_factor", "load": LOAD, "factor": 2})
SOLVED = result("fea", Verdict.PASS, safety_factor=(3.0, "dimensionless")).model_copy(
    update={"instance": TARGET.load.id}
)
STORED = (*suite(), SOLVED)


def reported(confirmed: tuple[MinSafetyFactor, ...] = ()) -> tuple[unjudged.Reported, ...]:
    return unjudged.without_verdicts(STORED, unjudged.unconfirmed_loads([TARGET], confirmed))


def test_a_result_under_an_unconfirmed_load_keeps_its_measures_and_has_no_verdict() -> None:
    fea = next(one for one in reported() if one.check_id == "fea")
    assert isinstance(fea, MeasureOnly)
    assert "verdict" not in fea.model_dump()
    assert fea.label == "measured under a load you have not confirmed, no verdict"
    assert fea.model_dump(exclude={"kind", "label"}) == SOLVED.model_dump(exclude={"verdict"})


def test_a_result_with_no_load_keeps_its_verdict() -> None:
    kept = [one for one in reported() if one.check_id != "fea"]
    assert kept == list(suite())
    assert all(isinstance(one, CheckResult) for one in kept)


def test_a_load_a_confirmed_target_also_reads_is_judged() -> None:
    assert reported(confirmed=(TARGET,)) == STORED


def test_the_awaiting_row_reads_the_measure_from_the_result_with_no_verdict() -> None:
    [row] = awaiting.rows([HOLDS], reported())
    assert [value.measured for value in row.values] == [UNITS.Quantity(3.0, "dimensionless")]


def test_after_confirm_the_same_stored_result_is_judged_with_no_rebuild() -> None:
    assert isinstance(reported()[-1], MeasureOnly)
    assert checked(requirements.judge(HOLDS, STORED)).verdict is Verdict.PASS
