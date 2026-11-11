import pytest

from cad.checks.container import fea
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.wire import FindingWire, LoadCaseWire, ResultWire, ValueWire
from tests.support.check_fakes import FakeKernel, FakeShape, NoFem

CASE: LoadCaseWire = {
    "support": {"kind": "flat_end"},
    "load": {"kind": "far_end", "force_n": 10.0, "direction": {"kind": "any"}},
}
PASSED: dict[str, ResultWire] = {
    one: {"id": one, "verdict": "pass", "measured": [], "reason": "ok"}
    for one in ("closed_solid", "interference")
}


def known(magnitude: float) -> ValueWire:
    return {"kind": "known", "magnitude": magnitude}


def solved(size_mm: float, displacement: float, von_mises: float) -> fea.Solved:
    return fea.Solved(size_mm, fea.Peaks(displacement, von_mises, 2 * von_mises))


def by_name(found: FindingWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


def test_safety_factor_is_yield_over_the_fine_mesh_peak_stress() -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.01, 12.5), 50.0, 200, [], False)
    assert found["verdict"] == "pass"
    assert by_name(found)["safety_factor"] == pytest.approx(4.0)
    assert by_name(found)["max_displacement"] == 1.01
    assert by_name(found)["support_max_von_mises"] == 25


@pytest.mark.parametrize("clamped_face", [True, False])
def test_the_clamped_face_note_is_on_the_result_only_when_a_face_is_clamped(
    clamped_face: bool,
) -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.0, 10), 50.0, 200, [], clamped_face)
    assert found["verdict"] == "pass"
    assert (fea.CLAMPED_FACE_NOTE in found["reason"]) is clamped_face


def test_no_yield_strength_drops_only_the_safety_factor() -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.0, 10), None, 200, [], False)
    assert found["verdict"] == "pass"
    assert "safety_factor" not in by_name(found)
    assert "max_displacement" in by_name(found)


def test_meshes_that_disagree_by_more_than_three_percent_are_unknown() -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.1, 10), 50.0, 200, [], False)
    assert found["verdict"] == "unknown"
    assert "differ by 9.1% in max_displacement, over the 3% limit" in found["reason"]
    assert "safety_factor" not in by_name(found)


def test_a_displacement_over_five_percent_of_the_extent_is_outside_linear_theory() -> None:
    found = fea.judged(solved(2, 11.0, 10), solved(1.3, 11.0, 10), 50.0, 200, [], False)
    assert found["verdict"] == "unknown"
    assert "a linear analysis does not hold" in found["reason"]


@pytest.mark.parametrize("missing", [Input.ELASTIC_MODULUS, Input.POISSON_RATIO])
def test_an_unknown_stiffness_is_unknown_not_a_failure(missing: Input) -> None:
    values: dict[str, ValueWire] = {
        Input.ELASTIC_MODULUS: known(3500),
        Input.POISSON_RATIO: known(0.36),
        Input.YIELD_STRENGTH: known(51),
        missing: {"kind": "unknown", "reason": f"the table has no {missing}"},
    }
    inputs = Inputs(fea.TAKES, values, (CASE,))
    found = fea.run(Subject(FakeKernel(), NoFem(), FakeShape(), inputs, PASSED))
    assert found["verdict"] == "unknown"
    assert found["reason"] == f"the table has no {missing}"


def test_fea_needs_one_closed_solid() -> None:
    failed: ResultWire = {**PASSED["closed_solid"], "verdict": "fail"}
    reported = {**PASSED, "closed_solid": failed}
    inputs = Inputs(fea.TAKES, {}, (CASE,))
    found = fea.run(Subject(FakeKernel(), NoFem(), FakeShape(), inputs, reported))
    assert found["verdict"] == "unknown"
    assert found["reason"].startswith("closed_solid is fail, so there is no one solid to load")
