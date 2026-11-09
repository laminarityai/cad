import math
from collections.abc import Sequence

import pytest
from solids import (
    Solid,
    box,
    cut,
    fillet_edges,
    fuse,
    rod,
    through_hole,
)

from cad.checks.container import anchors, fea
from cad.checks.container.anchors import (
    Bore,
    FarFrom,
    Plane,
    Region,
    Resolved,
    Unresolved,
    resolve,
)
from cad.checks.container.kernel import Point, ocp_kernel
from cad.checks.container.wire import (
    DirectionWire,
    HolesWire,
    LoadCaseWire,
    LoadWire,
    SupportWire,
)

KERNEL = ocp_kernel()
TOL = 1e-6
ANY: DirectionWire = {"kind": "any"}
ACROSS_HOLES: DirectionWire = {"kind": "across", "axis": "hole_axis"}
ALONG_LONG: DirectionWire = {"kind": "along", "axis": "long"}
LARGEST_FLAT: SupportWire = {"kind": "largest_flat"}
FLAT_END: SupportWire = {"kind": "flat_end"}

PLATE = cut(box(60, 20, 5), through_hole(5.5, 10, 10), through_hole(5.5, 50, 10))
THREE_HOLES = cut(PLATE, through_hole(5.5, 30, 10))
HANGER = cut(PLATE, through_hole(8, 30, 10))
POCKET = fillet_edges(
    box(15, 12, 4, at=(25, 4, 2)),
    2.75,
    lambda a, b: math.isclose(a[0], b[0]) and math.isclose(a[1], b[1]),
)
SLOT = fuse(
    box(10, 5.5, 7, at=(50, 7.25, -1)), rod(2.75, 7, (50, 10, -1)), rod(2.75, 7, (60, 10, -1))
)
FILLETED = cut(box(80, 20, 5), through_hole(5.5, 10, 10), through_hole(5.5, 70, 10), POCKET, SLOT)
COUNTERBORED = cut(
    box(40, 20, 8),
    through_hole(5.5, 10, 10, depth=8),
    rod(5, 4, (10, 10, 5)),
    through_hole(5.5, 30, 10, depth=8),
)
CROSSED = cut(
    box(40, 20, 20), through_hole(5.5, 30, 15, depth=20), rod(2.75, 42, (-1, 5, 10), (1, 0, 0))
)
BAR = box(100, 10, 6)
ROUNDED_BAR = fuse(BAR, rod(5, 6, (100, 5, 0)))
CUBE = box(10, 10, 10)
FLIPPED = cut(box(60, 20, 5), through_hole(5.5, 10, 10), rod(2.75, 7, (50, 10, 6), (0, 0, -1)))
PINNED = fuse(PLATE, rod(2.75, 4, (30, 10, 5)))


def holes(count: int, diameter_mm: float | None = 5.5) -> HolesWire:
    return {"kind": "holes", "count": count, "diameter_mm": diameter_mm}


def far_end(direction: DirectionWire = ANY) -> LoadWire:
    return {"kind": "far_end", "force_n": 49.0, "direction": direction}


def on_holes(count: int, diameter_mm: float | None) -> LoadWire:
    return {
        "kind": "on_holes",
        "count": count,
        "diameter_mm": diameter_mm,
        "force_n": 10.0,
        "direction": ACROSS_HOLES,
    }


def case(support: SupportWire, load: LoadWire | None = None) -> LoadCaseWire:
    return {"support": support, "load": far_end() if load is None else load}


def resolved(solid: Solid, wanted: LoadCaseWire) -> Resolved | Unresolved:
    return resolve(wanted, KERNEL.faces(solid), KERNEL.inertia(solid))


def must(solid: Solid, wanted: LoadCaseWire) -> Resolved:
    found = resolved(solid, wanted)
    assert isinstance(found, Resolved), found
    return found


def reason(solid: Solid, wanted: LoadCaseWire) -> str:
    found = resolved(solid, wanted)
    assert isinstance(found, Unresolved), found
    return found.reason


def held(solid: Solid, support: SupportWire) -> Region:
    found = anchors.support_regions(support, KERNEL.faces(solid), KERNEL.inertia(solid))
    assert not isinstance(found, Unresolved), found
    (region,) = found
    return region


def bores(region: Region | FarFrom) -> list[Bore]:
    assert isinstance(region, Region)
    found = [patch for patch in region.patches if isinstance(patch, Bore)]
    assert len(found) == len(region.patches)
    return found


def bore_ends(bore: Bore) -> list[tuple[float, ...]]:
    return sorted(
        tuple(round(o + t * a, 6) for o, a in zip(bore.origin, bore.axis, strict=True))
        for t in (bore.t0, bore.t1)
    )


def close(a: Sequence[float], b: Sequence[float], tol: float = TOL) -> bool:
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b, strict=True))


def test_two_bolt_holes_are_the_support_bores() -> None:
    support = held(PLATE, holes(2))
    found = sorted(bores(support), key=lambda bore: bore_ends(bore))
    assert [bore.radius for bore in found] == pytest.approx([2.75, 2.75])
    assert [bore_ends(bore) for bore in found] == [
        [(10, 10, 0), (10, 10, 5)],
        [(50, 10, 0), (50, 10, 5)],
    ]
    assert close(support.centroid, (30, 10, 2.5))


@pytest.mark.parametrize(
    ("solid", "support", "said"),
    [
        (THREE_HOLES, holes(2), "the brief names 2 support holes of 5.5 mm, the part has 3"),
        (PLATE, holes(3, None), "the brief names 3 support holes, the part has 2"),
        (PLATE, holes(2, 8), "the brief names 2 support holes of 8 mm, the part has 0"),
    ],
)
def test_a_count_that_does_not_match_fails_closed_and_names_both_counts(
    solid: Solid, support: HolesWire, said: str
) -> None:
    assert reason(solid, case(support)) == said


def test_a_pin_of_the_bore_radius_is_not_a_hole() -> None:
    assert len(bores(held(PINNED, holes(2)))) == 2


def test_concave_fillets_and_slot_ends_of_the_bore_radius_are_not_holes() -> None:
    faces = KERNEL.faces(FILLETED)
    concave = [f for f in faces if isinstance(f.surface, anchors.Round) and f.surface.concave]
    assert len(concave) >= 2 + 4 + 2
    assert {round(anchors.face_round(f).radius, 6) for f in concave} == {2.75}
    found = bores(held(FILLETED, holes(2)))
    assert sorted(bore_ends(b)[0][:2] for b in found) == [(10, 10), (70, 10)]


def test_a_counterbore_is_one_hole_held_at_its_narrow_bore() -> None:
    (candidate,) = must(COUNTERBORED, case(holes(2))).candidates
    found = sorted(bores(candidate.support), key=lambda bore: bore_ends(bore))
    assert [bore.radius for bore in found] == pytest.approx([2.75, 2.75])
    assert [bore_ends(bore) for bore in found] == [
        [(10, 10, 0), (10, 10, 5)],
        [(30, 10, 0), (30, 10, 8)],
    ]
    assert reason(COUNTERBORED, case(holes(2, 10))) == (
        "the brief names 2 support holes of 10 mm, the part has 0"
    )


def test_a_load_on_holes_takes_the_holes_that_are_not_supports() -> None:
    (candidate,) = must(HANGER, case(holes(2), on_holes(1, 8))).candidates
    (bore,) = bores(candidate.load)
    assert bore.radius == pytest.approx(4)
    assert bore_ends(bore) == [(30, 10, 0), (30, 10, 5)]
    assert reason(HANGER, case(holes(2), on_holes(2, None))) == (
        "the brief names 2 loaded holes, the part has 1"
    )


def across_holes(solid: Solid) -> tuple[Point, ...]:
    basis = anchors.direction_basis(
        ACROSS_HOLES, holes(2), KERNEL.faces(solid), KERNEL.inertia(solid)
    )
    assert not isinstance(basis, Unresolved), basis
    return basis


def test_the_hole_axis_is_the_axis_the_support_holes_share() -> None:
    basis = across_holes(PLATE)
    assert len(basis) == 2
    for vector in basis:
        assert vector[2] == pytest.approx(0, abs=TOL)
    assert len(across_holes(FLIPPED)) == 2
    assert reason(CROSSED, case(holes(2), far_end(ACROSS_HOLES))) == (
        "the support holes are not parallel, so they share no hole axis"
    )
    assert reason(BAR, case(FLAT_END, far_end(ACROSS_HOLES))) == (
        "the hole axis needs a support through holes"
    )


def test_tied_largest_flats_are_each_a_candidate() -> None:
    found = must(PLATE, case(LARGEST_FLAT)).candidates
    planes = sorted((plane(c.support) for c in found), key=lambda p: p.normal[2])
    assert [p.normal for p in planes] == [(0, 0, -1), (0, 0, 1)]
    assert [p.point[2] for p in planes] == pytest.approx([0, 5])


def test_both_flat_ends_of_a_bar_are_candidates_and_a_rounded_end_is_not() -> None:
    ends = must(BAR, case(FLAT_END)).candidates
    assert sorted(plane(c.support).point[0] for c in ends) == pytest.approx([0, 100])
    (end,) = must(ROUNDED_BAR, case(FLAT_END)).candidates
    assert plane(end.support).normal == pytest.approx((-1, 0, 0))


def test_a_flat_face_support_clamps_a_face_and_a_bolted_support_does_not() -> None:
    assert fea.clamps_a_face(must(BAR, case(FLAT_END)))
    assert fea.clamps_a_face(must(PLATE, case(LARGEST_FLAT)))
    assert not fea.clamps_a_face(must(PLATE, case(holes(2))))


def test_a_part_with_isotropic_inertia_has_no_long_axis() -> None:
    no_long = "the part has no unique long axis: its two largest volume spreads are within 1%"
    assert reason(CUBE, case(FLAT_END)) == no_long
    assert reason(CUBE, case(LARGEST_FLAT, far_end(ALONG_LONG))) == no_long
    assert len(must(CUBE, case(LARGEST_FLAT)).candidates) == 6


def test_the_far_end_is_measured_from_the_supports_toward_the_centre_of_mass() -> None:
    for candidate in must(BAR, case(FLAT_END)).candidates:
        far = candidate.load
        assert isinstance(far, FarFrom)
        assert far.center == pytest.approx(candidate.support.centroid)
        assert far.center[1:] == pytest.approx((5, 3))
        inward = 1.0 if far.center[0] < 50 else -1.0
        assert far.axis == pytest.approx((inward, 0, 0))
        corners = [(x, y, z) for x in (0.0, 100.0) for y in (0.0, 10.0) for z in (0.0, 6.0)]
        assert far.cutoff(corners) == pytest.approx(0.995 * 100)


def test_a_support_at_the_centre_of_mass_loads_each_end_of_the_long_axis() -> None:
    corners = [(x, y, z) for x in (0.0, 60.0) for y in (0.0, 20.0) for z in (0.0, 5.0)]
    fars = [candidate.load for candidate in must(PLATE, case(holes(2))).candidates]
    assert all(isinstance(far, FarFrom) for far in fars)
    axes = sorted(far.axis for far in fars if isinstance(far, FarFrom))
    assert axes == [pytest.approx((-1, 0, 0)), pytest.approx((1, 0, 0))]
    assert all(
        far.cutoff(corners) == pytest.approx(0.995 * 30) for far in fars if isinstance(far, FarFrom)
    )


def test_a_support_at_the_centre_of_a_part_with_no_long_axis_has_no_far_end() -> None:
    square = cut(box(40, 40, 5), *(through_hole(5.5, x, y) for x in (10, 30) for y in (10, 30)))
    assert reason(square, case(holes(4))) == (
        "the support sits at the part's centre of mass and the part has no unique long axis, "
        "so no end of the part is the far one"
    )


def plane(region: Region) -> Plane:
    (patch,) = region.patches
    assert isinstance(patch, Plane)
    return patch
