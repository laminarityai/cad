from cad.briefs.assumptions import Assumption
from cad.briefs.model import MinSafetyFactor
from cad.checks.result import Verdict
from cad.scorecard import assumed
from cad.scorecard.assumed import AssumedRow
from cad.tables.materials import UNITS
from tests.support.scorecard import TARGET, quantity, result, suite, weighing

MASS = Assumption(
    target=TARGET.validate_python({"kind": "max_mass", "mass": quantity(120, "g")}),
    why="a light part prints fast",
)


def test_a_row_shows_the_assumed_value_beside_the_measure_and_holds_no_verdict() -> None:
    [row] = assumed.rows([MASS], weighing(0.2))
    [value] = row.values
    assert (row.check_id, row.instance, row.why, value.measure) == ("mass", "", MASS.why, "mass")
    assert value.assumed == UNITS.Quantity(120, "g")
    assert value.measured == UNITS.Quantity(0.2, "kg")
    assert not {"verdict", "mark", "comparisons", "passed"} & set(AssumedRow.model_fields)


def test_the_row_is_the_same_whether_the_measure_beats_the_value_or_misses_it() -> None:
    light, heavy = (assumed.rows([MASS], weighing(kg))[0] for kg in (0.05, 0.9))
    assert light.model_dump(exclude={"values"}) == heavy.model_dump(exclude={"values"})


def test_a_check_that_measured_nothing_leaves_the_measure_empty() -> None:
    [row] = assumed.rows([MASS], suite())
    assert [v.measured for v in row.values] == [None]


def test_an_unknown_check_leaves_the_measure_empty_not_a_failure() -> None:
    unknown = suite(result("mass", Verdict.UNKNOWN))
    [row] = assumed.rows([MASS], unknown)
    assert [v.measured for v in row.values] == [None]


def test_a_row_for_an_assumed_load_names_the_result_that_read_it() -> None:
    load = {
        "support": {"kind": "holes", "count": 2, "diameter": quantity(5.5, "mm")},
        "load": {
            "kind": "far_end",
            "force": quantity(49, "N"),
            "direction": {"kind": "across", "axis": "hole_axis"},
        },
    }
    target = MinSafetyFactor.model_validate(
        {"kind": "min_safety_factor", "load": load, "factor": 2}
    )
    solved = result("fea", Verdict.PASS, safety_factor=(3.0, "dimensionless")).model_copy(
        update={"instance": target.load.id}
    )
    [row] = assumed.rows([Assumption(target=target, why="a full shelf")], (*suite(), solved))
    [value] = row.values
    assert (row.check_id, row.instance) == ("fea", target.load.id)
    assert value.measured == UNITS.Quantity(3.0, "dimensionless")
