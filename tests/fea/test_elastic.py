import math
import random

import pytest

from cad.checks.container.elastic import (
    Cylinder,
    Patch,
    Plane,
    Region,
    Stress,
    contains,
    largest_eigenvalue,
    region_faces,
    spread,
    von_mises,
    worst_displacement,
    worst_von_mises,
)
from cad.checks.container.mesher import Point, TetMesh

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
)  # fmt: skip
FLOOR = Plane((5.0, 5.0, 0.0), (0.0, 0.0, -3.0))


def test_a_region_takes_only_the_triangles_with_every_node_inside() -> None:
    assert region_faces(SQUARE, FLOOR, 1e-6) == SQUARE.faces[:2]
    assert region_faces(SQUARE, Plane((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), 1e-6) == SQUARE.faces[2:]


def test_spread_puts_the_whole_force_on_the_midside_nodes_by_area() -> None:
    loads = spread(SQUARE, SQUARE.faces[:2], (0.0, 0.0, -6.0))
    assert set(loads) == {4, 5, 6, 7, 8}
    assert sum(force[2] for force in loads.values()) == pytest.approx(-6.0)
    assert loads[6] == pytest.approx((0.0, 0.0, -2.0))
    assert loads[4] == pytest.approx((0.0, 0.0, -1.0))


@pytest.mark.parametrize(
    ("region", "point", "inside"),
    [
        (Cylinder((0.0, 0.0, 0.0), (0.0, 0.0, 2.0), 5.0), (3.0, 4.0, 7.0), True),
        (Cylinder((0.0, 0.0, 0.0), (0.0, 0.0, 2.0), 5.0), (3.0, 4.1, 7.0), False),
        (Patch((0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 1.0), (0.6, 0.8, 1.0), True),
        (Patch((0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 1.0), (0.7, 0.8, 1.0), False),
        (Patch((0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 1.0), (0.0, 0.0, 1.1), False),
    ],
)
def test_contains(region: Region, point: Point, inside: bool) -> None:
    assert contains(region, point, 1e-6) is inside
