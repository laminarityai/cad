import re
from typing import Any

import pytest

from cad.briefs.model import Requirement
from cad.briefs.words import describe
from cad.checks.result import CheckResult, Verdict
from cad.scorecard import requirements
from cad.scorecard.model import AgainstBrief, PendingCheck, Unverified
from cad.scorecard.waiting import Waiting
from cad.tables.materials import UNITS
from tests.support.scorecard import (
    BRIEF,
    SPEC,
    boxed,
    checked,
    envelope,
    max_mass,
    min_mass,
    quantity,
    requirement,
    result,
    suite,
    weighing,
)


@pytest.mark.parametrize(
    ("given", "results", "verdict"),
    [
        (max_mass(150), weighing(0.15), Verdict.PASS),
        (max_mass(150), weighing(0.1500001), Verdict.FAIL),
        (max_mass(150), weighing(0.12), Verdict.PASS),
        (max_mass(0.1, "kg"), weighing(0.12), Verdict.FAIL),
        (min_mass(150), weighing(0.15), Verdict.PASS),
        (min_mass(150), weighing(0.1499999), Verdict.FAIL),
        (min_mass(0.2, "kg"), weighing(0.25), Verdict.PASS),
    ],
)
def test_a_mass_limit_holds_inclusively_across_units(
    given: Requirement, results: tuple[CheckResult, ...], verdict: Verdict
) -> None:
    judged = checked(requirements.judge(given, results))
    assert judged.check_id == "mass"
    assert judged.verdict == verdict
    assert [c.verdict for c in judged.comparisons] == [verdict]


def test_a_part_built_exactly_to_a_limit_in_another_unit_passes_through_float_noise() -> None:
    noisy = 40 * (1 + 1e-12)
    judged = checked(
        requirements.judge(envelope((4, "cm"), (8, "cm"), (12, "cm")), boxed(noisy, 80, 120))
    )
    assert judged.verdict == Verdict.PASS


def test_the_longest_edge_is_held_against_the_largest_extent() -> None:
    judged = checked(
        requirements.judge(envelope((40, "mm"), (120, "mm"), (80, "mm")), boxed(40, 80, 120))
    )
    assert judged.verdict == Verdict.PASS
    assert [(c.measure, c.limit) for c in judged.comparisons] == [
        ("sorted_extent:largest", UNITS.Quantity(120, "mm")),
        ("sorted_extent:middle", UNITS.Quantity(80, "mm")),
        ("sorted_extent:smallest", UNITS.Quantity(40, "mm")),
    ]


def test_a_box_too_large_on_its_own_axes_is_unknown_because_a_rotated_part_may_fit() -> None:
    judged = checked(
        requirements.judge(envelope((40, "mm"), (120, "mm"), (80, "mm")), boxed(40, 80, 121))
    )
    assert judged.verdict == Verdict.UNKNOWN
    assert [c.verdict for c in judged.comparisons] == [
        Verdict.UNKNOWN,
        Verdict.PASS,
        Verdict.PASS,
    ]
    assert "rotated" in judged.reason


def test_an_unknown_density_leaves_a_mass_limit_unknown_not_failed() -> None:
    results = suite(result("mass", Verdict.UNKNOWN, volume=(1.0, "mm^3")))
    judged = checked(requirements.judge(max_mass(150), results))
    assert judged.verdict == Verdict.UNKNOWN
    assert [c.verdict for c in judged.comparisons] == [Verdict.UNKNOWN]


def test_a_failed_closed_solid_fails_its_requirement_and_leaves_mass_and_envelope_unknown() -> None:
    results = suite(result("closed_solid", Verdict.FAIL))
    solid = requirement({"kind": "closed_solid"})
    assert checked(requirements.judge(solid, results)).verdict == Verdict.FAIL
    assert checked(requirements.judge(solid, results)).comparisons == ()
    assert checked(requirements.judge(max_mass(150), results)).verdict == Verdict.UNKNOWN
    box = envelope((1, "mm"), (1, "mm"), (1, "mm"))
    assert checked(requirements.judge(box, results)).verdict == Verdict.UNKNOWN


def test_a_check_that_passed_without_the_named_measure_is_unknown() -> None:
    results = suite(result("mass", Verdict.PASS, volume=(1.0, "mm^3")))
    assert checked(requirements.judge(max_mass(150), results)).verdict == Verdict.UNKNOWN


def test_an_unchecked_requirement_is_unverified_with_no_verdict() -> None:
    given = requirement({"kind": "unchecked", "statement": "holds a 2 kg shelf"})
    assert requirements.judge(given, suite()) == Unverified(
        requirement_id=given.id, statement="holds a 2 kg shelf"
    )


def test_the_basis_keeps_the_confirmed_order_and_lists_the_unverified_ids() -> None:
    shelf = requirement({"kind": "unchecked", "statement": "holds a shelf"}, "a" * 16)
    look = requirement({"kind": "unchecked", "statement": "looks friendly"}, "b" * 16)
    light = max_mass(150)
    basis = requirements.assess_requirements(BRIEF, "d" * 64, (shelf, light, look), weighing(0.1))
    assert isinstance(basis, AgainstBrief)
    assert [r.requirement_id for r in basis.requirements] == [shelf.id, light.id, look.id]
    assert basis.unverified_requirements == (shelf.id, look.id)
    assert (basis.brief_id, basis.decision_sha256) == (BRIEF, "d" * 64)


@pytest.mark.parametrize(
    ("given", "results"),
    [
        (max_mass(150), weighing(0.12)),
        (max_mass(150), weighing(0.2)),
        (max_mass(150), suite(result("mass", Verdict.UNKNOWN))),
        (requirement({"kind": "closed_solid"}), suite(result("closed_solid", Verdict.PASS))),
        (requirement({"kind": "closed_solid"}), suite(result("closed_solid", Verdict.FAIL))),
        (envelope((1, "mm"), (2, "mm"), (3, "mm")), boxed(1, 2, 3)),
        (envelope((1, "mm"), (2, "mm"), (3, "mm")), boxed(1, 2, 4)),
    ],
)
def test_a_reason_holds_no_digit_so_every_number_on_a_card_is_a_traced_quantity(
    given: Requirement, results: tuple[CheckResult, ...]
) -> None:
    assert re.search(r"\d", checked(requirements.judge(given, results)).reason) is None


LOAD: dict[str, Any] = {
    "support": {"kind": "holes", "count": 2, "diameter": quantity(5.5, "mm")},
    "load": {
        "kind": "far_end",
        "force": quantity(49, "N"),
        "direction": {"kind": "across", "axis": "hole_axis"},
    },
}
FEA = SPEC["fea"]


def safety(factor: float) -> Requirement:
    return requirement({"kind": "min_safety_factor", "load": LOAD, "factor": factor})


def deflection(mm: float) -> Requirement:
    return requirement({"kind": "max_deflection", "load": LOAD, "deflection": quantity(mm, "mm")})


def solved(instance: str, factor: float = 3.0, mm: float = 1.0) -> CheckResult:
    found = result(
        "fea", Verdict.PASS, safety_factor=(factor, "dimensionless"), max_displacement=(mm, "mm")
    )
    return found.model_copy(update={"instance": instance})


def test_the_page_says_the_load_case_in_words() -> None:
    assert describe(safety(2)) == (
        "Safety factor against yield at least 2 with 49 N at the end farthest from the "
        "supports, in the worst direction across the hole axis; held by fixing the bores of "
        "exactly 2 holes of 5.5 mm"
    )
    assert describe(deflection(2)).startswith("Deflects at most 2 mm with 49 N at the end")


@pytest.mark.parametrize(
    ("factor", "verdict"),
    [(2.0, Verdict.PASS), (3.2, Verdict.UNKNOWN), (2.9, Verdict.UNKNOWN), (3.4, Verdict.FAIL)],
)
def test_a_safety_factor_within_the_stated_error_of_the_limit_is_unknown(
    factor: float, verdict: Verdict
) -> None:
    given = safety(factor)
    load_id = requirements.instance(given.target)
    judged = checked(requirements.judge(given, (*suite(), solved(load_id, factor=3.0))))
    assert (judged.check_id, judged.verdict) == ("fea", verdict)


@pytest.mark.parametrize(
    ("limit_mm", "verdict"),
    [(1.06, Verdict.PASS), (1.04, Verdict.UNKNOWN), (0.96, Verdict.UNKNOWN), (0.94, Verdict.FAIL)],
)
def test_a_deflection_is_judged_with_the_stated_five_percent(
    limit_mm: float, verdict: Verdict
) -> None:
    given = deflection(limit_mm)
    load_id = requirements.instance(given.target)
    judged = checked(requirements.judge(given, (*suite(), solved(load_id, mm=1.0))))
    assert judged.verdict == verdict


def test_a_requirement_reads_only_the_fea_result_for_its_own_load_case() -> None:
    given = safety(2)
    load_id = requirements.instance(given.target)
    results = (*suite(), solved("other", factor=1.0), solved(load_id, factor=3.0))
    assert checked(requirements.judge(given, results)).verdict == Verdict.PASS
    with pytest.raises(requirements.NoDecidingResult, match=f"for load case {load_id}"):
        requirements.judge(given, (*suite(), solved("other")))


def test_a_requirement_whose_fea_job_is_still_running_is_waiting() -> None:
    given = safety(2)
    pending = PendingCheck(
        check_id="fea",
        formula=FEA.formula,
        sources=FEA.sources,
        version=FEA.version,
        instance=requirements.instance(given.target),
    )
    assert requirements.judge(given, (*suite(), pending)) == Waiting(
        requirement_id=given.id, statement=describe(given), check_id="fea"
    )


RAIL = "part-" + "a" * 16


def clearance(kind: str, mm: float, part: str = RAIL) -> Requirement:
    return requirement({"kind": kind, "part": part, "clearance": quantity(mm, "mm")})


def fitted(mm: float, verdict: Verdict = Verdict.PASS, part: str = RAIL) -> CheckResult:
    found = result("fit", verdict, overlap_volume=(0.0, "mm^3"), min_clearance=(mm, "mm"))
    return found.model_copy(update={"instance": part})


@pytest.mark.parametrize(
    ("given", "measured", "verdict"),
    [
        (clearance("min_clearance", 0.2), 0.5, Verdict.PASS),
        (clearance("min_clearance", 0.2), 0.2, Verdict.PASS),
        (clearance("min_clearance", 0.2), 0.1, Verdict.FAIL),
        (clearance("max_clearance", 0.5), 0.5, Verdict.PASS),
        (clearance("max_clearance", 0.5), 40.0, Verdict.FAIL),
    ],
)
def test_a_clearance_is_held_against_the_fit_result_for_its_own_part(
    given: Requirement, measured: float, verdict: Verdict
) -> None:
    results = (*suite(), fitted(99.0, part="part-" + "b" * 16), fitted(measured))
    judged = checked(requirements.judge(given, results))
    assert (judged.check_id, judged.verdict) == ("fit", verdict)


def test_a_clearance_on_a_part_with_no_fit_result_is_unknown_not_an_error() -> None:
    given = clearance("min_clearance", 0.2)
    judged = checked(requirements.judge(given, (*suite(), fitted(0.5, part="part-" + "b" * 16))))
    assert (judged.verdict, judged.reason) == (
        Verdict.UNKNOWN,
        "The context part is not confirmed, so the fit check did not measure against it.",
    )
    assert [one.verdict for one in judged.comparisons] == [Verdict.UNKNOWN]


@pytest.mark.parametrize("kind", ["min_clearance", "max_clearance"])
def test_an_overlap_fails_any_clearance_on_that_part(kind: str) -> None:
    overlapping = fitted(0.0, Verdict.FAIL)
    judged = checked(requirements.judge(clearance(kind, 0.5), (*suite(), overlapping)))
    assert (judged.verdict, judged.reason) == (Verdict.FAIL, requirements.OVERLAPS)


def test_the_scorecard_names_a_context_part_by_its_name() -> None:
    results = (*suite(), fitted(0.3))
    judged = checked(requirements.judge(clearance("min_clearance", 0.2), results, {RAIL: "Rail"}))
    assert judged.statement == "At least 0.2 mm gap to Rail"


def test_the_page_names_the_part_and_the_clearance() -> None:
    assert (
        describe(clearance("min_clearance", 0.2)) == f"At least 0.2 mm clear of context part {RAIL}"
    )
    assert (
        describe(clearance("max_clearance", 0.5)) == f"At most 0.5 mm clear of context part {RAIL}"
    )


def test_demand_reads_the_load_of_every_target_it_is_given_assumed_ones_included() -> None:
    confirmed, assumed_load = safety(2).target, deflection(1).target
    asked = requirements.demand([confirmed, max_mass(150).target, assumed_load], {})
    assert set(asked.loads) == {requirements.instance(confirmed)}
