from collections.abc import Callable
from pathlib import Path

import pytest

from cad.checks.result import CheckRun, Verdict

pytestmark = pytest.mark.docker

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
NONE = "dimensionless"
STAR_IMPORT = "from build123d import *\n"

PLATE_SHELL = PLATE + "from build123d import Shell\nresult = Shell(result.faces()[:-1])\n"
PLATE_TWO = (
    PLATE
    + "from build123d import Compound, Pos\n"
    + 'result = Compound(children=[result, Pos(200, 0, 0) * result], label="plate")\n'
)
LOOSE_FACE = (
    STAR_IMPORT
    + "box = Box(10, 10, 10)\n"
    + "face = Pos(30, 0, 0) * Box(10, 10, 10).faces()[0]\n"
    + "result = Compound([box, face])\n"
)
SOLID_AND_CLOSED_SHELL = (
    STAR_IMPORT
    + "shell = Shell(Pos(5, 5, 5) * Box(10, 10, 10).faces())\n"
    + "result = Compound([Box(10, 10, 10), shell])\n"
)
OVERLAPPING_BOXES = (
    STAR_IMPORT
    + 'result = Compound(children=[Box(10, 10, 10), Pos(5, 5, 5) * Box(10, 10, 10)], label="box")\n'
)
OPEN_SHELL = STAR_IMPORT + "result = Shell(Box(10, 10, 10).faces()[:-1])\n"
INSIDE_OUT_BOX = STAR_IMPORT + "result = Solid(Box(10, 10, 10).wrapped.Reversed())\n"
INSIDE_OUT_IN_GOOD_BOX = (
    STAR_IMPORT
    + "inner = Solid(Box(10, 10, 10).wrapped.Reversed())\n"
    + 'result = Compound(children=[Box(20, 20, 20), inner], label="box")\n'
)

type Check = Callable[..., CheckRun]


def count(run: CheckRun, name: str) -> float:
    return run.result("closed_solid").number(name, NONE)


def test_plate_shell_fails_closed_solid_with_zero_solids(check: Check) -> None:
    closed = check(PLATE_SHELL).result("closed_solid")
    assert closed.verdict == Verdict.FAIL
    assert closed.number("solids", NONE) == 0
    assert closed.number("free_edges", NONE) == 2
    assert "found 0 solids" in closed.reason


def test_two_plates_of_one_body_pass_closed_solid_and_interference(check: Check) -> None:
    run = check(PLATE_TWO)
    closed = run.result("closed_solid")
    assert closed.verdict == Verdict.PASS, closed.reason
    assert count(run, "solids") == 2
    assert closed.reason.startswith("2 valid solids in 1 body")
    interference = run.result("interference")
    assert interference.verdict == Verdict.PASS, interference.reason
    assert interference.number("solids", NONE) == 2
    assert interference.number("max_common_volume", "mm^3") == pytest.approx(0, abs=1e-9)


def test_a_solid_with_a_loose_face_is_caught_by_the_edge_test_alone(check: Check) -> None:
    run = check(LOOSE_FACE)
    closed = run.result("closed_solid")
    assert closed.verdict == Verdict.FAIL
    assert count(run, "solids") == 1
    assert count(run, "free_edges") == 4
    assert "4 edges are used by one face" in closed.reason


def test_a_solid_beside_a_closed_shell_fails_closed_solid(check: Check) -> None:
    run = check(SOLID_AND_CLOSED_SHELL)
    closed = run.result("closed_solid")
    assert closed.verdict == Verdict.FAIL, closed.reason
    assert (count(run, "solids"), count(run, "free_edges")) == (1, 0)
    assert count(run, "shapes_outside_solids") == 1


def test_two_overlapping_boxes_of_one_body_fail_interference_and_are_not_weighed(
    check: Check,
) -> None:
    run = check(OVERLAPPING_BOXES)
    interference, mass = run.result("interference"), run.result("mass")
    assert interference.verdict == Verdict.FAIL
    assert interference.number("common_volume:0-1", "mm^3") == pytest.approx(125, rel=1e-6)
    assert interference.number("interfering_pairs", NONE) == 1
    assert "solids 0 (box) and 1 (box) share 125 mm^3" in interference.reason
    assert mass.verdict == Verdict.UNKNOWN, mass.reason
    assert mass.measured == ()
    assert interference.reason in mass.reason


def test_an_inside_out_box_fails_closed_solid(check: Check) -> None:
    run = check(INSIDE_OUT_BOX)
    closed = run.result("closed_solid")
    assert closed.verdict == Verdict.FAIL, closed.reason
    assert (count(run, "solids"), count(run, "inside_out_solids")) == (1, 1)
    assert "1 solids have a volume of 0 or less" in closed.reason


def test_an_inside_out_box_in_a_good_box_is_counted_per_solid(check: Check) -> None:
    run = check(INSIDE_OUT_IN_GOOD_BOX)
    assert run.result("closed_solid").verdict == Verdict.FAIL
    assert (count(run, "solids"), count(run, "inside_out_solids")) == (2, 1)


@pytest.mark.parametrize(
    "shape", ["Sphere(10)", "Cylinder(5, 10)", "Torus(20, 5)"], ids=["sphere", "cylinder", "torus"]
)
def test_a_seam_or_a_degenerated_edge_is_not_a_free_edge(shape: str, check: Check) -> None:
    run = check(f"{STAR_IMPORT}result = {shape}\n")
    closed = run.result("closed_solid")
    assert closed.verdict == Verdict.PASS, closed.reason
    assert (count(run, "free_edges"), count(run, "over_used_edges")) == (0, 0)


@pytest.mark.parametrize(
    "code",
    [
        PLATE_SHELL,
        OPEN_SHELL,
        LOOSE_FACE,
        SOLID_AND_CLOSED_SHELL,
        INSIDE_OUT_BOX,
    ],
    ids=[
        "plate_shell",
        "open_shell",
        "loose_face",
        "and_shell",
        "inside_out",
    ],
)
def test_mass_is_unknown_with_no_number_when_closed_solid_does_not_pass(
    code: str, check: Check
) -> None:
    run = check(code)
    closed, mass = run.result("closed_solid"), run.result("mass")
    assert closed.verdict == Verdict.FAIL
    assert mass.verdict == Verdict.UNKNOWN, mass.reason
    assert mass.measured == ()
    assert closed.reason in mass.reason
