import re
from pathlib import Path

import pytest

from cad.geometry import job
from cad.geometry.model import Tessellated
from cad.operations.guidance import COLOUR_EVERY_BUILD
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Area, Built
from cad.variants.entry import open_entry
from cad.variants.store import build_variant

pytestmark = pytest.mark.docker

BLOCK = """
from build123d import *
with BuildPart() as block:
    Box(40, 30, 10)
    fillet(block.edges().filter_by(Axis.Z), 3)
    Hole(4)
result = block.part
"""


def built(code: str, root: Path) -> Built:
    result = build_variant(code, root)
    assert isinstance(result.outcome, Built), result.output
    return result.outcome


def test_a_build_that_sets_no_colour_has_no_areas(tmp_path: Path) -> None:
    assert built(BLOCK, tmp_path) == Built()


def test_the_colour_and_label_on_the_part_colour_every_face(tmp_path: Path) -> None:
    code = BLOCK + 'result.color = Color("gray")\nresult.label = "aluminium body"\n'
    outcome = built(code, tmp_path)
    faces = tuple(range(len(outcome.areas[0].faces)))
    assert outcome.areas == (Area(name="aluminium body", colour="#808080", faces=faces),)
    assert len(faces) > 6


def test_faces_listed_in_areas_are_numbered_as_the_mesh_numbers_them(tmp_path: Path) -> None:
    code = BLOCK + (
        'result.color = Color("gray")\nresult.label = "body"\n'
        "top = result.faces().sort_by(Axis.Z)[-1]\n"
        'areas = [Compound([top], label="grip pad", color=Color(0.1, 0.1, 0.1))]\n'
    )
    result = build_variant(code, tmp_path)
    assert isinstance(result.outcome, Built), result.output
    body, pad = result.outcome.areas
    assert (body.name, pad.name, pad.colour) == ("body", "grip pad", "#1a1a1a")
    held = open_entry(tmp_path, result.variant_id, image_tag(BUILD))
    mesh = job.tessellate(held.brep, held.brep_sha256).read
    assert isinstance(mesh, Tessellated)
    facing_up = [
        number
        for number, face in enumerate(mesh.topology["faces"])
        if face["normal"] is not None and face["normal"][2] > 0.99 and face["center"][2] > 4.9
    ]
    assert list(pad.faces) == facing_up
    assert sorted(body.faces + pad.faces) == list(range(len(mesh.topology["faces"])))


def test_the_areas_example_every_client_is_told_keeps_the_area(tmp_path: Path) -> None:
    example = re.search(r"areas = \[.*?\)\)\]", COLOUR_EVERY_BUILD)
    assert example is not None
    outcome = built(BLOCK + 'result.color = Color("gray")\n' + example.group(0) + "\n", tmp_path)
    kept = {area.name: area for area in outcome.areas}
    assert set(kept) == {"unnamed", "holes"}
    assert kept["holes"].colour == "#333333"
    assert kept["holes"].faces


def test_each_child_of_a_compound_keeps_its_own_colour(tmp_path: Path) -> None:
    code = """
from build123d import *
gear = Cylinder(10, 4)
gear.color, gear.label = Color("gray"), "gear"
plate = Pos(0, 0, -6) * Box(40, 40, 2)
plate.color, plate.label = Color("black"), "plate"
result = Compound(children=[gear, plate])
"""
    gear, plate = built(code, tmp_path).areas
    assert (gear.name, gear.colour, gear.faces) == ("gear", "#808080", (0, 1, 2))
    assert (plate.name, plate.colour, plate.faces) == (
        "plate",
        "#000000",
        tuple(range(3, 9)),
    )


def test_a_compound_made_from_a_list_keeps_the_colours_of_its_parts(tmp_path: Path) -> None:
    """A walk's agent wrote this: Compound([...]) holds the parts' faces but drops their labels."""
    code = """
from build123d import *
gear = Cylinder(10, 4)
gear.color, gear.label = Color("gray"), "steel gear"
plate = Pos(0, 0, -6) * Box(40, 40, 2)
plate.color, plate.label = Color("black"), "carbon plate"
result = Compound([gear, plate], label="whole")
"""
    gear, plate = built(code, tmp_path).areas
    assert (gear.name, gear.faces) == ("steel gear", (0, 1, 2))
    assert (plate.name, plate.faces) == ("carbon plate", tuple(range(3, 9)))


def test_a_colour_list_that_cannot_be_read_keeps_the_build(tmp_path: Path) -> None:
    code = BLOCK + (
        "class Odd:\n    color = (1, 0, 0)\n"
        "    def faces(self):\n        raise ValueError('no faces')\n"
        "areas = [Odd()]\n"
    )
    outcome = built(code, tmp_path)
    assert outcome.areas == ()
    assert outcome.areas_dropped == "the colours could not be read: ValueError: no faces"


def test_a_name_over_the_limit_drops_the_colours_and_keeps_the_build(tmp_path: Path) -> None:
    code = BLOCK + f'result.color = Color("red")\nresult.label = "{"x" * 61}"\n'
    outcome = built(code, tmp_path)
    assert outcome.areas == ()
    assert outcome.areas_dropped is not None
    assert outcome.areas_dropped.startswith("the colours were dropped: 0.name")
