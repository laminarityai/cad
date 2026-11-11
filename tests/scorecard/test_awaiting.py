from cad.briefs.model import Requirement
from cad.checks.result import Verdict
from cad.scorecard import awaiting, requirements
from cad.scorecard.awaiting import AwaitingRow
from cad.tables.materials import UNITS
from tests.support.scorecard import checked, max_mass, requirement, result, suite, weighing


def test_a_row_shows_the_stated_value_beside_the_measure_and_holds_no_verdict() -> None:
    [row] = awaiting.rows([max_mass(30)], weighing(0.2))
    [value] = row.values
    assert (row.check_id, row.instance, value.measure) == ("mass", "", "mass")
    assert value.proposed == UNITS.Quantity(30, "g")
    assert value.measured == UNITS.Quantity(0.2, "kg")
    assert row.label == "waiting for your Confirm, no verdict"
    assert not {"verdict", "mark", "comparisons", "passed"} & set(AwaitingRow.model_fields)


def test_the_row_is_the_same_whether_the_measure_meets_the_target_or_misses_it() -> None:
    light, heavy = (awaiting.rows([max_mass(30)], weighing(kg))[0] for kg in (0.01, 0.9))
    assert light.model_dump(exclude={"values"}) == heavy.model_dump(exclude={"values"})


def test_a_check_that_measured_nothing_leaves_the_measure_empty() -> None:
    [row] = awaiting.rows([max_mass(30)], suite())
    assert [value.measured for value in row.values] == [None]
    unknown = suite(result("mass", Verdict.UNKNOWN))
    [again] = awaiting.rows([max_mass(30)], unknown)
    assert [value.measured for value in again.values] == [None]


def test_a_requirement_no_check_decides_has_no_row() -> None:
    unchecked: Requirement = requirement({"kind": "unchecked", "statement": "prints in an hour"})
    assert awaiting.rows([unchecked], weighing(0.2)) == ()


def test_confirming_judges_the_same_stored_results_with_no_rebuild() -> None:
    stored = weighing(0.2)
    waiting = max_mass(30)
    [row] = awaiting.rows([waiting], stored)
    [value] = row.values
    judged = checked(requirements.judge(waiting, stored))
    assert judged.verdict is Verdict.FAIL
    assert [comparison.limit for comparison in judged.comparisons] == [value.proposed]
