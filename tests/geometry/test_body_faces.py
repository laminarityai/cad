from cad.geometry.bodies import BodyFaces, body_faces
from cad.sandbox.bodies import Body

PLATE_AND_GEARS = (Body(name="plate", solids=(0,)), Body(name="gear", solids=(1, 2)))


def test_a_body_takes_the_faces_of_each_of_its_solids_by_their_offset() -> None:
    assert body_faces(PLATE_AND_GEARS, (6, 3, 3)) == (
        BodyFaces(name="plate", faces=(0, 1, 2, 3, 4, 5)),
        BodyFaces(name="gear", faces=(6, 7, 8, 9, 10, 11)),
    )


def test_bodies_that_interleave_their_solids_still_get_each_solid_s_own_faces() -> None:
    bodies = (Body(name="gear", solids=(0, 2)), Body(name="plate", solids=(1,)))
    assert body_faces(bodies, (2, 3, 1)) == (
        BodyFaces(name="gear", faces=(0, 1, 5)),
        BodyFaces(name="plate", faces=(2, 3, 4)),
    )


def test_no_body_has_faces_when_the_mesh_does_not_count_a_solid_for_each_the_bodies_name() -> None:
    assert body_faces(PLATE_AND_GEARS, (6, 6)) == ()
    assert body_faces(PLATE_AND_GEARS, ()) == ()


def test_a_variant_of_one_unnamed_body_has_none() -> None:
    assert body_faces((), (6,)) == ()
