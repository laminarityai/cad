from itertools import accumulate

from cad.frozen import Frozen
from cad.sandbox.bodies import Bodies, BodyName


class BodyFaces(Frozen):
    """The faces of one body of a variant, numbered as its mesh numbers them."""

    name: BodyName
    faces: tuple[int, ...]


def body_faces(bodies: Bodies, solid_faces: tuple[int, ...]) -> tuple[BodyFaces, ...]:
    """Each body's faces, from the face count of each solid: face k of solid i is face
    `offset_i + k`, where `offset_i` counts the faces of the solids before it. Empty for one
    unnamed body, and when the mesh counts no solid for each one the bodies name."""
    if len(solid_faces) != sum(len(body.solids) for body in bodies):
        return ()
    starts = list(accumulate(solid_faces, initial=0))
    return tuple(
        BodyFaces(
            name=body.name,
            faces=tuple(
                face for solid in body.solids for face in range(starts[solid], starts[solid + 1])
            ),
        )
        for body in bodies
    )
