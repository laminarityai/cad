import importlib
import itertools
import math
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Protocol, cast

from cad.checks.container.channel import serve
from cad.geometry.container.topology import Shape, topology
from cad.geometry.container.wire import (
    BoundingBoxWire,
    Location,
    PartWire,
    ShapesWire,
    ShapeWire,
    TessellationReport,
)

RELATIVE_TOLERANCE: Final = 0.0005
MIN_TOLERANCE_MM: Final = 0.001
ANGULAR_TOLERANCE: Final = 0.1
COLOR: Final = "#e8b024"
ORIGIN: Final[Location] = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
# three-cad-viewer numbers face and edge types as OCCT's GeomAbs enums do.
FACE_TYPES: Final = {
    name: index
    for index, name in enumerate(
        [
            "PLANE",
            "CYLINDER",
            "CONE",
            "SPHERE",
            "TORUS",
            "BEZIER",
            "BSPLINE",
            "REVOLUTION",
            "EXTRUSION",
            "OFFSET",
            "OTHER",
        ]
    )
}
EDGE_TYPES: Final = {
    name: index
    for index, name in enumerate(
        [
            "LINE",
            "CIRCLE",
            "ELLIPSE",
            "HYPERBOLA",
            "PARABOLA",
            "BEZIER",
            "BSPLINE",
            "OFFSET",
            "OTHER",
        ]
    )
}


class _Vector(Protocol):
    @property
    def X(self) -> float: ...
    @property
    def Y(self) -> float: ...
    @property
    def Z(self) -> float: ...


class _GeomType(Protocol):
    @property
    def name(self) -> str: ...


class _Box(Protocol):
    @property
    def min(self) -> _Vector: ...
    @property
    def max(self) -> _Vector: ...


class _Face(Protocol):
    @property
    def geom_type(self) -> _GeomType: ...
    def tessellate(
        self, tolerance: float, angular_tolerance: float
    ) -> tuple[list[_Vector], list[tuple[int, int, int]]]: ...


class _Edge(Protocol):
    @property
    def geom_type(self) -> _GeomType: ...
    def positions(self, *, deflection: float) -> list[_Vector]: ...


class _Shape(Protocol):
    def mesh(self, tolerance: float, angular_tolerance: float) -> None: ...
    def faces(self) -> Sequence[_Face]: ...
    def edges(self) -> Sequence[_Edge]: ...
    def vertices(self) -> Sequence[_Vector]: ...
    def bounding_box(self) -> _Box: ...


class _Build123d(Protocol):
    def import_brep(self, file_name: str) -> _Shape: ...


def main() -> None:
    serve(lambda args, brep: tessellate(brep))


def tessellate(brep: bytes) -> TessellationReport:
    if not brep:
        return {"kind": "unreadable", "reason": "the BREP is empty"}
    build123d = cast(_Build123d, importlib.import_module("build123d"))
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variant.brep"
            path.write_bytes(brep)
            shape = build123d.import_brep(str(path))
        return {
            "kind": "tessellated",
            "shapes": _shapes(shape),
            "topology": topology(cast(Shape, shape)),
        }
    except Exception as error:
        return {"kind": "unreadable", "reason": f"{type(error).__name__}: {error}"}


def _shapes(shape: _Shape) -> ShapesWire:
    box = _bounding_box(shape.bounding_box())
    extent = max(box["xmax"] - box["xmin"], box["ymax"] - box["ymin"], box["zmax"] - box["zmin"])
    tolerance = max(extent * RELATIVE_TOLERANCE, MIN_TOLERANCE_MM)
    shape.mesh(tolerance, ANGULAR_TOLERANCE)
    part: PartWire = {
        "version": 3,
        "id": "/variant/part",
        "name": "part",
        "type": "shapes",
        "subtype": "solid",
        "shape": _mesh(shape, tolerance),
        "state": (1, 1),
        "color": COLOR,
        "alpha": 1.0,
        "texture": None,
        "loc": ORIGIN,
        "renderback": False,
        "accuracy": tolerance,
        "bb": None,
    }
    return {
        "version": 3,
        "id": "/variant",
        "name": "variant",
        "parts": [part],
        "loc": ORIGIN,
        "normal_len": 0,
        "bb": box,
    }


def _mesh(shape: _Shape, tolerance: float) -> ShapeWire:
    mesh: ShapeWire = {
        "vertices": [],
        "normals": [],
        "triangles": [],
        "triangles_per_face": [],
        "face_types": [],
        "edges": [],
        "segments_per_edge": [],
        "edge_types": [],
        "obj_vertices": [],
    }
    for face in shape.faces():
        points, triangles = face.tessellate(tolerance, ANGULAR_TOLERANCE)
        offset = len(mesh["vertices"]) // 3
        mesh["vertices"] += _flat(points)
        mesh["normals"] += _normals(points, triangles)
        mesh["triangles"] += [offset + index for triangle in triangles for index in triangle]
        mesh["triangles_per_face"].append(len(triangles))
        mesh["face_types"].append(FACE_TYPES.get(face.geom_type.name, FACE_TYPES["OTHER"]))
    for edge in shape.edges():
        points = edge.positions(deflection=tolerance)
        for start, end in itertools.pairwise(points):
            mesh["edges"] += _flat((start, end))
        mesh["segments_per_edge"].append(max(len(points) - 1, 0))
        mesh["edge_types"].append(EDGE_TYPES.get(edge.geom_type.name, EDGE_TYPES["OTHER"]))
    mesh["obj_vertices"] = _flat(shape.vertices())
    return mesh


def _normals(points: Sequence[_Vector], triangles: Sequence[tuple[int, int, int]]) -> list[float]:
    """Each vertex's normal is the area-weighted sum of its triangles' normals, so it points out
    of the solid wherever the triangles are wound outward."""
    sums = [[0.0, 0.0, 0.0] for _ in points]
    for triangle in triangles:
        a, b, c = (points[index] for index in triangle)
        u = (b.X - a.X, b.Y - a.Y, b.Z - a.Z)
        v = (c.X - a.X, c.Y - a.Y, c.Z - a.Z)
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        for index in triangle:
            for axis in range(3):
                sums[index][axis] += n[axis]
    normals: list[float] = []
    for x, y, z in sums:
        length = math.sqrt(x * x + y * y + z * z) or 1.0
        normals += (x / length, y / length, z / length)
    return normals


def _flat(points: Sequence[_Vector]) -> list[float]:
    return [axis for point in points for axis in (point.X, point.Y, point.Z)]


def _bounding_box(box: _Box) -> BoundingBoxWire:
    return {
        "xmin": box.min.X,
        "xmax": box.max.X,
        "ymin": box.min.Y,
        "ymax": box.max.Y,
        "zmin": box.min.Z,
        "zmax": box.max.Z,
    }
