"""What each face and edge of a shape is, numbered as `tessellate._mesh` numbers them."""

import importlib
import math
from collections.abc import Callable, Sequence
from typing import Final, Protocol, cast

from cad.geometry.container.wire import EdgeFacts, FaceFacts, TopologyWire, Vec

DECIMALS: Final = 4


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


class _Edge(Protocol):
    @property
    def geom_type(self) -> _GeomType: ...
    @property
    def length(self) -> float: ...
    @property
    def radius(self) -> float: ...
    def position_at(self, distance: float) -> _Vector: ...
    def tangent_at(self, position: float) -> _Vector: ...
    def __hash__(self) -> int: ...
    def __eq__(self, other: object) -> bool: ...


class _Face(Protocol):
    @property
    def wrapped(self) -> object: ...
    @property
    def geom_type(self) -> _GeomType: ...
    @property
    def area(self) -> float: ...
    def center(self) -> _Vector: ...
    def normal_at(self, point: _Vector) -> _Vector: ...
    def edges(self) -> Sequence[_Edge]: ...


class Shape(Protocol):
    def faces(self) -> Sequence[_Face]: ...
    def edges(self) -> Sequence[_Edge]: ...


class _Direction(Protocol):
    def X(self) -> float: ...
    def Y(self) -> float: ...
    def Z(self) -> float: ...


class _Axis(Protocol):
    def Direction(self) -> _Direction: ...


class _Round(Protocol):
    def Axis(self) -> _Axis: ...


class _Cylinder(_Round, Protocol):
    def Radius(self) -> float: ...


class _Cone(_Round, Protocol):
    def RefRadius(self) -> float: ...


class _Sphere(_Round, Protocol):
    def Radius(self) -> float: ...


class _Torus(_Round, Protocol):
    def MajorRadius(self) -> float: ...


class _Adaptor(Protocol):
    def Cylinder(self) -> _Cylinder: ...
    def Cone(self) -> _Cone: ...
    def Sphere(self) -> _Sphere: ...
    def Torus(self) -> _Torus: ...


def topology(shape: Shape) -> TopologyWire:
    faces, edges = shape.faces(), shape.edges()
    edge_index = {edge: index for index, edge in enumerate(edges)}
    faces_of: list[list[int]] = [[] for _ in edges]
    face_facts: list[FaceFacts] = []
    for index, face in enumerate(faces):
        bounding = sorted({edge_index[edge] for edge in face.edges()})
        for edge in bounding:
            faces_of[edge].append(index)
        face_facts.append(_face(face, bounding))
    return {"faces": face_facts, "edges": [_edge(e, faces_of[i]) for i, e in enumerate(edges)]}


def _face(face: _Face, bounding: list[int]) -> FaceFacts:
    kind = face.geom_type.name
    center = face.center()
    radius, axis = _round(face, kind)
    return {
        "type": kind,
        "area": _r(face.area),
        "center": _vec(center),
        "normal": _attempt(lambda: _unit(face.normal_at(center))),
        "radius": radius,
        "axis": axis,
        "edges": bounding,
    }


def _edge(edge: _Edge, bounding: list[int]) -> EdgeFacts:
    kind = edge.geom_type.name
    return {
        "type": kind,
        "length": _r(edge.length),
        "center": _vec(edge.position_at(0.5)),
        "direction": _attempt(lambda: _unit(edge.tangent_at(0.5))) if kind == "LINE" else None,
        "radius": _attempt(lambda: _r(edge.radius)) if kind == "CIRCLE" else None,
        "faces": bounding,
    }


def _round(face: _Face, kind: str) -> tuple[float | None, Vec | None]:
    """The radius and axis of a cylinder, cone, sphere or torus, read from the OCCT surface."""
    surface = _SURFACES.get(kind)
    if surface is None:
        return None, None

    def read() -> tuple[float | None, Vec | None]:
        ocp = importlib.import_module("OCP.BRepAdaptor")
        adaptor = cast(_Adaptor, ocp.BRepAdaptor_Surface(face.wrapped))
        round_surface, radius = surface(adaptor)
        axis = round_surface.Axis().Direction()
        return _r(radius), _unit_xyz(axis.X(), axis.Y(), axis.Z())

    return _attempt(read) or (None, None)


_SURFACES: Final[dict[str, Callable[[_Adaptor], tuple[_Round, float]]]] = {
    "CYLINDER": lambda a: (a.Cylinder(), a.Cylinder().Radius()),
    "CONE": lambda a: (a.Cone(), a.Cone().RefRadius()),
    "SPHERE": lambda a: (a.Sphere(), a.Sphere().Radius()),
    "TORUS": lambda a: (a.Torus(), a.Torus().MajorRadius()),
}


def _attempt[T](read: Callable[[], T]) -> T | None:
    """A fact OCCT cannot give for one entity is None; it never fails the tessellation."""
    try:
        return read()
    except Exception:
        return None


def _r(value: float) -> float:
    return round(value, DECIMALS) + 0.0


def _vec(vector: _Vector) -> Vec:
    return (_r(vector.X), _r(vector.Y), _r(vector.Z))


def _unit(vector: _Vector) -> Vec:
    return _unit_xyz(vector.X, vector.Y, vector.Z)


def _unit_xyz(x: float, y: float, z: float) -> Vec:
    length = math.sqrt(x * x + y * y + z * z)
    if length == 0.0:
        raise ValueError("a zero vector has no direction")
    return (_r(x / length), _r(y / length), _r(z / length))
