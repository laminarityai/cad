"""The min_wall check's verdicts, on a fake kernel whose rays read what the test says."""

from typing import Literal

import pytest

from cad.checks.container import closed_solid, min_wall
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import Across, Glancing, Lost, Unreadable
from cad.checks.container.wire import FindingWire, ResultWire
from tests.support.check_fakes import FakeKernel, FakeShape, FakeWalls, NoFem

INPUTS = Inputs(frozenset[Input](), {})
type Verdict = Literal["pass", "fail", "unknown"]


def reported(verdict: Verdict) -> dict[str, ResultWire]:
    found: ResultWire = {"id": closed_solid.ID, "verdict": verdict, "measured": [], "reason": "r"}
    return {closed_solid.ID: found}


def checked(walls: FakeWalls, closed: Verdict = "pass") -> FindingWire:
    subject = Subject(FakeKernel(wall=walls), NoFem(), FakeShape(), INPUTS, reported(closed))
    return min_wall.run(subject)


def test_a_wall_every_ray_reads_as_2_mm_measures_2_mm() -> None:
    found = checked(FakeWalls(Across(2.0)))
    assert found["verdict"] == "pass"
    assert found["measured"] == [{"name": "min_wall", "magnitude": 2.0, "unit": "mm"}]


def test_a_ray_that_never_comes_out_makes_it_unknown_with_no_value() -> None:
    found = checked(FakeWalls(Lost("a ray into the material never came out of it")))
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert "never came out" in found["reason"]


def test_rays_that_only_come_out_at_corners_make_it_unknown() -> None:
    found = checked(FakeWalls(Glancing()))
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert found["reason"] == "no ray from any face crossed a wall"


def test_a_point_off_every_face_makes_it_unknown() -> None:
    assert checked(FakeWalls(None))["verdict"] == "unknown"


def test_a_part_with_too_many_faces_is_unknown_not_a_guess() -> None:
    too_many = min_wall.GRID_POINTS // min_wall.FIRST_SAMPLES**2 + 1
    found = checked(FakeWalls(Across(2.0), count=too_many))
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert "more than 10000 faces" in found["reason"]


def test_running_out_of_rays_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(min_wall, "MAX_RAYS", 100)
    found = checked(FakeWalls(Across(2.0)))
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert "more than 100 rays" in found["reason"]


def test_running_out_of_time_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(min_wall, "MAX_SECONDS", -1.0)
    found = checked(FakeWalls(Across(2.0)))
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert "longer than -1 seconds" in found["reason"]


@pytest.mark.parametrize("closed", ["fail", "unknown"])
def test_without_one_closed_solid_there_is_no_value(closed: Verdict) -> None:
    found = checked(FakeWalls(Across(2.0)), closed)
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert found["reason"].startswith(f"closed_solid is {closed}")


def test_an_unreadable_shape_is_unknown() -> None:
    subject = Subject(FakeKernel(), NoFem(), Unreadable("bad"), INPUTS, reported("pass"))
    assert min_wall.run(subject)["verdict"] == "unknown"
