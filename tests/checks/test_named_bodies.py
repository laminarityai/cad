from collections.abc import Sequence

import pytest

from cad.checks.container import fea
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import Across, VolumeProps
from cad.checks.container.wire import (
    BodyWire,
    FindingWire,
    LoadCaseWire,
    ResultWire,
    ValueWire,
)
from tests.support.check_fakes import (
    FakeKernel,
    FakeShape,
    FakeWalls,
    NoFem,
    body,
    request,
    run_report,
)

CARBON: ValueWire = {"kind": "known", "magnitude": 1.5e-6}
STEEL: ValueWire = {"kind": "known", "magnitude": 7.85e-6}
UNKNOWN: ValueWire = {"kind": "unknown", "reason": "the table lists no density for it"}
QUICK = ("closed_solid", "interference", "mass", "min_wall")
PLATE_AND_GEARS = (body("plate", (0,), CARBON), body("gear", (1, 2), STEEL))
SOLIDS = {
    0: VolumeProps(1000.0, (0.0, 0.0, 0.0)),
    1: VolumeProps(500.0, (10.0, 0.0, 0.0)),
    2: VolumeProps(500.0, (20.0, 0.0, 0.0)),
}


def checked(kernel: FakeKernel, bodies: Sequence[BodyWire]) -> dict[str, ResultWire]:
    report, _ = run_report(request(checks=QUICK, bodies=bodies), b"brep", kernel)
    return {one["id"]: one for one in report["results"]}


def measured(found: FindingWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


def test_closed_solid_passes_when_the_kernel_finds_each_solid_the_bodies_name() -> None:
    found = checked(FakeKernel(solid_count=3), PLATE_AND_GEARS)["closed_solid"]
    assert found["verdict"] == "pass"
    assert found["reason"] == "3 valid solids in 2 bodies, every edge shared by two faces"


def test_closed_solid_fails_a_solid_no_body_names() -> None:
    found = checked(FakeKernel(solid_count=4), PLATE_AND_GEARS)["closed_solid"]
    assert found["verdict"] == "fail"
    assert "found 4 solids; the 2 bodies name 3" in found["reason"]


def test_interference_fails_two_solids_of_one_body_and_names_the_body() -> None:
    kernel = FakeKernel(solid_count=3, commons={(1, 2): 5.0})
    found = checked(kernel, PLATE_AND_GEARS)["interference"]
    assert found["verdict"] == "fail"
    assert found["reason"] == "solids 1 (gear) and 2 (gear) share 5 mm^3"


def test_mass_weighs_each_body_at_its_own_density_and_sums_them() -> None:
    found = checked(FakeKernel(solid_count=3, solid_props=SOLIDS), PLATE_AND_GEARS)["mass"]
    plate, gear = 1000.0 * 1.5e-6, 1000.0 * 7.85e-6
    assert found["verdict"] == "pass"
    assert measured(found) == pytest.approx(
        {
            "volume": 2000.0,
            "volume:plate": 1000.0,
            "density:plate": 1.5e-6,
            "mass:plate": plate,
            "volume:gear": 1000.0,
            "density:gear": 7.85e-6,
            "mass:gear": gear,
            "mass": plate + gear,
            "center_of_mass:x": gear * 15.0 / (plate + gear),
            "center_of_mass:y": 0.0,
            "center_of_mass:z": 0.0,
        }
    )


def test_no_mass_is_measured_while_one_body_s_density_is_unknown() -> None:
    bodies = (body("plate", (0,), CARBON), body("gear", (1, 2), UNKNOWN))
    found = checked(FakeKernel(solid_count=3, solid_props=SOLIDS), bodies)["mass"]
    assert found["verdict"] == "unknown"
    assert found["reason"].startswith("no mass is measured while a density is unknown: gear")
    names = set(measured(found))
    assert {"mass", "center_of_mass:x"}.isdisjoint(names)
    assert {"mass:plate", "volume:gear", "volume"} <= names


def test_min_wall_reads_each_body_as_one_shape_and_names_the_thinnest() -> None:
    walls = {(0,): FakeWalls(Across(3.0)), (1, 2): FakeWalls(Across(1.2))}
    found = checked(FakeKernel(solid_count=3, body_walls=walls), PLATE_AND_GEARS)["min_wall"]
    assert found["verdict"] == "pass"
    assert measured(found) == pytest.approx(
        {"min_wall": 1.2, "min_wall:plate": 3.0, "min_wall:gear": 1.2}
    )
    assert ", in gear," in found["reason"]


def test_min_wall_is_unknown_when_one_body_crosses_no_wall() -> None:
    walls = {(0,): FakeWalls(Across(3.0)), (1, 2): FakeWalls(None)}
    found = checked(FakeKernel(solid_count=3, body_walls=walls), PLATE_AND_GEARS)["min_wall"]
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert found["reason"] == "no ray from any face of gear crossed a wall"


def test_stress_on_more_than_one_solid_is_unknown_until_one_body_can_be_solved_alone() -> None:
    case: LoadCaseWire = {
        "support": {"kind": "flat_end"},
        "load": {"kind": "far_end", "force_n": 10.0, "direction": {"kind": "any"}},
    }
    passed: dict[str, ResultWire] = {
        one: {"id": one, "verdict": "pass", "measured": [], "reason": "ok"}
        for one in ("closed_solid", "interference")
    }
    inputs = Inputs(fea.TAKES, {Input.DENSITY: STEEL}, (case,))
    found = fea.run(Subject(FakeKernel(solid_count=2), NoFem(), FakeShape(), inputs, passed))
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert found["reason"] == fea.ONE_BODY
