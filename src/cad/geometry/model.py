from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.geometry.container.wire import ShapesWire, ShapeWire, TopologyWire
from cad.variants.entry import UnknownVariant


class UnknownMesh(UnknownVariant):
    pass


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Tessellated(_Frozen):
    """The mesh of one BREP, made in the analysis image, as three-cad-viewer renders it."""

    kind: Literal["tessellated"] = "tessellated"
    brep_sha256: str
    version: str
    shapes: ShapesWire
    topology: TopologyWire


class TessellationFailed(_Frozen):
    kind: Literal["failed"] = "failed"
    brep_sha256: str
    version: str
    reason: str


class TessellationPending(_Frozen):
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
