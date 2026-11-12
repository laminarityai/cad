import pytest
from cases import (
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

from cad.checks.container.regions import FarFrom, Plane, Region
from tests.support.anchors import FLAT_END, case, must
from tests.support.solids import box, fuse


def plane(region: Region | FarFrom) -> Plane:
    assert isinstance(region, Region)
    (patch,) = region.patches
    assert isinstance(patch, Plane)
    return patch


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
