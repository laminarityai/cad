import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

import pytest

from cad.geometry.exports import lane, store
from cad.geometry.exports.lane import Exports
from cad.geometry.exports.model import Exported
from cad.geometry.lane import Tessellations
from cad.geometry.model import Tessellated
from cad.sandbox import image
from cad.sandbox.bodies import Body
from cad.sandbox.outcome import Built
from cad.variants import entry
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


@dataclass(frozen=True)
class Made:
    held: entry.Entry
    mesh: Tessellated
    step: str
    threemf: bytes


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Made:
    root = tmp_path_factory.mktemp("gears")
    built = build_variant(GEARS_ON_A_PLATE, root / "variants")
    assert isinstance(built.outcome, Built), built.output
    held = entry.open_entry(root / "variants", built.variant_id, image.image_tag(image.BUILD))
    mesh = Tessellations().read(root / "geometry", held, wait_seconds=60)
    assert isinstance(mesh, Tessellated), mesh
    read = Exports().read(root / "geometry", held, wait_seconds=120)
    assert isinstance(read, Exported), read
    key = lane.key_of(held)
    step = store.read_file(root / "geometry", key, "step")
    threemf = store.read_file(root / "geometry", key, "3mf")
    assert step is not None
    assert threemf is not None
    return Made(held, mesh, step.decode(), threemf)


def test_the_mesh_counts_the_faces_of_each_solid(made: Made) -> None:
    assert made.held.bodies == (Body(name="plate", solids=(0,)), Body(name="gear", solids=(1, 2)))
    assert made.mesh.solid_faces == (6, 3, 3)


def test_the_step_holds_one_product_per_body_under_its_name(made: Made) -> None:
    assert re.findall(r"PRODUCT\('([^']*)'", made.step) == ["result", "plate", "gear"]
    assert len(re.findall(r"MANIFOLD_SOLID_BREP", made.step)) == 3


def test_the_step_colours_each_body_s_faces(made: Made) -> None:
    assert "DRAUGHTING_PRE_DEFINED_COLOUR('black')" in made.step
    assert "COLOUR_RGB('',0.501960785193,0.501960785193,0.501960785193)" in made.step


def test_the_3mf_builds_one_named_coloured_object_per_body(made: Made) -> None:
    with zipfile.ZipFile(BytesIO(made.threemf)) as archive:
        model = ElementTree.fromstring(archive.read("3D/3dmodel.model"))
    ns = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    shown = [one.get("objectid") for one in model.iter(f"{ns}item")]
    objects = {one.get("id"): one for one in model.iter(f"{ns}object")}
    colour = {
        one.get("id"): one.find(f"{ns}base").get("displaycolor")  # type: ignore[union-attr]
        for one in model.iter(f"{ns}basematerials")
    }
    assert [(objects[i].get("name"), colour[objects[i].get("pid")]) for i in shown] == [
        ("plate", "#000000FF"),
        ("gear", "#808080FF"),
    ]
