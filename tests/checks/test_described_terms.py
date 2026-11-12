import math
from collections.abc import Sequence

import pytest

from cad.checks.container import anchors
from cad.checks.container.elastic import region_faces
from cad.checks.container.mesher import TetMesh
from cad.checks.container.regions import Bore, Candidate, Disc, FarFrom, Plane, Region
from cad.checks.container.terms import (
    Across,
    Along,
    AnyWay,
    Away,
    Each,
    EndOf,
    Facing,
    FarEnd,
    Holes,
    InOneFlatFace,
    Into,
    LargestFlat,
    LoadCase,
    OnFarthest,
    OnLargestFlat,
    OnOpposite,
)
from cad.checks.container.vectors import Point, norm, sub
from tests.support.anchors import PLATE
from tests.support.described import (
    CLAMP,
    CLAMPED,
    CUBOID,
    FIVE_HOLES,
    HOOK,
    HUNG,
    PLATE_80,
    POCKETED,
    RAIL,
    RAIL_HOOK,
    THIRD_HOLE,
    TWO_LEGS,
    clamp,
    must,
    reason,
)
from tests.support.solids import Solid, apply, rotate, turn_and_move, turned

TOL = 1e-6
ANY = AnyWay()


def places(candidates: tuple[Candidate, ...]) -> list[tuple[Point, Point]]:
    return sorted((rounded(c.support.centroid), rounded(centroid_of(c.load))) for c in candidates)


def rounded(point: Point) -> Point:
    x, y, z = (round(v, 6) + 0.0 for v in point)
    return (x, y, z)


def centroid_of(load: Region | FarFrom) -> Point:
    assert isinstance(load, Region)
    return load.centroid


def normals(region: Region | FarFrom) -> list[Point]:
    assert isinstance(region, Region)
    return [patch.normal for patch in region.patches if isinstance(patch, Plane | Disc)]


def test_end_of_the_middle_axis_fixes_each_end_and_loads_the_other() -> None:
    found = must(PLATE_80, LoadCase(EndOf("middle"), FarEnd(), ANY)).candidates
    assert places(found) == [((40, 0, 3), (40, 40, 3)), ((40, 40, 3), (40, 0, 3))]


def test_end_of_the_short_axis_finds_the_two_faces_across_its_thickness() -> None:
    found = must(PLATE_80, LoadCase(EndOf("short"), FarEnd(), ANY)).candidates
    assert sorted(normals(c.support)[0][2] for c in found) == [-1, 1]


def test_end_of_a_middle_axis_tied_with_the_short_gives_an_end_of_each() -> None:
    found = must(CUBOID, LoadCase(EndOf("middle"), FarEnd(), ANY)).candidates
    assert len(found) == 4


def test_end_of_a_round_bar_across_its_axis_is_unknown() -> None:
    assert reason(RAIL, LoadCase(EndOf("middle"), FarEnd(), ANY)) == (
        "no flat face that bounds the part faces within 30° of either end of its middle axis"
    )


def test_facing_fixes_each_jaw_and_loads_the_other() -> None:
    found = must(CLAMP, CLAMPED).candidates
    assert places(found) == [((37.5, 10, 15), (37.5, 10, 35)), ((37.5, 10, 35), (37.5, 10, 15))]


def test_facing_takes_one_face_not_every_face_in_its_plane() -> None:
    (first, _) = must(CLAMP, CLAMPED).candidates
    assert len(first.support.faces) == 1 and len(centroid_faces(first.load)) == 1


def centroid_faces(region: Region | FarFrom) -> frozenset[int]:
    assert isinstance(region, Region)
    return region.faces


def test_a_part_with_no_gap_between_flat_faces_has_no_facing_support() -> None:
    assert reason(PLATE_80, CLAMPED) == "no flat face faces another across a gap"


def test_into_presses_along_the_loaded_face_inward_normal() -> None:
    found = must(CLAMP, LoadCase(Facing(), OnOpposite(middle=False), Into())).candidates
    for candidate in found:
        (normal,) = normals(candidate.load)
        assert candidate.basis == (pytest.approx(tuple(-v for v in normal)),)


def test_away_pulls_from_the_support_centroid_to_the_load_centroid() -> None:
    (first, second) = must(CLAMP, CLAMPED).candidates
    assert first.basis == (pytest.approx((0, 0, 1)),)
    assert second.basis == (pytest.approx((0, 0, -1)),)


def test_away_is_unknown_when_the_centroids_are_within_1_percent_of_the_reach() -> None:
    assert reason(clamp(0.4), CLAMPED) == (
        "the load's centroid is within 1% of the part's reach of the support's, so no line runs "
        "away from the supports"
    )


def test_each_hole_is_a_candidate_and_the_farthest_other_hole_is_loaded() -> None:
    case = LoadCase(Each("hole", 5.5), OnFarthest("hole", 5.5), Across("hole_axis"))
    found = must(PLATE, case).candidates
    assert places(found) == [((10, 10, 2.5), (50, 10, 2.5)), ((50, 10, 2.5), (10, 10, 2.5))]


def test_each_of_a_diameter_the_part_lacks_is_unknown() -> None:
    case = LoadCase(Each("hole", 9), OnFarthest("hole", None), ANY)
    assert reason(PLATE, case) == "the part has no hole of 9 mm"


def test_each_inner_curve_skips_holes_and_takes_each_curl() -> None:
    found = must(RAIL_HOOK, HUNG).candidates
    assert [c.support.centroid[0] for c in found] == [
        pytest.approx(3.82, abs=0.01),
        pytest.approx(56.18, abs=0.01),
    ]
    for candidate in found:
        (bore,) = candidate.support.patches
        assert isinstance(bore, Bore) and bore.radius == pytest.approx(6)


def test_an_inner_curve_of_a_diameter_matches_within_the_hole_tolerance() -> None:
    case = LoadCase(Holes(2, 5), OnFarthest("inner_curve", 12.04), Across("hole_axis"))
    (only,) = must(HOOK, case).candidates
    assert centroid_of(only.load)[0] == pytest.approx(56.18, abs=0.01)


def test_on_farthest_never_loads_a_support_curve() -> None:
    assert reason(HOOK, HUNG) == "the part has no inner curve outside the supports"


def test_the_hole_axis_needs_a_hole_support() -> None:
    case = LoadCase(Each("inner_curve", None), FarEnd(), Across("hole_axis"))
    assert reason(HOOK, case) == "the hole axis needs a support through holes"


def test_in_one_flat_face_gives_each_face_holding_the_holes() -> None:
    found = must(TWO_LEGS, LoadCase(InOneFlatFace(2, 4.5), FarEnd(), ANY)).candidates
    assert sorted(len(c.support.patches) for c in found) == [2, 2]
    assert sorted(round(c.support.centroid[0], 6) for c in found) == [2.5, 65]


def test_in_one_flat_face_is_unknown_when_a_face_holds_another_number() -> None:
    assert reason(THIRD_HOLE, LoadCase(InOneFlatFace(2, 4.5), FarEnd(), ANY)) == (
        "the brief names 2 holes in one flat face, and a flat face has 3 holes of 4.5 mm"
    )


def test_in_one_flat_face_is_unknown_on_a_part_with_no_such_hole() -> None:
    assert reason(PLATE_80, LoadCase(InOneFlatFace(2, 4.5), FarEnd(), ANY)) == (
        "no flat face has a hole of 4.5 mm opening on it"
    )


def test_on_largest_flat_keeps_each_face_of_a_tie_that_is_not_a_support_face() -> None:
    found = must(PLATE_80, LoadCase(EndOf("short"), OnLargestFlat(middle=False), Into())).candidates
    assert [(c.support.faces, centroid_faces(c.load)) for c in found] == [
        (frozenset({4}), frozenset({5})),
        (frozenset({5}), frozenset({4})),
    ]


def test_on_largest_flat_is_unknown_when_the_support_holds_every_largest_face() -> None:
    case = LoadCase(LargestFlat(), OnLargestFlat(middle=False), Into())
    assert reason(POCKETED, case) == "every largest flat face of the part is a support face"


def test_the_middle_is_a_disc_at_the_face_centroid_a_tenth_of_its_root_area_across() -> None:
    case = LoadCase(EndOf("middle"), OnLargestFlat(middle=True), Into())
    for candidate in must(PLATE_80, case).candidates:
        assert isinstance(candidate.load, Region)
        (patch,) = candidate.load.patches
        assert isinstance(patch, Disc)
        assert patch.center[:2] == pytest.approx((40, 20))
        assert patch.radius == pytest.approx(0.1 * math.sqrt(80 * 40))


def test_a_load_on_the_opposite_face_needs_a_facing_support() -> None:
    assert reason(PLATE_80, LoadCase(EndOf("short"), OnOpposite(middle=False), ANY)) == (
        "a load on the opposite face needs a support on one of two facing faces"
    )


def test_into_needs_a_load_on_a_flat_face() -> None:
    case = LoadCase(Holes(2, 5.5), OnFarthest("hole", None), Into())
    assert reason(PLATE, case) == "pressing into the face needs a load on a flat face"


def test_more_candidates_than_the_limit_is_unknown_and_gives_the_count() -> None:
    case = LoadCase(Each("hole", 5.5), OnFarthest("hole", 5.5), ANY)
    assert reason(FIVE_HOLES, case) == (
        "the load case gives 6 pairs of support and load, over the limit of 4"
    )
    assert anchors.CANDIDATE_LIMIT == 4


FRAMED = [
    (PLATE_80, LoadCase(EndOf("middle"), OnLargestFlat(middle=True), Into())),
    (CUBOID, LoadCase(EndOf("short"), FarEnd(), Along("long"))),
    (CLAMP, CLAMPED),
    (CLAMP, LoadCase(Facing(), OnOpposite(middle=True), Into())),
    (RAIL_HOOK, HUNG),
    (PLATE, LoadCase(Each("hole", 5.5), OnFarthest("hole", 5.5), Across("hole_axis"))),
    (TWO_LEGS, LoadCase(InOneFlatFace(2, 4.5), FarEnd(), Away())),
]


@pytest.mark.parametrize(("solid", "case"), FRAMED)
def test_every_term_finds_the_same_faces_whatever_the_frame(solid: Solid, case: LoadCase) -> None:
    move = turn_and_move()
    before = must(solid, case).candidates
    after = must(turned(solid, move), case).candidates
    assert len(after) == len(before)
    for candidate in before:
        assert any(same(move, candidate, other) for other in after), candidate


def same(move: object, first: Candidate, second: Candidate) -> bool:
    turned_basis = [rotate(move, way) for way in first.basis]
    return (
        close(apply(move, first.support.centroid), second.support.centroid)
        and close(apply(move, centroid_or_center(first.load)), centroid_or_center(second.load))
        and projector(turned_basis) == pytest.approx(projector(second.basis), abs=TOL)
    )


def projector(basis: Sequence[Point]) -> list[float]:
    """The span of the basis, which a load anywhere in it may take, as one matrix."""
    return [sum(way[i] * way[j] for way in basis) for i in range(3) for j in range(3)]


def centroid_or_center(load: Region | FarFrom) -> Point:
    return load.centroid if isinstance(load, Region) else load.center


def close(a: Point, b: Point) -> bool:
    return norm(sub(a, b)) <= 1e-6 * 100


def six_node(a: Point, b: Point, c: Point) -> list[Point]:
    return [a, b, c, middle(a, b), middle(b, c), middle(c, a)]


def middle(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def flat_mesh(triangles: list[tuple[Point, Point, Point]]) -> TetMesh:
    nodes = tuple(point for t in triangles for point in six_node(*t))
    faces = tuple(tuple(range(6 * k, 6 * k + 6)) for k in range(len(triangles)))
    return TetMesh(nodes, (), faces, (0,) * len(faces))


DISC = Region((Disc((0, 0, 0), (0, 0, 1), 1.0),), (0, 0, 0), frozenset({0}))


def test_a_middle_disc_mostly_covered_by_triangles_wholly_inside_it_is_loaded() -> None:
    ring = [(math.cos(k * math.pi / 3), math.sin(k * math.pi / 3), 0.0) for k in range(7)]
    fan = [((0.0, 0.0, 0.0), ring[k], ring[k + 1]) for k in range(6)]
    assert region_faces(flat_mesh(fan), DISC, TOL) == flat_mesh(fan).faces


def test_a_middle_disc_the_inside_triangles_cover_under_half_of_is_unknown() -> None:
    small = [((0.0, 0.0, 0.0), (0.5, 0.0, 0.0), (0.0, 0.5, 0.0))]
    found = region_faces(flat_mesh(small), DISC, TOL)
    assert not isinstance(found, tuple)
    assert (
        found.reason == "the mesh triangles wholly inside the middle disc cover 4% of it, under 50%"
    )
