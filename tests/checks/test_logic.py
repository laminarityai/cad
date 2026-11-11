import base64
import json
import math
from dataclasses import dataclass

import pytest

from cad.checks.container import closed_solid, interference
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import EdgeUses, Shape, Unreadable, VolumeProps
from cad.checks.container.runner import run
from cad.checks.container.suite import CHECKS
from cad.checks.container.wire import (
    FindingWire,
    ResultWire,
    ValueUnknown,
    ValueWire,
)
from tests.support.check_fakes import (
    KNOWN,
    REPORT_CAP,
    UNREADABLE_BREP,
    FakeKernel,
    FakeShape,
    NoFem,
    request,
)

UNKNOWN: ValueUnknown = {"kind": "unknown", "reason": "no material with key 'x'"}
INPUTS = Inputs(frozenset(Input), {Input.DENSITY: KNOWN})


def subject(kernel: FakeKernel) -> Subject:
    return Subject(kernel, NoFem(), FakeShape(), INPUTS, {})


def unreadable() -> Subject:
    return Subject(FakeKernel(), NoFem(), Unreadable("not a BREP"), INPUTS, {})


def checked(
    kernel: FakeKernel, density: ValueWire = KNOWN, brep: bytes = b"brep"
) -> dict[str, ResultWire]:
    return by_id(run(request(density), brep, kernel, REPORT_CAP)["results"])


def measured(found: FindingWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


@pytest.mark.parametrize(
    ("solids", "valid", "uses", "verdict"),
    [
        pytest.param(1, True, EdgeUses(0, 0), "pass", id="one-closed-valid-solid"),
        pytest.param(0, True, EdgeUses(2, 0), "fail", id="a-shell-has-no-solid"),
        pytest.param(2, True, EdgeUses(0, 0), "fail", id="two-solids"),
        pytest.param(1, False, EdgeUses(0, 0), "fail", id="invalid"),
        pytest.param(1, True, EdgeUses(4, 0), "fail", id="one-solid-and-a-loose-face"),
        pytest.param(1, True, EdgeUses(0, 1), "fail", id="an-edge-of-three-faces"),
    ],
)
def test_closed_solid_passes_only_on_one_valid_solid_with_no_free_or_over_used_edge(
    solids: int, valid: bool, uses: EdgeUses, verdict: str
) -> None:
    found = closed_solid.run(subject(FakeKernel(solid_count=solids, valid=valid, uses=uses)))
    assert found["verdict"] == verdict, found["reason"]


def test_closed_solid_fails_one_solid_beside_a_closed_shell() -> None:
    found = closed_solid.run(subject(FakeKernel(outside=1)))
    assert found["verdict"] == "fail"
    assert measured(found)["shapes_outside_solids"] == 1


def test_closed_solid_reason_names_every_failing_term() -> None:
    kernel = FakeKernel(solid_count=0, valid=False, uses=EdgeUses(2, 1), outside=1)
    found = closed_solid.run(subject(kernel))
    assert found["reason"] == (
        "found 0 solids; exactly 1 is required; 1 shells, faces, edges or vertices lie outside "
        "any solid; BRepCheck_Analyzer calls the shape invalid; 2 edges are used by one face; "
        "1 edges are used by more than two faces"
    )
    assert measured(found) == {
        "solids": 0,
        "shapes_outside_solids": 1,
        "free_edges": 2,
        "over_used_edges": 1,
        "valid": 0,
        "inside_out_solids": 0,
    }


def test_closed_solid_fails_an_unreadable_brep_and_says_why() -> None:
    found = closed_solid.run(unreadable())
    assert (found["verdict"], found["reason"]) == ("fail", "the BREP could not be read: not a BREP")


def test_interference_reports_every_interfering_pair_not_the_first() -> None:
    kernel = FakeKernel(solid_count=3, commons={(0, 1): 5.0, (1, 2): 7.0})
    found = interference.run(subject(kernel))
    assert found["verdict"] == "fail"
    assert measured(found) == {
        "bodies": 3,
        "interfering_pairs": 2,
        "max_common_volume": 7.0,
        "common_volume:0-1": 5.0,
        "common_volume:1-2": 7.0,
    }
    assert found["reason"] == "solids 0 and 1 share 5 mm^3; solids 1 and 2 share 7 mm^3"


@pytest.mark.parametrize(
    ("common", "verdict"), [(0.001, "pass"), (0.0011, "fail"), (0.0, "pass"), (125.0, "fail")]
)
def test_interference_threshold_is_inclusive_at_a_thousandth_of_a_cubic_millimetre(
    common: float, verdict: str
) -> None:
    found = interference.run(subject(FakeKernel(solid_count=2, commons={(0, 1): common})))
    assert found["verdict"] == verdict


def test_interference_of_one_solid_passes_with_one_body() -> None:
    found = interference.run(subject(FakeKernel(solid_count=1)))
    assert (found["verdict"], measured(found)["bodies"]) == ("pass", 1)


def test_interference_cannot_pass_a_shape_with_no_solid_or_an_undone_boolean() -> None:
    assert interference.run(subject(FakeKernel(solid_count=0)))["verdict"] == "unknown"
    undone = interference.run(subject(FakeKernel(solid_count=2, commons={(0, 1): None})))
    assert (undone["verdict"], undone["reason"]) == (
        "unknown",
        "solids 0 and 1 could not be intersected",
    )
    assert interference.run(unreadable())["verdict"] == "unknown"


def test_interference_cannot_pass_a_pair_whose_common_volume_is_not_a_number() -> None:
    found = interference.run(subject(FakeKernel(solid_count=2, commons={(0, 1): math.nan})))
    assert (found["verdict"], found["reason"]) == (
        "unknown",
        "solids 0 and 1 could not be intersected",
    )


def test_interference_names_an_undone_pair_beside_a_real_overlap() -> None:
    kernel = FakeKernel(solid_count=3, commons={(0, 1): 5.0, (0, 2): None})
    found = interference.run(subject(kernel))
    assert found["verdict"] == "fail"
    assert found["reason"].endswith("solids 0 and 2 could not be intersected")


def test_mass_multiplies_the_volume_by_the_density_it_was_given() -> None:
    found = checked(FakeKernel(props=VolumeProps(2000.0, (1.0, 2.0, 3.0))))["mass"]
    assert found["verdict"] == "pass"
    assert measured(found) == {
        "volume": 2000.0,
        "center_of_mass:x": 1.0,
        "center_of_mass:y": 2.0,
        "center_of_mass:z": 3.0,
        "density": 1.24e-6,
        "mass": 2000.0 * 1.24e-6,
    }


def test_mass_never_guesses_a_density() -> None:
    found = checked(FakeKernel(), UNKNOWN)["mass"]
    assert (found["verdict"], found["reason"]) == ("unknown", UNKNOWN["reason"])
    assert sorted(measured(found)) == [
        "center_of_mass:x",
        "center_of_mass:y",
        "center_of_mass:z",
        "volume",
    ]


@pytest.mark.parametrize(
    ("volume", "closed", "mass"),
    [
        (0.0, "fail", "unknown"),
        (-5.0, "fail", "unknown"),
        (math.nan, "fail", "unknown"),
        (math.inf, "pass", "fail"),
    ],
)
def test_no_check_passes_a_volume_that_is_not_positive_and_finite(
    volume: float, closed: str, mass: str
) -> None:
    results = checked(FakeKernel(props=VolumeProps(volume, (0.0, 0.0, 0.0))))
    assert (results["closed_solid"]["verdict"], results["mass"]["verdict"]) == (closed, mass)


@pytest.mark.parametrize(
    "kernel",
    [
        pytest.param(FakeKernel(solid_count=0, uses=EdgeUses(2, 0)), id="a-shell-has-no-solid"),
        pytest.param(FakeKernel(solid_count=2, commons={(0, 1): 125.0}), id="overlapping-solids"),
        pytest.param(FakeKernel(valid=False), id="invalid"),
        pytest.param(FakeKernel(uses=EdgeUses(4, 0)), id="a-loose-face"),
        pytest.param(FakeKernel(outside=1), id="a-closed-shell-beside-the-solid"),
    ],
)
def test_mass_is_unknown_with_no_number_on_a_shape_closed_solid_does_not_pass(
    kernel: FakeKernel,
) -> None:
    results = checked(kernel)
    found = results["mass"]
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert results["closed_solid"]["reason"] in found["reason"]


def test_mass_of_an_unreadable_brep_is_unknown_never_pass() -> None:
    assert checked(FakeKernel(), brep=UNREADABLE_BREP)["mass"]["verdict"] == "unknown"


@pytest.mark.parametrize(
    "kernel",
    [
        pytest.param(FakeKernel(solid_count=0), id="no-solid"),
        pytest.param(FakeKernel(solid_count=2), id="two-solids"),
        pytest.param(FakeKernel(valid=False), id="invalid"),
        pytest.param(FakeKernel(uses=EdgeUses(4, 0)), id="a-loose-face"),
        pytest.param(FakeKernel(outside=1), id="a-closed-shell-beside-the-solid"),
    ],
)
def test_extents_is_unknown_with_no_number_on_a_shape_closed_solid_does_not_pass(
    kernel: FakeKernel,
) -> None:
    results = checked(kernel)
    found = results["extents"]
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert results["closed_solid"]["reason"] in found["reason"]


def test_extents_reports_each_axis_and_the_same_sizes_sorted() -> None:
    found = checked(FakeKernel(box=(30.0, 10.0, 20.0)))["extents"]
    sizes = {one["name"]: one["magnitude"] for one in found["measured"]}
    assert found["verdict"] == "pass"
    assert sizes == {
        "extent:x": 30.0,
        "extent:y": 10.0,
        "extent:z": 20.0,
        "sorted_extent:smallest": 10.0,
        "sorted_extent:middle": 20.0,
        "sorted_extent:largest": 30.0,
    }
    assert {one["unit"] for one in found["measured"]} == {"mm"}


@pytest.mark.parametrize("box", [None, (1.0, math.inf, 3.0), (math.nan, 1.0, 1.0)])
def test_extents_cannot_pass_a_shape_with_no_finite_bounding_box(
    box: tuple[float, float, float] | None,
) -> None:
    found = checked(FakeKernel(box=box))["extents"]
    assert (found["verdict"], found["measured"]) == ("unknown", [])


def test_extents_of_an_unreadable_brep_is_unknown_never_pass() -> None:
    assert checked(FakeKernel(), brep=UNREADABLE_BREP)["extents"]["verdict"] == "unknown"


def by_id(results: list[ResultWire]) -> dict[str, ResultWire]:
    return {result["id"]: result for result in results}


def test_a_check_that_raises_becomes_unknown_and_the_others_still_run() -> None:
    report = run(request(), b"brep", FakeKernel(invalid_raises=True), REPORT_CAP)
    results = by_id(report["results"])
    assert results["closed_solid"]["verdict"] == "unknown"
    assert (
        results["closed_solid"]["reason"] == "closed_solid raised RuntimeError: BRepCheck exploded"
    )
    assert (results["interference"]["verdict"], results["mass"]["verdict"]) == ("pass", "unknown")
    assert results["extents"]["verdict"] == "unknown"


@dataclass(slots=True)
class ValidityRaisesOnceKernel(FakeKernel):
    raised: bool = False

    def is_valid(self, shape: Shape) -> bool:
        if not self.raised:
            self.raised = True
            raise RuntimeError("BRepCheck exploded")
        return self.valid


def test_a_check_that_requires_closed_solid_reads_its_reported_verdict_not_a_rerun() -> None:
    results = checked(ValidityRaisesOnceKernel())
    assert results["closed_solid"]["verdict"] == "unknown"
    for check_id in ("mass", "extents"):
        assert (results[check_id]["verdict"], results[check_id]["measured"]) == ("unknown", [])


def test_every_check_runs_after_the_checks_whose_verdicts_it_reads() -> None:
    for index, check in enumerate(CHECKS):
        earlier = {done.ID for done in CHECKS[:index]}
        assert {required.ID for required in check.REQUIRES} <= earlier, check.ID


def test_the_report_lists_every_check_in_suite_order_with_the_step_of_the_measured_shape() -> None:
    report = run(request(), b"brep", FakeKernel(), REPORT_CAP)
    assert [result["id"] for result in report["results"]] == [
        "closed_solid",
        "interference",
        "mass",
        "extents",
        "holes",
    ]
    step = report["step"]
    assert step["kind"] == "written"
    assert base64.b64decode(step["base64"]) == b"STEP bytes"


def test_an_unreadable_brep_still_reports_every_quick_check_and_no_step() -> None:
    report = run(request(), UNREADABLE_BREP, FakeKernel(), REPORT_CAP)
    verdicts = {result["id"]: result["verdict"] for result in report["results"]}
    assert verdicts == {
        "closed_solid": "fail",
        "interference": "unknown",
        "mass": "unknown",
        "extents": "unknown",
        "holes": "unknown",
    }
    assert report["step"] == {
        "kind": "missing",
        "reason": "no STEP was derived, because the BREP could not be read",
    }


def test_a_step_that_cannot_be_written_leaves_the_checks_standing() -> None:
    report = run(request(), b"brep", FakeKernel(step_raises=True), REPORT_CAP)
    assert report["step"] == {
        "kind": "missing",
        "reason": "the STEP writer raised RuntimeError: no STEP",
    }
    assert {result["verdict"] for result in report["results"]} == {"pass"}


def test_a_step_too_large_for_the_report_is_left_out_and_the_checks_stand() -> None:
    cap = 64 * 1024
    report = run(request(), b"brep", FakeKernel(step=b"x" * cap), cap)
    assert {result["verdict"] for result in report["results"]} == {"pass"}
    assert report["step"]["kind"] == "missing"
    assert report["step"]["reason"].startswith("the STEP is 65536 bytes, over the ")
    assert len(json.dumps(report).encode()) <= cap


def test_a_step_near_the_room_left_is_sent_only_when_the_report_still_fits() -> None:
    cap = 64 * 1024
    kinds: set[str] = set()
    for size in range(cap * 3 // 4 - 3000, cap * 3 // 4 + 4):
        report = run(request(), b"brep", FakeKernel(step=b"x" * size), cap)
        assert len(json.dumps(report).encode()) <= cap, size
        kinds.add(report["step"]["kind"])
    assert kinds == {"written", "missing"}
