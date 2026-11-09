from typing import Literal, TypedDict

type Location = tuple[tuple[float, float, float], tuple[float, float, float, float]]


class ShapeWire(TypedDict):
    """One part's mesh in three-cad-viewer's layout: flat xyz arrays and each face's triangles in
    turn. Every face has vertices of its own, so the edges between faces stay sharp."""

    vertices: list[float]
    normals: list[float]
    triangles: list[int]
    triangles_per_face: list[int]
    face_types: list[int]
    edges: list[float]
    segments_per_edge: list[int]
    edge_types: list[int]
    obj_vertices: list[float]


class BoundingBoxWire(TypedDict):
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float


class PartWire(TypedDict):
    version: Literal[3]
    id: str
    name: str
    type: Literal["shapes"]
    subtype: Literal["solid"]
    shape: ShapeWire
    state: tuple[int, int]
    color: str
    alpha: float
    texture: None
    loc: Location
    renderback: bool
    accuracy: float
    bb: None


class ShapesWire(TypedDict):
    version: Literal[3]
    id: str
    name: str
    parts: list[PartWire]
    loc: Location
    normal_len: int
    bb: BoundingBoxWire


class TessellatedReport(TypedDict):
    kind: Literal["tessellated"]
    shapes: ShapesWire


class UnreadableReport(TypedDict):
    kind: Literal["unreadable"]
    reason: str


type TessellationReport = TessellatedReport | UnreadableReport
