import re
from typing import Any

import pytest
from pydantic import TypeAdapter

from cad.briefs.model import BriefId, BriefSpan, Requirement, RequirementId, Target
from cad.checks.report import SPECS, unknown_for_all
from cad.checks.result import CheckResult, Measure, Verdict
from cad.scorecard import requirements
from cad.scorecard.model import AgainstBrief, Checked, Unverified
from cad.tables.materials import UNITS

TARGET = TypeAdapter[Target](Target)
SPEC = {spec.id: spec for spec in SPECS}
BRIEF = BriefId("1" * 16)


def requirement(raw: dict[str, Any], rid: str = "0" * 16) -> Requirement:
    return Requirement(
        id=RequirementId(rid),
        brief_id=BRIEF,
        target=TARGET.validate_python(raw),
        origin=BriefSpan(start=0, end=1),
    )


def quantity(magnitude: float, unit: str) -> dict[str, Any]:
    return {"magnitude": magnitude, "unit": unit}


def max_mass(magnitude: float, unit: str = "g") -> Requirement:
    return requirement({"kind": "max_mass", "mass": quantity(magnitude, unit)})


def min_mass(magnitude: float, unit: str = "g") -> Requirement:
    return requirement({"kind": "min_mass", "mass": quantity(magnitude, unit)})


def envelope(*edges: tuple[float, str]) -> Requirement:
    return requirement({"kind": "envelope", "edges": [quantity(m, u) for m, u in edges]})


def result(check_id: str, verdict: Verdict, **measured: tuple[float, str]) -> CheckResult:
    spec = SPEC[check_id]
    return CheckResult(
        check_id=check_id,
        verdict=verdict,
        measured=tuple(
            Measure(name=name.replace("__", ":"), value=UNITS.Quantity(magnitude, unit))
            for name, (magnitude, unit) in measured.items()
        ),
        formula=spec.formula,
        reason="r",
        sources=spec.sources,
        version=spec.version,
    )


def suite(*replacing: CheckResult) -> tuple[CheckResult, ...]:
    given = {one.check_id: one for one in replacing}
    return tuple(given.get(one.check_id, one) for one in unknown_for_all("not run"))


def weighing(kg: float) -> tuple[CheckResult, ...]:
    return suite(result("mass", Verdict.PASS, volume=(1.0, "mm^3"), mass=(kg, "kg")))


def boxed(smallest: float, middle: float, largest: float) -> tuple[CheckResult, ...]:
    return suite(
        result(
            "extents",
            Verdict.PASS,
            sorted_extent__smallest=(smallest, "mm"),
            sorted_extent__middle=(middle, "mm"),
            sorted_extent__largest=(largest, "mm"),
        )
    )


def checked(judged: Checked | Unverified) -> Checked:
    assert isinstance(judged, Checked)
    return judged


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
