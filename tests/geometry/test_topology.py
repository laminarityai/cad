from pathlib import Path

import pytest

from cad.geometry.lane import Tessellations
from cad.geometry.model import Tessellated
from cad.sandbox import image
from cad.sandbox.outcome import Built
from cad.variants import entry
from cad.variants.store import build_variant

PARTS = Path(__file__).parents[1] / "sandbox/parts"


@pytest.fixture(scope="module")
def plate(tmp_path_factory: pytest.TempPathFactory) -> Tessellated:
    root = tmp_path_factory.mktemp("plate")
    built = build_variant((PARTS / "plate.py").read_text(), root / "variants")
    assert built.outcome == Built(), built.output
    held = entry.open_entry(root / "variants", built.variant_id, image.image_tag(image.BUILD))
    read = Tessellations().read(root / "geometry", held, wait_seconds=60)
    assert isinstance(read, Tessellated), read
    return read


def test_topology_has_one_entry_per_face_and_edge_of_the_mesh(plate: Tessellated) -> None:
    mesh = plate.shapes["parts"][0]["shape"]
    assert len(plate.topology["faces"]) == len(mesh["face_types"]) == 6 + 4
    assert len(plate.topology["edges"]) == len(mesh["edge_types"])


def test_the_top_face_is_a_plane_that_faces_up(plate: Tessellated) -> None:
    top = [f for f in plate.topology["faces"] if f["normal"] == (0.0, 0.0, 1.0)]
    assert len(top) == 1
    assert top[0]["type"] == "PLANE"
    assert top[0]["center"][2] == 3.0
    assert top[0]["area"] == pytest.approx(100 * 50 - 4 * 3.14159265 * 2.55**2, abs=0.01)


def test_a_hole_is_a_cylinder_with_its_radius_and_axis(plate: Tessellated) -> None:
    holes = [f for f in plate.topology["faces"] if f["type"] == "CYLINDER"]
    assert len(holes) == 4
    for hole in holes:
        assert hole["radius"] == 2.55
        assert hole["axis"] is not None
        assert abs(hole["axis"][2]) == 1.0
        assert hole["normal"] is not None
        assert hole["normal"][2] == 0.0


def test_every_edge_of_a_closed_solid_bounds_two_faces_but_a_seam(plate: Tessellated) -> None:
    faces = plate.topology["faces"]
    seams = 0
    for index, edge in enumerate(plate.topology["edges"]):
        for face in edge["faces"]:
            assert index in faces[face]["edges"]
        if len(edge["faces"]) == 1:
            seams += 1
            assert faces[edge["faces"][0]]["type"] == "CYLINDER"
        else:
            assert len(edge["faces"]) == 2
    assert seams == 4


def test_edges_know_their_line_direction_and_circle_radius(plate: Tessellated) -> None:
    edges = plate.topology["edges"]
    circles = [e for e in edges if e["type"] == "CIRCLE"]
    assert circles
    assert {e["radius"] for e in circles} == {2.55}
    lines = [e for e in edges if e["type"] == "LINE"]
    assert all(e["direction"] is not None for e in lines)
    assert {e["length"] for e in lines} == {100.0, 50.0, 6.0}
