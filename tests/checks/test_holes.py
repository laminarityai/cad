import math

import pytest

from cad.checks.container import closed_solid, holes
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import Arc, Opening, Unreadable, ocp_kernel
from cad.checks.container.wire import FindingWire, ResultWire
from tests.support.check_fakes import FakeKernel, FakeShape, NoFem
from tests.support.solids import (
    Solid,
    box,
    cone,
    cut,
    fuse,
    hexagon_hole,
    rod,
    through_hole,
    turn_and_move,
    turned,
)

KERNEL = ocp_kernel()
INPUTS = Inputs(frozenset[Input](), {})
PASSED: dict[str, ResultWire] = {
    closed_solid.ID: {"id": closed_solid.ID, "verdict": "pass", "measured": [], "reason": ""}
}

PLATE = box(60, 20, 5)
TWO_HOLES = cut(PLATE, through_hole(5.5, 10, 10), through_hole(5.5, 50, 10))
MIXED = cut(PLATE, through_hole(5.5, 10, 10), through_hole(8, 30, 10), through_hole(4.2, 50, 10))
COUNTERBORED = cut(
    box(40, 20, 8),
    through_hole(5.5, 10, 10, depth=8),
    rod(5, 4, (10, 10, 5)),
    through_hole(5.5, 30, 10, depth=8),
)
COUNTERSUNK = cut(
    box(40, 20, 8), through_hole(5.5, 10, 10, depth=8), cone(5.5, 12, 3.25, (10, 10, 4.75))
)
BLIND = cut(PLATE, rod(2.75, 3, (10, 10, 2)))
BOSSED = fuse(TWO_HOLES, rod(4, 6, (30, 10, 5)))
SLOT = cut(
    PLATE,
    fuse(
        box(10, 5.5, 7, at=(25, 7.25, -1)), rod(2.75, 7, (25, 10, -1)), rod(2.75, 7, (35, 10, -1))
    ),
)
WINDOW = cut(PLATE, box(10, 6, 7, at=(25, 7, -1)))
HEXAGON = cut(PLATE, through_hole(5.5, 10, 10), hexagon_hole(8, 40, 10))
CONE_ONLY = cut(PLATE, cone(1, 6, 3, (30, 10, 2)))
SOLID_PLATE = PLATE


def run(solid: Solid) -> FindingWire:
    return holes.run(Subject(KERNEL, NoFem(), solid, INPUTS, PASSED))


def diameters(found: FindingWire) -> list[float]:
    named = [one for one in found["measured"] if one["name"].startswith("hole_diameter:")]
    return [one["magnitude"] for one in sorted(named, key=lambda one: one["name"])]


def count_of(found: FindingWire, name: str) -> float:
    return next(one["magnitude"] for one in found["measured"] if one["name"] == name)


def test_a_plate_with_two_holes_reports_both_diameters() -> None:
    found = run(TWO_HOLES)
    assert found["verdict"] == "pass", found["reason"]
    assert diameters(found) == pytest.approx([5.5, 5.5])
    assert count_of(found, "hole_count") == 2
    assert count_of(found, "unclassified_openings") == 0


def test_the_holes_are_listed_from_the_narrowest() -> None:
    assert diameters(run(MIXED)) == pytest.approx([4.2, 5.5, 8.0])


def test_a_counterbored_hole_is_one_hole_with_the_narrowest_diameter() -> None:
    found = run(COUNTERBORED)
    assert found["verdict"] == "pass", found["reason"]
    assert diameters(found) == pytest.approx([5.5, 5.5])


def test_a_countersunk_hole_reads_its_bore() -> None:
    found = run(COUNTERSUNK)
    assert found["verdict"] == "pass", found["reason"]
    assert diameters(found) == pytest.approx([5.5])


def test_a_blind_round_hole_is_a_hole() -> None:
    found = run(BLIND)
    assert found["verdict"] == "pass", found["reason"]
    assert diameters(found) == pytest.approx([5.5])


def test_a_part_with_no_hole_passes_with_none_measured() -> None:
    found = run(SOLID_PLATE)
    assert found["verdict"] == "pass", found["reason"]
    assert count_of(found, "hole_count") == 0
    assert diameters(found) == []


def test_a_boss_is_not_an_opening() -> None:
    found = run(BOSSED)
    assert found["verdict"] == "pass", found["reason"]
    assert diameters(found) == pytest.approx([5.5, 5.5])


@pytest.mark.parametrize(
    ("solid", "round_holes"),
    [
        pytest.param(SLOT, 0, id="slot"),
        pytest.param(WINDOW, 0, id="rectangular-window"),
        pytest.param(HEXAGON, 1, id="hexagon-beside-a-round-hole"),
        pytest.param(CONE_ONLY, 0, id="a-cone-no-cylinder-explains"),
    ],
)
def test_an_opening_that_is_not_a_round_hole_makes_the_result_unknown(
    solid: Solid, round_holes: int
) -> None:
    found = run(solid)
    assert found["verdict"] == "unknown"
    assert "openings that are not round holes" in found["reason"]
    assert count_of(found, "unclassified_openings") >= 1
    assert count_of(found, "hole_count") == round_holes


def test_the_same_part_turned_and_moved_reads_the_same_holes() -> None:
    found = run(turned(MIXED, turn_and_move()))
    assert found["verdict"] == "pass", found["reason"]
    assert diameters(found) == pytest.approx([4.2, 5.5, 8.0])


def test_an_unreadable_shape_is_unknown_with_no_measure() -> None:
    found = holes.run(Subject(FakeKernel(), NoFem(), Unreadable("not a BREP"), INPUTS, {}))
    assert (found["verdict"], found["measured"]) == ("unknown", [])


def test_a_part_that_is_not_one_closed_solid_is_not_measured_for_holes() -> None:
    failed: dict[str, ResultWire] = {
        closed_solid.ID: {"id": closed_solid.ID, "verdict": "fail", "measured": [], "reason": "two"}
    }
    found = holes.run(Subject(FakeKernel(), NoFem(), FakeShape(), INPUTS, failed))
    assert (found["verdict"], found["measured"]) == ("unknown", [])


def circle(radius: float, sweep: float = 2 * math.pi) -> Arc:
    return Arc((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), radius, sweep)


def test_two_half_circles_are_one_whole_circle() -> None:
    whole = Opening((circle(3, math.pi), circle(3, math.pi)), 0)
    assert holes.whole_circle(whole, 1e-4) is not None


def test_half_a_circle_and_a_line_are_not() -> None:
    assert holes.whole_circle(Opening((circle(3, math.pi), None), 0), 1e-4) is None
    assert holes.whole_circle(Opening((circle(3, math.pi),), 0), 1e-4) is None


def test_arcs_of_two_radii_are_not_one_circle() -> None:
    assert holes.whole_circle(Opening((circle(3, math.pi), circle(4, math.pi)), 0), 1e-4) is None
