"""Rays through one solid's material, for the min_wall check.

Each face gets its own IntCurvesFace_Intersector, and a tree of the faces' bounding boxes sends a
ray only to the faces whose boxes it passes through, nearest first. Asking every face of a large
part, as IntCurvesFace_ShapeIntersector does, costs time in proportion to the face count."""

import heapq
import importlib
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

from cad.checks.container.kernel.ocp_handles import Ocp, Xyz
from cad.checks.container.kernel.protocol import (
    Across,
    Glancing,
    Lost,
    Patch,
    Reading,
    Shape,
)
from cad.checks.container.vectors import Point, dot, norm, scale

OPPOSED = 0.5
"""cos 60 degrees: the exit face must look back at the start face at least this squarely."""
GRAZING = 1e-9
START_GAP_MM = 1e-7
"""The ray starts this far along, so the start face does not count as its exit."""
INTERSECT_TOL_MM = 1e-9
BOX_GAP_MM = 1e-6
LEAF_FACES = 4
LENGTH_STEPS = 8

type Box = tuple[Point, Point]


class _Intersector(Protocol):
    def Perform(self, line: object, low: float, high: float) -> None: ...
    def IsDone(self) -> bool: ...
    def NbPnt(self) -> int: ...
    def WParameter(self, index: int) -> float: ...
    def UParameter(self, index: int) -> float: ...
    def VParameter(self, index: int) -> float: ...
    def ClassifyUVPoint(self, point: object) -> object: ...


class _FaceProps(Protocol):
    def Normal(self, u: float, v: float, point: Xyz, normal: Xyz) -> None: ...


@dataclass(frozen=True, slots=True)
class _Node:
    box: Box
    faces: tuple[int, ...]
    kids: tuple["_Node", ...]


@dataclass(frozen=True, slots=True)
class _Face:
    intersector: _Intersector
    props: _FaceProps
    patch: Patch


class OcpWalls:
    def __init__(self, ocp: Ocp, shape: Shape) -> None:
        intersect = importlib.import_module("OCP.IntCurvesFace")
        gp = importlib.import_module("OCP.gp")
        self._ocp = ocp
        self._new_line = cast(Callable[[Xyz, object], object], gp.gp_Lin)
        self._new_uv = cast(Callable[[float, float], object], gp.gp_Pnt2d)
        self._inside = importlib.import_module("OCP.TopAbs").TopAbs_IN
        new_intersector = cast(
            Callable[[Shape, float], _Intersector], intersect.IntCurvesFace_Intersector
        )
        faces: list[_Face] = []
        boxes: list[tuple[Box, int]] = []
        explorer = ocp.new_explorer(shape, ocp.face, ocp.any_shape)
        while explorer.More():
            face = ocp.topods.Face_s(explorer.Current())
            explorer.Next()
            props = cast(_FaceProps, ocp.new_face_props(face))
            faces.append(_Face(new_intersector(face, INTERSECT_TOL_MM), props, _patch(ocp, face)))
            boxes.append((_box(ocp, face), len(boxes)))
        self._faces = tuple(faces)
        self._tree = _build(boxes)

    @property
    def patches(self) -> tuple[Patch, ...]:
        return tuple(face.patch for face in self._faces)

    def reading(self, face: int, u: float, v: float) -> Reading | None:
        start = self._faces[face]
        if start.intersector.ClassifyUVPoint(self._new_uv(u, v)) != self._inside:
            return None
        found = _point_normal(self._ocp, start.props, u, v)
        if found is None:
            return None
        origin, outward = found
        return self._cast(origin, scale(outward, -1))

    def _cast(self, origin: Point, way: Point) -> Reading:
        ocp = self._ocp
        line = self._new_line(ocp.new_point(*origin), ocp.new_direction(*way))
        inverse = tuple(math.inf if c == 0 else 1 / c for c in way)
        best, facing = math.inf, 0.0
        queue: list[tuple[float, int, _Node]] = [(0.0, 0, self._tree)]
        pushed = 1
        while queue:
            near, _, node = heapq.heappop(queue)
            if near >= best:
                break
            for index in node.faces:
                face = self._faces[index]
                face.intersector.Perform(line, START_GAP_MM, best)
                if not face.intersector.IsDone():
                    return Lost("IntCurvesFace_Intersector did not finish a ray")
                for hit in range(1, face.intersector.NbPnt() + 1):
                    along = face.intersector.WParameter(hit)
                    if along >= best:
                        continue
                    exit = _point_normal(
                        ocp,
                        face.props,
                        face.intersector.UParameter(hit),
                        face.intersector.VParameter(hit),
                    )
                    if exit is not None and dot(exit[1], way) > GRAZING:
                        best, facing = along, dot(exit[1], way)
            for kid in node.kids:
                entry = _entry(kid.box, origin, inverse)
                if entry is not None and entry < best:
                    heapq.heappush(queue, (entry, pushed, kid))
                    pushed += 1
        if best == math.inf:
            return Lost("a ray into the material never came out of it")
        return Across(best) if facing >= OPPOSED else Glancing()


def _point_normal(ocp: Ocp, props: _FaceProps, u: float, v: float) -> tuple[Point, Point] | None:
    point, normal = ocp.new_point(0, 0, 0), ocp.new_vector(0, 0, 0)
    props.Normal(u, v, point, normal)
    outward = (normal.X(), normal.Y(), normal.Z())
    size = norm(outward)
    if size < 1e-12:
        return None
    return (point.X(), point.Y(), point.Z()), scale(outward, 1 / size)


def _patch(ocp: Ocp, face: Shape) -> Patch:
    u0, u1, v0, v1 = ocp.brep_tools.UVBounds_s(face)
    props = cast(_FaceProps, ocp.new_face_props(face))

    def at(u: float, v: float) -> Point:
        point, normal = ocp.new_point(0, 0, 0), ocp.new_vector(0, 0, 0)
        props.Normal(u, v, point, normal)
        return (point.X(), point.Y(), point.Z())

    def run(points: list[Point]) -> float:
        return sum(norm(_minus(b, a)) for a, b in itertools.pairwise(points))

    steps = [k / LENGTH_STEPS for k in range(LENGTH_STEPS + 1)]
    across = (0.25, 0.5, 0.75)
    length_u = max(run([at(u0 + s * (u1 - u0), v0 + f * (v1 - v0)) for s in steps]) for f in across)
    length_v = max(run([at(u0 + f * (u1 - u0), v0 + s * (v1 - v0)) for s in steps]) for f in across)
    return Patch(u0, u1, v0, v1, length_u, length_v)


def _minus(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _box(ocp: Ocp, face: Shape) -> Box:
    box = ocp.new_box()
    ocp.brep_bnd_lib.AddOptimal_s(face, box, useTriangulation=False, useShapeTolerance=False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    gap = BOX_GAP_MM
    return (x0 - gap, y0 - gap, z0 - gap), (x1 + gap, y1 + gap, z1 + gap)


def _build(boxes: list[tuple[Box, int]]) -> _Node:
    low = tuple(min(box[0][k] for box, _ in boxes) for k in range(3))
    high = tuple(max(box[1][k] for box, _ in boxes) for k in range(3))
    bounds: Box = ((low[0], low[1], low[2]), (high[0], high[1], high[2]))
    if len(boxes) <= LEAF_FACES:
        return _Node(bounds, tuple(index for _, index in boxes), ())
    axis = max(range(3), key=lambda k: high[k] - low[k])
    ordered = sorted(boxes, key=lambda item: (item[0][0][axis] + item[0][1][axis], item[1]))
    half = len(ordered) // 2
    return _Node(bounds, (), (_build(ordered[:half]), _build(ordered[half:])))


def _entry(box: Box, origin: Point, inverse: tuple[float, ...]) -> float | None:
    """Where the ray first enters the box, by the slab test, or None when it misses it."""
    near, far = 0.0, math.inf
    for k in range(3):
        if math.isinf(inverse[k]):
            if not box[0][k] <= origin[k] <= box[1][k]:
                return None
            continue
        a = (box[0][k] - origin[k]) * inverse[k]
        b = (box[1][k] - origin[k]) * inverse[k]
        near, far = max(near, min(a, b)), min(far, max(a, b))
        if near > far:
            return None
    return near
