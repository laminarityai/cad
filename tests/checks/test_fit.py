import pytest

from cad.checks.container.kernel import Shape, ocp_kernel
from cad.checks.container.runner import run
from cad.checks.container.wire import RequestWire, ResultWire
from tests.support.check_fakes import REPORT_CAP
from tests.support.solids import box, box_face, brep_bytes, compound, cut

KERNEL = ocp_kernel()
RAIL = box(300, 18, 12)


def clip(sunk: float = 0.0) -> Shape:
    outer = box(20, 25, 15.5, at=(140, -3.5, -sunk))
    channel = box(22, 19, 13.5, at=(139, -0.5, -1 - sunk))
    return cut(outer, channel)


def fitted(variant: Shape, context: Shape | None = RAIL) -> ResultWire:
    tail = b"" if context is None else brep_bytes(context)
    request: RequestWire = {
        "checks": ["fit"],
        "values": {},
        "load_cases": [],
        "context_bytes": len(tail),
    }
    report = run(request, brep_bytes(variant) + tail, KERNEL, REPORT_CAP)
    assert [one["id"] for one in report["results"]] == ["interference", "fit"]
    return report["results"][1]


def measures(found: ResultWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


def test_a_clip_half_a_millimetre_clear_of_the_rail_passes_with_that_clearance() -> None:
    found = fitted(clip())
    assert found["verdict"] == "pass", found["reason"]
    assert measures(found) == {
        "overlap_volume": pytest.approx(0, abs=1e-9),
        "min_clearance": 0.5,
        "context_solids": 1,
        "variant_solids": 1,
    }


def test_a_clip_sunk_into_the_rail_fails_with_the_shared_volume_and_no_clearance() -> None:
    found = fitted(clip(sunk=0.8))
    assert found["verdict"] == "fail"
    assert measures(found)["overlap_volume"] == pytest.approx(0.3 * 18 * 20, rel=1e-6)
    assert measures(found)["min_clearance"] == 0


def test_a_cube_inside_the_context_overlaps_though_their_boundaries_are_apart() -> None:
    found = fitted(box(2, 2, 2, at=(4, 4, 4)), box(10, 10, 10))
    assert found["verdict"] == "fail"
    assert measures(found)["overlap_volume"] == pytest.approx(8, rel=1e-9)
    assert measures(found)["min_clearance"] == 0


def test_faces_that_touch_pass_with_no_clearance() -> None:
    found = fitted(box(10, 10, 10, at=(10, 0, 0)), box(10, 10, 10))
    assert found["verdict"] == "pass", found["reason"]
    assert measures(found)["min_clearance"] == 0


def test_the_clearance_of_two_variant_solids_is_the_nearer_one() -> None:
    variant = compound(box(5, 5, 5, at=(12, 0, 0)), box(5, 5, 5, at=(0, 0, 13)))
    found = fitted(variant, box(10, 10, 10))
    assert found["verdict"] == "pass", found["reason"]
    assert measures(found)["min_clearance"] == 2
    assert measures(found)["variant_solids"] == 2


def test_with_no_context_part_the_fit_is_unknown() -> None:
    found = fitted(clip(), context=None)
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert found["reason"] == "the host sent no context part to measure against"


def test_a_context_part_with_a_loose_face_is_not_measured() -> None:
    found = fitted(clip(), compound(RAIL, box_face(5, 5, 5)))
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert found["reason"].startswith("the context part has 1 shells, faces")


def test_a_variant_whose_own_solids_overlap_is_not_measured() -> None:
    variant = compound(box(10, 10, 10, at=(0, 30, 0)), box(10, 10, 10, at=(5, 30, 0)))
    found = fitted(variant)
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert found["reason"].startswith("interference is fail")
