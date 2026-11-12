"""A wall limit the person states binds to the min_wall check's measure, which keeps its value when
the part is turned, moved, or its faces come in another order, as `cad.briefs.bindable` demands."""

from typing import Any

from cad.briefs.bindable import BINDABLE
from cad.briefs.words import describe
from cad.checks.container import closed_solid, min_wall
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel.ocp_kernel import OcpKernel
from cad.checks.container.wire import ResultWire
from cad.checks.result import Verdict
from cad.scorecard import requirements
from tests.support.check_fakes import NoFem
from tests.support.scorecard import checked, requirement, result
from tests.support.solids import Solid, box, cut, fuse, turn_and_move, turned

INPUTS = Inputs(frozenset[Input](), {})
PASSED: dict[str, ResultWire] = {
    closed_solid.ID: {"id": closed_solid.ID, "verdict": "pass", "measured": [], "reason": ""}
}


def shell(wall: float) -> Solid:
    return cut(box(40, 30, 20), box(40 - 2 * wall, 30 - 2 * wall, 20, (wall, wall, wall)))


RIB_0_8 = fuse(box(50, 30, 4), box(0.8, 30, 10, (20, 0, 4)))


def walls_at_least(magnitude: float) -> dict[str, Any]:
    return {
        "kind": "measure_limit",
        "check_id": min_wall.ID,
        "measure": "min_wall",
        "comparator": "at_least",
        "limit": {"magnitude": magnitude, "unit": "mm"},
    }


def judged(raw: dict[str, Any], solid: Solid) -> Verdict:
    subject = Subject(OcpKernel(), NoFem(), turned(solid, turn_and_move()), INPUTS, PASSED)
    found = min_wall.run(subject)
    assert found["verdict"] == "pass", found["reason"]
    [wall] = found["measured"]
    measured = result(min_wall.ID, Verdict.PASS, min_wall=(wall["magnitude"], "mm"))
    return checked(requirements.judge(requirement(raw), (measured,))).verdict


def test_min_wall_is_the_one_bindable_wall_measure() -> None:
    assert [key for key in BINDABLE if key[0] == min_wall.ID] == [("min_wall", "min_wall")]
    assert BINDABLE[("min_wall", "min_wall")].unit == "mm"


def test_walls_at_least_2_mm_pass_a_2_5_mm_shell_and_fail_a_1_5_mm_one() -> None:
    assert judged(walls_at_least(2), shell(2.5)) == Verdict.PASS
    assert judged(walls_at_least(2), shell(1.5)) == Verdict.FAIL


def test_no_wall_under_1_5_mm_passes_a_2_mm_shell_and_fails_a_0_8_mm_rib() -> None:
    assert judged(walls_at_least(1.5), shell(2)) == Verdict.PASS
    assert judged(walls_at_least(1.5), RIB_0_8) == Verdict.FAIL


def test_a_wall_exactly_at_the_limit_is_unknown_within_the_check_s_stated_error() -> None:
    assert judged(walls_at_least(2), shell(2)) == Verdict.UNKNOWN


def test_a_wall_limit_reads_in_the_person_s_words() -> None:
    assert describe(requirement(walls_at_least(2))) == (
        "The thickness of the part's thinnest wall is at least 2 mm"
    )
