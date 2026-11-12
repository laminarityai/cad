import math

import pytest

from cad.checks.container import anchors
from cad.checks.container.anchors import resolve
from cad.checks.container.elastic import Face, region_faces
from cad.checks.container.features import geometry
from cad.checks.container.mesher import TetMesh
from cad.checks.container.regions import Candidate, FarFrom, Region, Resolved, Unresolved
from cad.checks.container.terms import of_wire
from cad.checks.container.vectors import Point, add, scale
from tests.support.anchors import FLAT_END, KERNEL, case
from tests.support.solids import Solid, apply, box, turn_and_move, turned

LENGTH, WIDTH, THICK = 200.0, 100.0, 5.0
WIDE = box(LENGTH, WIDTH, THICK)
MOVE = turn_and_move()
TOL = 1e-6


def six_node_triangles(
    origin: Point, u: Point, v: Point, cells: tuple[int, int]
) -> list[list[Point]]:
    n, m = cells

    def at(i: int, j: int) -> Point:
        return add(origin, add(scale(u, i / (2 * n)), scale(v, j / (2 * m))))

    triangles: list[list[Point]] = []
    for i in range(0, 2 * n, 2):
        for j in range(0, 2 * m, 2):
            a, b, c, d = (i, j), (i + 2, j), (i + 2, j + 2), (i, j + 2)
            for p, q, r in ((a, b, c), (a, c, d)):
                corners = [at(*p), at(*q), at(*r)]
                mids = [
                    at((x[0] + y[0]) // 2, (x[1] + y[1]) // 2) for x, y in ((p, q), (q, r), (r, p))
                ]
                triangles.append(corners + mids)
    return triangles


def boundary_and_far_end(
    length: float, width: float, thick: float
) -> tuple[TetMesh, tuple[Face, ...]]:
    x, y, z = (length, 0.0, 0.0), (0.0, width, 0.0), (0.0, 0.0, thick)
    origin = (0.0, 0.0, 0.0)
    far = six_node_triangles(x, y, z, (4, 1))
    sides = [
        six_node_triangles(origin, z, y, (1, 4)),
        six_node_triangles(origin, x, z, (8, 1)),
        six_node_triangles(y, z, x, (1, 8)),
        six_node_triangles(origin, y, x, (4, 8)),
        six_node_triangles(z, x, y, (8, 4)),
    ]
    triangles = far + [t for side in sides for t in side]
    nodes = tuple(point for triangle in triangles for point in triangle)
    faces = tuple(tuple(range(6 * k, 6 * k + 6)) for k in range(len(triangles)))
    return TetMesh(nodes, (), faces), faces[: len(far)]


def clamped_at(solid: Solid, root: Point) -> Candidate:
    found = resolve(of_wire(case(FLAT_END)), geometry(KERNEL, solid))
    assert isinstance(found, Resolved), found
    (candidate,) = (c for c in found.candidates if math.dist(c.support.centroid, root) <= TOL)
    return candidate


def band_of(solid: Solid, root: Point) -> FarFrom:
    """The band the far end falls back to when no flat face qualifies."""
    (line,) = must_lines(anchors.far_from(clamped_at(solid, root).support, KERNEL.inertia(solid)))
    return line


def must_lines(found: tuple[FarFrom, ...] | Unresolved) -> tuple[FarFrom, ...]:
    assert not isinstance(found, Unresolved), found
    return found


def moved(mesh: TetMesh) -> TetMesh:
    return TetMesh(tuple(apply(MOVE, node) for node in mesh.nodes), mesh.tets, mesh.faces)


MESH, END = boundary_and_far_end(LENGTH, WIDTH, THICK)
ROOT = (0.0, WIDTH / 2, THICK / 2)
TIP_CENTRE = (LENGTH, WIDTH / 2, THICK / 2)


@pytest.mark.parametrize("rule", ["whole face", "band"])
def test_the_far_end_of_a_wide_plate_is_its_whole_end_face_centre_included(rule: str) -> None:
    far = clamped_at(WIDE, ROOT).load if rule == "whole face" else band_of(WIDE, ROOT)
    assert isinstance(far, Region if rule == "whole face" else FarFrom)
    selected = region_faces(MESH, far, TOL)
    assert not isinstance(selected, Unresolved), selected
    assert selected == END
    assert any(math.dist(MESH.nodes[i], TIP_CENTRE) <= TOL for face in selected for i in face)


@pytest.mark.parametrize("rule", ["whole face", "band"])
def test_a_turned_and_moved_plate_selects_the_same_end_faces(rule: str) -> None:
    solid, root = turned(WIDE, MOVE), apply(MOVE, ROOT)
    far = clamped_at(solid, root).load if rule == "whole face" else band_of(solid, root)
    assert region_faces(moved(MESH), far, TOL) == END
