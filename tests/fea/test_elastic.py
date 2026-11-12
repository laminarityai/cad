import math
import random

import pytest

from cad.checks.container.elastic import (
    Stress,
    contains,
    largest_eigenvalue,
    region_faces,
    spread,
    surfaces_of,
    von_mises,
    worst_displacement,
    worst_von_mises,
)
from cad.checks.container.mesher import TetMesh
from cad.checks.container.regions import Bore, FarFrom, Patch, Plane, Region, Unresolved
from cad.checks.container.vectors import Point

NODES = 20
SAMPLES = 20_000


def directions(k: int) -> list[list[float]]:
    rng = random.Random(k)
    found: list[list[float]] = []
    for _ in range(SAMPLES):
        a = [rng.gauss(0, 1) for _ in range(k)]
        length = math.sqrt(sum(x * x for x in a))
        found.append([x / length for x in a])
    return found


def mix(vectors: tuple[tuple[float, ...], ...], a: list[float]) -> list[float]:
    return [sum(w * v[c] for w, v in zip(a, vectors, strict=True)) for c in range(len(vectors[0]))]


def points(rng: random.Random) -> list[Point]:
    return [(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)) for _ in range(NODES)]


def stresses(rng: random.Random) -> list[Stress]:
    def one() -> Stress:
        a, b, c, d, e, f = (rng.uniform(-1, 1) for _ in range(6))
        return (a, b, c, d, e, f)

    return [one() for _ in range(NODES)]


def stress(values: list[float]) -> Stress:
    a, b, c, d, e, f = values
    return (a, b, c, d, e, f)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_the_worst_displacement_is_the_largest_over_sampled_directions(k: int) -> None:
    rng = random.Random(10 + k)
    fields = [points(rng) for _ in range(k)]
    worst = worst_displacement(fields)
    sampled = max(
        math.sqrt(sum(x * x for x in mix(per_load, a)))
        for a in directions(k)
        for per_load in zip(*fields, strict=True)
    )
    assert worst * (1 - 1e-3) <= sampled <= worst * (1 + 1e-12)


@pytest.mark.parametrize("k", [1, 2, 3])
def test_the_worst_von_mises_is_the_largest_over_sampled_directions(k: int) -> None:
    rng = random.Random(20 + k)
    fields = [stresses(rng) for _ in range(k)]
    worst = worst_von_mises(fields)
    sampled = max(
        von_mises(stress(mix(per_load, a)))
        for a in directions(k)
        for per_load in zip(*fields, strict=True)
    )
    assert worst * (1 - 1e-3) <= sampled <= worst * (1 + 1e-12)


def test_von_mises_of_uniaxial_and_pure_shear_stress() -> None:
    assert von_mises((10.0, 0.0, 0.0, 0.0, 0.0, 0.0)) == pytest.approx(10.0)
    assert von_mises((0.0, 0.0, 0.0, 10.0, 0.0, 0.0)) == pytest.approx(10 * math.sqrt(3))
    assert von_mises((5.0, 5.0, 5.0, 0.0, 0.0, 0.0)) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(
    ("matrix", "largest"),
    [
        (((4.0,),), 4.0),
        (((2.0, 1.0), (1.0, 2.0)), 3.0),
        (((3.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 3.0)), 3.0),
        (((2.0, -1.0, 0.0), (-1.0, 2.0, -1.0), (0.0, -1.0, 2.0)), 2 + math.sqrt(2)),
        (((1.0, 0.0, 0.0), (0.0, 5.0, 0.0), (0.0, 0.0, -2.0)), 5.0),
    ],
)
def test_the_largest_eigenvalue_in_closed_form(
    matrix: tuple[tuple[float, ...], ...], largest: float
) -> None:
    assert largest_eigenvalue(matrix) == pytest.approx(largest)


SQUARE = TetMesh(
    nodes=(
        (0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 0.0), (0.0, 2.0, 0.0),
        (1.0, 0.0, 0.0), (2.0, 1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 2.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, 0.0, 2.0), (0.0, 0.0, 1.0), (0.0, 1.0, 1.0),
    ),
    tets=(),
    faces=((0, 1, 2, 4, 5, 6), (0, 2, 3, 6, 7, 8), (0, 3, 9, 8, 11, 10)),
    surfaces=(0, 0, 1),
)  # fmt: skip
ORIGIN = (0.0, 0.0, 0.0)
HALF = math.sqrt(0.5)
FLOOR = Region((Plane((5.0, 5.0, 0.0), (0.0, 0.0, -1.0)),), (1.0, 1.0, 0.0), frozenset({0}))
WALL = Plane((0.0, 0.0, 0.0), (-1.0, 0.0, 0.0))


def test_a_region_takes_the_triangles_on_its_faces() -> None:
    assert region_faces(SQUARE, FLOOR, 1e-6) == SQUARE.faces[:2]
    assert (
        region_faces(SQUARE, Region((WALL,), (0.0, 1.0, 1.0), frozenset({1})), 1e-6)
        == (SQUARE.faces[2:])
    )


def test_a_region_takes_no_triangle_off_its_faces_even_one_lying_on_its_plane() -> None:
    split = TetMesh(SQUARE.nodes, (), SQUARE.faces, (0, 2, 1))
    assert region_faces(split, FLOOR, 1e-6) == SQUARE.faces[:1]


def test_a_chosen_face_whose_triangles_are_off_its_surface_is_unresolved() -> None:
    """The mesh and the kernel would then number the faces differently."""
    swapped = Region((WALL,), (0.0, 1.0, 1.0), frozenset({0}))
    found = region_faces(SQUARE, swapped, 1e-6)
    assert isinstance(found, Unresolved)
    assert "do not order the faces alike" in found.reason


def test_the_surfaces_of_triangles_are_the_kernel_faces_they_lie_on_lowest_first() -> None:
    assert surfaces_of(SQUARE, SQUARE.faces[:2]) == (0,)
    assert surfaces_of(SQUARE, SQUARE.faces[1:]) == (0, 1)
    assert surfaces_of(SQUARE, SQUARE.faces[2:]) == (1,)
    assert surfaces_of(SQUARE, ()) == ()


def test_far_from_takes_the_triangles_wholly_past_the_cutoff() -> None:
    assert (
        region_faces(SQUARE, FarFrom((1.0, 1.0, 50.0), (0.0, 0.0, -1.0)), 1e-6) == SQUARE.faces[:2]
    )


def test_an_anchor_no_whole_triangle_lies_on_is_unresolved() -> None:
    assert isinstance(region_faces(SQUARE, FarFrom(ORIGIN, (HALF, HALF, 0.0)), 1e-6), Unresolved)
    off = Region((Plane((0.0, 0.0, 9.0), (0.0, 0.0, 1.0)),), (0.0, 0.0, 9.0))
    assert isinstance(region_faces(SQUARE, off, 1e-6), Unresolved)


def test_spread_puts_the_whole_force_on_the_midside_nodes_by_area() -> None:
    loads = spread(SQUARE, SQUARE.faces[:2], (0.0, 0.0, -6.0))
    assert set(loads) == {4, 5, 6, 7, 8}
    assert sum(force[2] for force in loads.values()) == pytest.approx(-6.0)
    assert loads[6] == pytest.approx((0.0, 0.0, -2.0))
    assert loads[4] == pytest.approx((0.0, 0.0, -1.0))


@pytest.mark.parametrize(
    ("patch", "point", "inside"),
    [
        (Bore((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 5.0, 0.0, 8.0), (3.0, 4.0, 7.0), True),
        (Bore((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 5.0, 0.0, 8.0), (3.0, 4.1, 7.0), False),
        (Bore((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 5.0, 0.0, 6.0), (3.0, 4.0, 7.0), False),
        (WALL, (0.0, 7.0, -3.0), True),
        (WALL, (0.1, 7.0, -3.0), False),
    ],
)
def test_contains(patch: Patch, point: Point, inside: bool) -> None:
    assert contains(patch, point, 1e-6) is inside
