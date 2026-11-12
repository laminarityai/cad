"""The holes measures a limit binds to keep their value when the part is turned, moved, or its
faces come in another order, as `cad.briefs.bindable` demands of every row."""

from typing import Any

import pytest

from cad.briefs.bindable import BINDABLE
from cad.briefs.model import amount
from cad.briefs.words import describe
from cad.checks.container import closed_solid, holes
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import Opening, Shape
from cad.checks.container.kernel.ocp_kernel import OcpKernel
from cad.checks.container.kernel.protocol import FaceInfo
from cad.checks.container.wire import FindingWire, ResultWire
from cad.checks.result import Verdict
from cad.scorecard import requirements
from cad.tables.materials import UNITS
from tests.support.check_fakes import NoFem
from tests.support.scorecard import checked, requirement, result
from tests.support.solids import Solid, box, cut, through_hole, turn_and_move, turned

HOLES_ROWS = sorted(measure for check, measure in BINDABLE if check == holes.ID)
INPUTS = Inputs(frozenset[Input](), {})
PASSED: dict[str, ResultWire] = {
    closed_solid.ID: {"id": closed_solid.ID, "verdict": "pass", "measured": [], "reason": ""}
}
MIXED = cut(
    box(60, 20, 5), through_hole(5.5, 10, 10), through_hole(8, 30, 10), through_hole(4.2, 50, 10)
)
TWO_M5 = cut(box(60, 20, 5), through_hole(5.5, 10, 10), through_hole(5.5, 50, 10))


class Reordered(OcpKernel):
    """The same kernel, listing faces and openings back to front."""

    def faces(self, shape: Shape) -> tuple[FaceInfo, ...]:
        return super().faces(shape)[::-1]

    def openings(self, shape: Shape) -> tuple[Opening, ...]:
        return super().openings(shape)[::-1]


def measured(solid: Solid, kernel: OcpKernel) -> dict[str, float]:
    found: FindingWire = holes.run(Subject(kernel, NoFem(), solid, INPUTS, PASSED))
    assert found["verdict"] == "pass", found["reason"]
    return {one["name"]: one["magnitude"] for one in found["measured"]}


def test_the_holes_check_reports_every_bindable_holes_measure() -> None:
    assert HOLES_ROWS == ["hole_count", "hole_diameter:0"]
    assert set(HOLES_ROWS) <= measured(MIXED, OcpKernel()).keys()


def test_the_narrowest_hole_is_hole_diameter_0() -> None:
    plain = measured(MIXED, OcpKernel())
    assert plain["hole_count"] == 3
    assert plain["hole_diameter:0"] == pytest.approx(4.2)


@pytest.mark.parametrize("measure", HOLES_ROWS)
def test_a_bindable_holes_measure_is_the_same_on_the_part_turned_moved_and_reordered(
    measure: str,
) -> None:
    plain = measured(MIXED, OcpKernel())[measure]
    assert measured(turned(MIXED, turn_and_move()), OcpKernel())[measure] == pytest.approx(plain)
    assert measured(MIXED, Reordered())[measure] == pytest.approx(plain)
    assert measured(turned(MIXED, turn_and_move()), Reordered())[measure] == pytest.approx(plain)


def holes_limit(measure: str, comparator: str, magnitude: float, unit: str) -> dict[str, Any]:
    return {
        "kind": "measure_limit",
        "check_id": holes.ID,
        "measure": measure,
        "comparator": comparator,
        "limit": {"magnitude": magnitude, "unit": unit},
    }


def judged(raw: dict[str, Any], solid: Solid) -> Verdict:
    values = measured(turned(solid, turn_and_move()), OcpKernel())
    units = {"hole_count": "dimensionless"}
    found = result(
        holes.ID,
        Verdict.PASS,
        **{
            name.replace(":", "__"): (value, units.get(name, "mm"))
            for name, value in values.items()
            if name in HOLES_ROWS
        },
    )
    return checked(requirements.judge(requirement(raw), (found,))).verdict


def test_no_hole_under_5_mm_passes_two_m5_holes_and_fails_a_4_2_mm_hole() -> None:
    no_hole_under_5 = holes_limit("hole_diameter:0", "at_least", 5, "mm")
    assert judged(no_hole_under_5, TWO_M5) == Verdict.PASS
    assert judged(no_hole_under_5, MIXED) == Verdict.FAIL


def test_at_most_two_holes_passes_two_and_fails_three() -> None:
    at_most_two = holes_limit("hole_count", "at_most", 2, "dimensionless")
    assert judged(at_most_two, TWO_M5) == Verdict.PASS
    assert judged(at_most_two, MIXED) == Verdict.FAIL


def test_a_hole_count_limit_reads_as_a_plain_number() -> None:
    at_most_two = requirement(holes_limit("hole_count", "at_most", 2, "dimensionless"))
    assert describe(at_most_two) == "The number of round holes in the part is at most 2"
    assert amount(UNITS.Quantity(2, "dimensionless")) == "2"
