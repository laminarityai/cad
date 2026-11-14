from typing import Literal, TypedDict

type Location = tuple[tuple[float, float, float], tuple[float, float, float, float]]
type Vec = tuple[float, float, float]


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


class FaceFacts(TypedDict):
    """What one BREP face is, in the order `shapes` numbers faces, so faces_<i> in the viewer is
    entry i. Lengths in mm. `normal` points out of the solid at `center`; `axis` and `radius`
    describe a cylinder, cone, sphere or torus and are None for other faces."""

    type: str
    area: float
    center: Vec
    normal: Vec | None
    radius: float | None
    axis: Vec | None
    edges: list[int]


class EdgeFacts(TypedDict):
    """What one BREP edge is, in the order `shapes` numbers edges. `center` is the point halfway
    along it, `direction` is a line's, `radius` a circle's, and `faces` are the faces it bounds."""

    type: str
    length: float
    center: Vec
    direction: Vec | None
    radius: float | None
    faces: list[int]


class TopologyWire(TypedDict):
    faces: list[FaceFacts]
    edges: list[EdgeFacts]


class TessellatedReport(TypedDict):
    kind: Literal["tessellated"]
    shapes: ShapesWire
    topology: TopologyWire
    solid_faces: list[int]


class UnreadableReport(TypedDict):
    kind: Literal["unreadable"]
    reason: str


type TessellationReport = TessellatedReport | UnreadableReport
