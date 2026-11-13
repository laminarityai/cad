import pytest

from cad.checks.container import fea
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.mesher import OverCap
from cad.checks.container.wire import FindingWire, LoadCaseWire, ResultWire, ValueWire, WhereWire
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
    peaks = fea.Peaks(displacement, von_mises, 2 * von_mises)
    return fea.Solved(size_mm, peaks, {"support": [0], "load": [1]})


def by_name(found: FindingWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


def test_safety_factor_is_yield_over_the_fine_mesh_peak_stress() -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.01, 12.5), 50.0, 200, [], False, None)
    assert found["verdict"] == "pass"
    assert by_name(found)["safety_factor"] == pytest.approx(4.0)
    assert by_name(found)["max_displacement"] == 1.01
    assert by_name(found)["support_max_von_mises"] == 25


@pytest.mark.parametrize(
    ("coarse_displacement", "fine_displacement", "verdict"),
    [(1.0, 1.0, "pass"), (1.0, 1.5, "unknown"), (11.0, 11.0, "unknown")],
)
def test_every_verdict_of_a_solved_load_case_carries_the_faces_of_the_fine_mesh(
    coarse_displacement: float, fine_displacement: float, verdict: str
) -> None:
    where: WhereWire = {"support": [4], "load": [2, 5]}
    fine = fea.Solved(1.3, fea.Peaks(fine_displacement, 10, 20), where)
    found = fea.judged(solved(2, coarse_displacement, 10), fine, 50.0, 200, [], False, None)
    assert found["verdict"] == verdict
    assert found.get("where") == where


@pytest.mark.parametrize("clamped_face", [True, False])
def test_the_clamped_face_note_is_on_the_result_only_when_a_face_is_clamped(
    clamped_face: bool,
) -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.0, 10), 50.0, 200, [], clamped_face, None)
    assert found["verdict"] == "pass"
    assert (fea.CLAMPED_FACE_NOTE in found["reason"]) is clamped_face


def test_no_yield_strength_drops_only_the_safety_factor() -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.0, 10), None, 200, [], False, None)
    assert found["verdict"] == "pass"
    assert "safety_factor" not in by_name(found)
    assert "max_displacement" in by_name(found)


def test_meshes_that_disagree_by_more_than_three_percent_are_unknown() -> None:
    found = fea.judged(solved(2, 1.0, 10), solved(1.3, 1.1, 10), 50.0, 200, [], False, None)
    assert found["verdict"] == "unknown"
    assert "differ by 9.1% in max_displacement, over the 3% limit" in found["reason"]
    assert "safety_factor" not in by_name(found)


def test_a_part_that_bends_over_five_percent_of_its_size_is_unknown_and_told_to_stiffen() -> None:
    found = fea.judged(solved(2, 11.0, 10), solved(1.3, 11.0, 10), 50.0, 200, [], False, None)
    assert found["verdict"] == "unknown"
    assert found["reason"].startswith(
        "the part bends 11 mm under this load, over 5% of its 200 mm size, which is too far for "
        "a linear analysis to give a verdict; make it stiffer where it bends"
    )


@pytest.mark.parametrize(("fine_displacement", "verdict"), [(1.0, "pass"), (1.1, "unknown")])
def test_a_floored_mesh_says_why_whatever_the_verdict(
    fine_displacement: float, verdict: str
) -> None:
    over = OverCap("the mesh at 2 mm has 900000 nodes, above the cap of 150000")
    found = fea.judged(
        solved(2, 1.0, 10), solved(1.3, fine_displacement, 10), 50.0, 200, [], False, over
    )
    assert found["verdict"] == verdict
    assert found["reason"].endswith(
        "both meshes keep every element at least half the coarse size, because the mesh at 2 mm "
        "has 900000 nodes, above the cap of 150000"
    )


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
