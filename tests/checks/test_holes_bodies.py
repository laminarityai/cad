import pytest

from cad.checks.container import closed_solid, holes
from cad.checks.container.check import BodyPart, Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import ocp_kernel
from cad.checks.container.wire import FindingWire, ResultWire
from tests.support.check_fakes import NoFem
from tests.support.solids import box, compound, cut, rod, through_hole

KERNEL = ocp_kernel()
INPUTS = Inputs(frozenset[Input](), {})
PASSED: dict[str, ResultWire] = {
    closed_solid.ID: {"id": closed_solid.ID, "verdict": "pass", "measured": [], "reason": ""}
}
PLATE = cut(box(60, 20, 5), through_hole(5, 10, 10), through_hole(8, 50, 10))
GEAR = cut(box(20, 20, 5, at=(0, 40, 0)), through_hole(3, 10, 50))
BODIES = (BodyPart("plate", (0,), INPUTS), BodyPart("gear", (1,), INPUTS))


def measured(found: FindingWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


def test_each_body_s_holes_are_read_from_its_own_solids_beside_the_whole_result() -> None:
    shape = compound(PLATE, GEAR)
    found = measured(holes.run(Subject(KERNEL, NoFem(), shape, INPUTS, PASSED, bodies=BODIES)))
    assert found["hole_count"] == 3
    assert [found[f"hole_diameter:{at}"] for at in range(3)] == pytest.approx([3, 5, 8])
    assert found["hole_count:plate"] == 2
    assert [found["hole_diameter:plate:0"], found["hole_diameter:plate:1"]] == pytest.approx([5, 8])
    assert found["hole_count:gear"] == 1
    assert found["hole_diameter:gear:0"] == pytest.approx(3)
    assert found["unclassified_openings:gear"] == 0


def test_a_hole_through_two_stacked_bodies_is_one_hole_of_the_whole_and_one_of_each_body() -> None:
    bore = through_hole(5.5, 10, 10, depth=10)
    plate = cut(box(20, 20, 5), bore)
    spacer = cut(box(20, 20, 5, at=(0, 0, 5)), bore)
    stacked = (BodyPart("plate", (0,), INPUTS), BodyPart("spacer", (1,), INPUTS))
    subject = Subject(KERNEL, NoFem(), compound(plate, spacer), INPUTS, PASSED, bodies=stacked)
    found = holes.run(subject)
    assert found["verdict"] == "pass"
    counts = measured(found)
    assert (counts["hole_count"], counts["hole_count:plate"], counts["hole_count:spacer"]) == (
        1,
        1,
        1,
    )


def test_two_separate_holes_of_two_bodies_on_one_axis_count_as_one_hole_of_the_whole() -> None:
    plate = cut(box(20, 20, 5), through_hole(5.5, 10, 10))
    apart = cut(box(20, 20, 5, at=(0, 0, 55)), rod(2.75, 7, (10, 10, 54)))
    subject = Subject(KERNEL, NoFem(), compound(plate, apart), INPUTS, PASSED, bodies=BODIES)
    counts = measured(holes.run(subject))
    assert (counts["hole_count"], counts["hole_count:plate"], counts["hole_count:gear"]) == (
        1,
        1,
        1,
    )
