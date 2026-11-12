"""The described harness cases solve the faces and direction the resolver gives for their terms."""

import pytest
from cases import (
    BY_NAME,
    C_DEPTH,
    C_SIDE,
    C_T,
    HOOK_B,
    HOOK_HOLE,
    HOOK_HOLES,
    HOOK_RI,
    HOOK_RO,
    HOOK_SHANK,
    HOOK_W,
    SHELF_T,
    SHELF_X,
    SHELF_Y,
    Case,
)

from cad.checks.container.regions import Bore, Disc, FarFrom, Patch, Plane, Region
from cad.checks.container.terms import (
    Away,
    Facing,
    FlatEnd,
    Holes,
    Into,
    LoadCase,
    OnFarthest,
    OnLargestFlat,
    OnOpposite,
)
from cad.checks.container.vectors import cross, dot, norm, sub, unit
from tests.support.described import must
from tests.support.solids import Solid, box, cut, fuse, rod

Y = (0.0, 1.0, 0.0)
RING = cut(
    rod(HOOK_RO, HOOK_B, (HOOK_RO, 0, 0), Y),
    rod(HOOK_RI, HOOK_B + 2, (HOOK_RO, -1, 0), Y),
    box(2 * HOOK_RO + 2, HOOK_B + 2, HOOK_RO + 1, at=(-1, -1, 0)),
)
HOOK = cut(
    fuse(box(HOOK_W, HOOK_B, HOOK_SHANK), RING),
    *(rod(HOOK_HOLE / 2, 30, (HOOK_W / 2, -10, z), Y) for z in HOOK_HOLES),
)
C_FRAME = cut(
    box(C_SIDE, C_DEPTH, C_SIDE), box(C_SIDE, C_DEPTH + 2, C_SIDE - 2 * C_T, at=(C_T, -1, C_T))
)

SOLIDS: dict[str, tuple[Solid, LoadCase]] = {
    "plate pressed in the middle": (
        box(SHELF_X, SHELF_Y, SHELF_T),
        LoadCase(FlatEnd(), OnLargestFlat(middle=True), Into()),
    ),
    "clamp pried apart": (C_FRAME, LoadCase(Facing(), OnOpposite(middle=False), Into())),
    "hook pulled from its curl": (
        HOOK,
        LoadCase(Holes(2, HOOK_HOLE), OnFarthest("inner_curve", None), Away()),
    ),
}


def same_patch(found: Patch, wanted: Patch) -> bool:
    match found, wanted:
        case Plane(point, normal), Plane(at, facing):
            return dot(normal, facing) == pytest.approx(1) and dot(
                sub(point, at), facing
            ) == pytest.approx(0, abs=1e-6)
        case Bore(origin, axis, radius, _, _), Bore(at, along, size, _, _):
            off = norm(cross(sub(origin, at), along))
            return (
                abs(dot(axis, along)) == pytest.approx(1)
                and radius == pytest.approx(size)
                and off == pytest.approx(0, abs=1e-6)
            )
        case Disc(center, normal, radius), Disc(at, facing, size):
            return (
                list(center) == pytest.approx(list(at))
                and list(normal) == pytest.approx(list(facing))
                and radius == pytest.approx(size)
            )
        case _:
            return False


def same_region(found: Region | FarFrom, wanted: Region | FarFrom) -> bool:
    if not isinstance(found, Region) or not isinstance(wanted, Region):
        return False
    return (
        len(found.patches) == len(wanted.patches)
        and all(any(same_patch(f, w) for f in found.patches) for w in wanted.patches)
        and list(found.centroid) == pytest.approx(list(wanted.centroid), abs=1e-6)
    )


@pytest.mark.parametrize("name", list(SOLIDS))
def test_the_harness_case_is_a_candidate_the_terms_resolve_to(name: str) -> None:
    case: Case = BY_NAME[name]
    solid, terms = SOLIDS[name]
    way = unit(case.force)
    assert any(
        same_region(c.support, case.fixed)
        and same_region(c.load, case.loaded)
        and [list(b) for b in c.basis] == [pytest.approx(list(way))]
        for c in must(solid, terms).candidates
    )
