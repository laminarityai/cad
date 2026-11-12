import math

import pytest

from cad.checks.container import anchors
from cad.checks.container.kernel import Flat
from cad.checks.container.regions import FarFrom, Plane, Region
from cad.checks.container.vectors import Point, angle, scale
from tests.fea.cases import (
    ARM_TIP,
    BEAM_B,
    BEAM_H,
    BEAM_L,
    PLATE_BACK,
    PLATE_BELOW,
    PLATE_X,
    PLATE_Y,
    PLATE_Z,
)
from tests.support.anchors import (
    BOLTED_L,
    CHAMFER_DEG,
    CHAMFERED_BAR,
    CUBE,
    FLAT_END,
    KERNEL,
    L_BRACKET,
    NOSED_BAR,
    SLANT_DEG,
    SLANTED_BAR,
    SQUARE_TAB,
    T_ARM,
    case,
    holes,
    must,
)
from tests.support.solids import Solid, box, fuse


def plane(region: Region | FarFrom) -> Plane:
    assert isinstance(region, Region)
    (patch,) = region.patches
    assert isinstance(patch, Plane)
    return patch


def ends(solid: Solid) -> list[Plane]:
    return sorted(
        (plane(c.support) for c in must(solid, case(FLAT_END)).candidates),
        key=lambda p: (p.normal, p.point),
    )


def tilt_deg(solid: Solid, normal: Point) -> float:
    axis = anchors.long_axis(KERNEL.inertia(solid))
    assert not isinstance(axis, anchors.Unresolved), axis
    return math.degrees(min(angle(normal, axis), angle(normal, scale(axis, -1))))


def test_an_l_bracket_is_held_at_its_wall_face_and_its_arm_tip() -> None:
    wall, tip = ends(L_BRACKET)
    assert wall.normal == pytest.approx((-1, 0, 0)) and wall.point[0] == pytest.approx(0)
    assert tip.normal == pytest.approx((1, 0, 0)) and tip.point[0] == pytest.approx(100)
    assert tilt_deg(L_BRACKET, tip.normal) == pytest.approx(15.1, abs=0.1)


def test_the_wall_face_of_an_l_joins_the_arm_end_flush_with_it() -> None:
    (wall,) = (
        c.support
        for c in must(L_BRACKET, case(FLAT_END)).candidates
        if plane(c.support).point[0] < 50
    )
    assert wall.centroid == pytest.approx((0, 15, -20))


def test_a_t_arm_with_an_off_centre_plate_is_held_at_the_plate_and_the_arm_tip() -> None:
    plate, tip = ends(T_ARM)
    assert plate.normal == pytest.approx((-1, 0, 0)) and plate.point[0] == pytest.approx(0)
    assert tip.normal == pytest.approx((1, 0, 0)) and tip.point[0] == pytest.approx(100)
    assert tilt_deg(T_ARM, tip.normal) == pytest.approx(10.1, abs=0.1)


def test_a_face_40_degrees_off_the_long_axis_is_not_an_end() -> None:
    (only,) = ends(SLANTED_BAR)
    assert only.normal == pytest.approx((-1, 0, 0))
    slanted = (math.cos(math.radians(SLANT_DEG)), math.sin(math.radians(SLANT_DEG)), 0.0)
    assert tilt_deg(SLANTED_BAR, slanted) > 39


@pytest.mark.parametrize("role", ["support", "load"])
def test_a_chamfer_inside_the_cone_next_to_a_flat_end_is_never_the_end(role: str) -> None:
    chamfer = (math.cos(math.radians(CHAMFER_DEG)), math.sin(math.radians(CHAMFER_DEG)), 0.0)
    assert tilt_deg(CHAMFERED_BAR, chamfer) < 30
    found = must(CHAMFERED_BAR, case(FLAT_END)).candidates
    regions = [c.support if role == "support" else c.load for c in found]
    tips = [plane(r) for r in regions if plane(r).normal[0] > 0]
    assert [tip.normal for tip in tips] == [pytest.approx((1, 0, 0))]
    assert [tip.point[0] for tip in tips] == [pytest.approx(100)]
    assert all(angle(plane(r).normal, chamfer) > 0.1 for r in regions)


def test_the_far_end_of_a_bolted_l_is_its_whole_arm_tip() -> None:
    (candidate,) = must(BOLTED_L, case(holes(2, 4.5))).candidates
    tip = plane(candidate.load)
    assert tip.normal == pytest.approx((1, 0, 0)) and tip.point[0] == pytest.approx(100)
    assert isinstance(candidate.load, Region)
    assert candidate.load.centroid == pytest.approx((100, 15, 2.5))


@pytest.mark.parametrize(("solid", "count"), [(SQUARE_TAB, 4), (CUBE, 6)])
def test_tied_long_axes_make_each_bounding_side_an_end(solid: Solid, count: int) -> None:
    found = must(solid, case(FLAT_END)).candidates
    assert len(found) == count
    for candidate in found:
        support, tip = plane(candidate.support), plane(candidate.load)
        assert tip.normal == pytest.approx(scale(support.normal, -1))


def test_a_flat_face_with_material_beyond_its_plane_is_not_an_end() -> None:
    flats = [f.surface for f in KERNEL.faces(NOSED_BAR) if isinstance(f.surface, Flat)]
    behind = [flat.beyond for flat in flats if flat.normal[0] > 0.99]
    assert behind and behind == pytest.approx([3.0] * len(behind))
    (only,) = must(NOSED_BAR, case(FLAT_END)).candidates
    assert plane(only.support).normal == pytest.approx((-1, 0, 0))
    assert isinstance(only.load, FarFrom)


def test_the_plated_cantilever_harness_case_is_the_case_the_anchors_resolve() -> None:
    plate = box(PLATE_X, PLATE_Y, PLATE_Z, at=(-PLATE_X, -(PLATE_Y - BEAM_B) / 2, -PLATE_BELOW))
    found = must(fuse(plate, box(BEAM_L, BEAM_B, BEAM_H)), case(FLAT_END)).candidates
    pairs = [(plane(c.support), plane(c.load)) for c in found]
    fixed, loaded = plane(PLATE_BACK), plane(ARM_TIP)
    assert any(
        support.normal == pytest.approx(fixed.normal)
        and support.point[0] == pytest.approx(fixed.point[0])
        and tip.normal == pytest.approx(loaded.normal)
        and tip.point[0] == pytest.approx(loaded.point[0])
        for support, tip in pairs
    )
