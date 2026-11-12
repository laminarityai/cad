"""The min_wall check on real solids whose thinnest wall is known by hand, read through the real
kernel, as made, turned and moved with its faces in reverse order. Each truth follows from the
check's own rule: the ray along the inward normal, counted only when it comes out through a face
that looks back within 60 degrees."""

import pytest

from cad.checks.container import closed_solid, min_wall
from cad.checks.container.check import Subject
from cad.checks.container.inputs import Input, Inputs
from cad.checks.container.kernel import Patch, Reading, Shape, Walls
from cad.checks.container.kernel.ocp_kernel import OcpKernel
from cad.checks.container.wire import ResultWire
from tests.support.check_fakes import NoFem
from tests.support.solids import (
    Solid,
    box,
    cut,
    fillet_edges,
    fuse,
    prism,
    rod,
    turn_and_move,
    turned,
)

INPUTS = Inputs(frozenset[Input](), {})
PASSED: dict[str, ResultWire] = {
    closed_solid.ID: {"id": closed_solid.ID, "verdict": "pass", "measured": [], "reason": ""}
}
BOUND = min_wall.ERROR_BOUNDS["min_wall"]


def top_long_edge(first: tuple[float, float, float], last: tuple[float, float, float]) -> bool:
    return first[0] == last[0] == 40 and first[2] == last[2] == 2


KNOWN: dict[str, tuple[Solid, float]] = {
    "box shell 2 mm": (cut(box(40, 30, 20), box(36, 26, 20, (2, 2, 2))), 2.0),
    "tube 1.5 mm": (cut(rod(10, 30, (0, 0, 0)), rod(8.5, 32, (0, 0, -1))), 1.5),
    "plate with a 0.8 mm rib": (fuse(box(50, 30, 4), box(0.8, 30, 10, (20, 0, 4))), 0.8),
    "hole 0.6 mm from an edge": (cut(box(40, 20, 6), rod(3, 8, (3.6, 10, -1))), 0.6),
    "wall tapered from 3 to 1 mm": (prism([(0, 0), (40, 0), (40, 1), (0, 3)], 20), 1.0),
    "crossed slots 0.5 mm apart": (
        cut(box(60, 60, 6), box(2, 60, 3.25, (29, 0, 3.25)), box(60, 2, 2.75, (0, 29, 0))),
        0.5,
    ),
    "crossed holes 0.4 mm apart": (
        cut(box(60, 60, 30), rod(1, 32, (30, 30, -1)), rod(1, 62, (32.4, -1, 15), (0, 1, 0))),
        0.4,
    ),
    "bore 0.05 mm under the top": (
        cut(box(40, 20, 10), rod(4, 22, (20, -1, 5.95), (0, 1, 0))),
        0.05,
    ),
    "solid block": (box(10, 20, 30), 10.0),
    "rod": (rod(4, 30, (0, 0, 0)), 8.0),
    # Past the point where the round turns 60 degrees from the bottom face, a ray up from the
    # bottom comes out at a corner, so the reading stops at 2 - 1 / 2.
    "2 mm plate with a 1 mm round": (fillet_edges(box(40, 20, 2), 1.0, top_long_edge), 1.5),
}
KNIFE = prism([(0, 0), (40, 0), (0, 5)], 10)


class ReversedWalls:
    def __init__(self, walls: Walls) -> None:
        self._walls = walls
        self._last = len(walls.patches) - 1

    @property
    def patches(self) -> tuple[Patch, ...]:
        return self._walls.patches[::-1]

    def reading(self, face: int, u: float, v: float) -> Reading | None:
        return self._walls.reading(self._last - face, u, v)


class Reordered(OcpKernel):
    """The same kernel, listing the faces back to front."""

    def walls(self, shape: Shape) -> Walls:
        return ReversedWalls(super().walls(shape))


def thinnest(solid: Solid, kernel: OcpKernel) -> float:
    found = min_wall.run(Subject(kernel, NoFem(), solid, INPUTS, PASSED))
    assert found["verdict"] == "pass", found["reason"]
    [wall] = found["measured"]
    return wall["magnitude"]


@pytest.mark.parametrize("name", sorted(KNOWN))
def test_the_thinnest_wall_is_within_the_stated_error_however_the_part_lies(name: str) -> None:
    solid, truth = KNOWN[name]
    for wall in (
        thinnest(solid, OcpKernel()),
        thinnest(turned(solid, turn_and_move()), Reordered()),
    ):
        assert abs(wall - truth) <= BOUND * truth, wall


def test_a_knife_edge_reads_as_a_wall_that_thins_to_nothing() -> None:
    assert thinnest(KNIFE, OcpKernel()) < 1e-4
    assert thinnest(turned(KNIFE, turn_and_move()), Reordered()) < 1e-4
