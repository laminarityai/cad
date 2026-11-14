from pathlib import Path

import pytest

from cad.sandbox.bodies import Body
from cad.sandbox.outcome import Built, NoResult
from cad.variants.store import build_variant

pytestmark = pytest.mark.docker

GEARS_ON_A_PLATE = """
from build123d import *
plate = Box(80, 40, 4)
plate.label, plate.color = "plate", Color("black")
teeth = [Pos(x, 0, 6) * Cylinder(8, 6) for x in (-20, 20)]
gears = Compound(children=teeth, label="gear")
gears.color = Color("gray")
result = Compound(children=[plate, gears])
"""


def outcome_of(code: str, root: Path) -> Built | NoResult:
    built = build_variant(code, root)
    assert isinstance(built.outcome, Built | NoResult), built.output
    return built.outcome


def test_each_solid_takes_the_label_of_its_nearest_labelled_node(tmp_path: Path) -> None:
    outcome = outcome_of(GEARS_ON_A_PLATE, tmp_path)
    assert isinstance(outcome, Built)
    assert outcome.bodies == (Body(name="plate", solids=(0,)), Body(name="gear", solids=(1, 2)))


def test_a_colour_on_a_labelled_node_names_its_area_as_its_body_is_named(tmp_path: Path) -> None:
    outcome = outcome_of(GEARS_ON_A_PLATE, tmp_path)
    assert isinstance(outcome, Built)
    assert {area.name: area.colour for area in outcome.areas} == {
        "plate": "#000000",
        "gear": "#808080",
    }


def test_a_moved_result_keeps_its_body_names(tmp_path: Path) -> None:
    outcome = outcome_of(GEARS_ON_A_PLATE + "result = Pos(0, 0, 10) * result\n", tmp_path)
    assert isinstance(outcome, Built)
    assert [body.name for body in outcome.bodies] == ["plate", "gear"]


def test_a_labelled_single_solid_stays_one_unnamed_body(tmp_path: Path) -> None:
    code = 'from build123d import *\nresult = Box(10, 10, 10)\nresult.label = "block"\n'
    outcome = outcome_of(code, tmp_path)
    assert isinstance(outcome, Built)
    assert outcome.bodies == ()


def test_two_solids_apart_with_no_label_refuse_the_build(tmp_path: Path) -> None:
    code = "from build123d import *\nresult = Box(80, 40, 4) + Pos(0, 0, 30) * Cylinder(8, 6)\n"
    outcome = outcome_of(code, tmp_path)
    assert isinstance(outcome, NoResult)
    assert "2 of the 2 solids of `result` have no label" in outcome.reason


def test_a_fuse_gives_every_solid_the_left_shape_s_label(tmp_path: Path) -> None:
    code = (
        "from build123d import *\n"
        "plate = Box(80, 40, 4)\n"
        'plate.label = "plate"\n'
        "result = plate + Pos(0, 0, 30) * Cylinder(8, 6)\n"
    )
    outcome = outcome_of(code, tmp_path)
    assert isinstance(outcome, Built)
    assert outcome.bodies == (Body(name="plate", solids=(0, 1)),)
