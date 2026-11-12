import pytest

from cad.checks.container import fea
from cad.checks.container.features import face_round
from cad.checks.container.kernel import Point, Round
from cad.checks.container.regions import FarFrom, Plane, Region
from cad.checks.container.wire import (
    HolesWire,
)
from tests.support.anchors import (
    ACROSS_HOLES,
    ALONG_LONG,
    BAR,
    COUNTERBORED,
    CROSSED,
    CUBE,
    FILLETED,
    FLAT_END,
    FLIPPED,
    HANGER,
    KERNEL,
    LARGEST_FLAT,
    PINNED,
    PLATE,
    ROUNDED_BAR,
    THREE_HOLES,
    TOL,
    bore_ends,
    bores,
    case,
    close,
    far_end,
    held,
    holes,
    must,
    on_holes,
    reason,
)
from tests.support.solids import Solid, box, cut, through_hole


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
    concave = [f for f in faces if isinstance(f.surface, Round) and f.surface.concave]
    assert len(concave) >= 2 + 4 + 2
    assert {round(face_round(f).radius, 6) for f in concave} == {2.75}
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
    (candidate,) = must(solid, case(holes(2), far_end(ACROSS_HOLES))).candidates[:1]
    return candidate.basis


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


def test_a_part_with_isotropic_inertia_has_no_long_axis_to_load_along() -> None:
    no_long = "the part has no unique long axis: its two largest volume spreads are within 1%"
    assert reason(CUBE, case(LARGEST_FLAT, far_end(ALONG_LONG))) == no_long
    assert len(must(CUBE, case(LARGEST_FLAT)).candidates) == 6


def test_the_far_end_of_a_bar_is_the_whole_end_face_opposite_its_support() -> None:
    for candidate in must(BAR, case(FLAT_END)).candidates:
        support, tip = plane(candidate.support), plane(candidate.load)
        assert tip.normal == pytest.approx(tuple(-n for n in support.normal))
        assert abs(tip.point[0] - support.point[0]) == pytest.approx(100)


def test_a_rounded_tip_falls_back_to_the_band_toward_the_centre_of_mass() -> None:
    (candidate,) = must(ROUNDED_BAR, case(FLAT_END)).candidates
    far = candidate.load
    assert isinstance(far, FarFrom)
    assert far.center == pytest.approx(candidate.support.centroid)
    assert far.axis == pytest.approx((1, 0, 0))
    assert far.cutoff([(0.0, 5.0, 3.0), (105.0, 5.0, 3.0)]) == pytest.approx(0.995 * 105)


def test_a_support_at_the_centre_of_mass_loads_each_end_of_the_long_axis() -> None:
    tips = [plane(candidate.load) for candidate in must(PLATE, case(holes(2))).candidates]
    found = sorted((tip.normal[0], tip.point[0]) for tip in tips)
    assert found == [pytest.approx((-1, 0)), pytest.approx((1, 60))]


def test_a_support_at_the_centre_of_a_part_with_no_long_axis_has_no_far_end() -> None:
    square = cut(box(40, 40, 5), *(through_hole(5.5, x, y) for x in (10, 30) for y in (10, 30)))
    assert reason(square, case(holes(4))) == (
        "the support sits at the part's centre of mass and the part has no unique long axis, "
        "so no end of the part is the far one"
    )


def plane(region: Region | FarFrom) -> Plane:
    assert isinstance(region, Region)
    (patch,) = region.patches
    assert isinstance(patch, Plane)
    return patch
