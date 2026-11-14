from typing import Annotated, Literal

from pydantic import Field

from cad.errors import NotFound
from cad.frozen import Frozen
from cad.geometry.container.wire import ShapesWire, ShapeWire, TopologyWire


class UnknownMesh(NotFound):
    pass


class Tessellated(Frozen):
    """The mesh of one BREP, made in the analysis image, as three-cad-viewer renders it.
    `solid_faces` counts the faces of each solid in the order the kernel's explorer finds the
    solids, so face k of solid i is face `sum(solid_faces[:i]) + k`. It is empty when the solids'
    faces do not add up to the mesh's, as for a copy left in place."""

    kind: Literal["tessellated"] = "tessellated"
    brep_sha256: str
    version: str
    shapes: ShapesWire
    topology: TopologyWire
    solid_faces: tuple[int, ...] = ()


class TessellationFailed(Frozen):
    kind: Literal["failed"] = "failed"
    brep_sha256: str
    version: str
    reason: str


class TessellationPending(Frozen):
    kind: Literal["pending"] = "pending"
    brep_sha256: str


type Stored = Annotated[Tessellated | TessellationFailed, Field(discriminator="kind")]
type GeometryRead = Annotated[
    Tessellated | TessellationFailed | TessellationPending, Field(discriminator="kind")
]


def mesh_volume(shape: ShapeWire) -> float:
    """The volume the triangles enclose, by the divergence theorem: the sum of the signed
    volumes of the tetrahedra each outward-wound triangle makes with the origin."""
    v, t = shape["vertices"], shape["triangles"]
    total = 0.0
    for start in range(0, len(t), 3):
        ax, ay, az = v[3 * t[start] : 3 * t[start] + 3]
        bx, by, bz = v[3 * t[start + 1] : 3 * t[start + 1] + 3]
        cx, cy, cz = v[3 * t[start + 2] : 3 * t[start + 2] + 3]
        total += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return total / 6.0
