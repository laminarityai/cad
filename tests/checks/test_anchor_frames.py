import math

import pytest
from solids import Solid, apply, rotate, turn_and_move, turned
from test_anchors import (
    ACROSS_HOLES,
    ALONG_LONG,
    BAR,
    COUNTERBORED,
    CUBE,
    FLAT_END,
    HANGER,
    LARGEST_FLAT,
    PLATE,
    ROUNDED_BAR,
    THREE_HOLES,
    case,
    far_end,
    holes,
    on_holes,
    resolved,
)

from cad.checks.container.anchors import (
    Bore,
    Candidate,
    FarFrom,
    Patch,
    Plane,
    Region,
    Resolved,
    Unresolved,
)
from cad.checks.container.kernel import Point
from cad.checks.container.wire import LoadCaseWire

MOVE = turn_and_move()
TOL = 1e-6
CASES: list[tuple[Solid, LoadCaseWire]] = [
    (PLATE, case(holes(2), far_end(ACROSS_HOLES))),
    (HANGER, case(holes(2), on_holes(1, 8))),
    (COUNTERBORED, case(holes(2), far_end(ALONG_LONG))),
    (PLATE, case(LARGEST_FLAT)),
    (BAR, case(FLAT_END, far_end(ALONG_LONG))),
    (ROUNDED_BAR, case(FLAT_END, far_end({"kind": "across", "axis": "long"}))),
    (CUBE, case(LARGEST_FLAT)),
    (CUBE, case(FLAT_END)),
    (THREE_HOLES, case(holes(2))),
]


def near(a: Point, b: Point) -> bool:
    return math.dist(a, b) <= TOL


def same_patch(first: Patch, second: Patch) -> bool:
    match first, second:
        case Bore(), Bore():
            ends = sorted(end(first, t) for t in (first.t0, first.t1))
            others = sorted(end(second, t) for t in (second.t0, second.t1))
            return math.isclose(first.radius, second.radius, abs_tol=TOL) and all(
                near(a, b) for a, b in zip(ends, others, strict=True)
            )
        case Plane(), Plane():
            offset = sum(
                (a - b) * n for a, b, n in zip(first.point, second.point, first.normal, strict=True)
            )
            return near(first.normal, second.normal) and abs(offset) <= TOL
        case _:
            return False


def end(bore: Bore, t: float) -> Point:
    x, y, z = (o + t * a for o, a in zip(bore.origin, bore.axis, strict=True))
    return (x, y, z)


def moved_patch(patch: Patch) -> Patch:
    match patch:
        case Bore(origin, axis, radius, t0, t1):
            return Bore(apply(MOVE, origin), rotate(MOVE, axis), radius, t0, t1)
        case Plane(point, normal):
            return Plane(apply(MOVE, point), rotate(MOVE, normal))


def same_place(first: Region | FarFrom, second: Region | FarFrom) -> bool:
    match first, second:
        case Region(), Region():
            return (
                near(apply(MOVE, first.centroid), second.centroid)
                and len(first.patches) == len(second.patches)
                and all(
                    any(same_patch(moved_patch(a), b) for b in second.patches)
                    for a in first.patches
                )
            )
        case FarFrom(center), FarFrom(other):
            return near(apply(MOVE, center), other)
        case _:
            return False


def same_candidate(first: Candidate, second: Candidate) -> bool:
    return same_place(first.support, second.support) and same_place(first.load, second.load)


def projector(basis: tuple[Point, ...]) -> list[float]:
    return [sum(v[i] * v[j] for v in basis) for i in range(3) for j in range(3)]


@pytest.mark.parametrize(("solid", "wanted"), CASES)
def test_turning_and_moving_the_part_changes_no_resolved_anchor(
    solid: Solid, wanted: LoadCaseWire
) -> None:
    before, after = resolved(solid, wanted), resolved(turned(solid, MOVE), wanted)
    if isinstance(before, Unresolved):
        assert after == before
        return
    assert isinstance(after, Resolved), after
    assert len(after.candidates) == len(before.candidates)
    for candidate in before.candidates:
        assert any(same_candidate(candidate, other) for other in after.candidates), candidate
    turned_basis = tuple(rotate(MOVE, vector) for vector in before.basis)
    assert projector(after.basis) == pytest.approx(projector(turned_basis), abs=TOL)
