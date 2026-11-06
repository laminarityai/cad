"""Kernel-neutral fingerprint of a STEP file, read with OCP only.

A fingerprint lists each solid with its volume, bounding box, validity and the analytic
surfaces it is made of. Faces that lie on one surface are merged and their areas summed,
so two libraries that split a face differently still give the same fingerprint.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import (
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_Torus,
)
from OCP.gp import gp_Dir, gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape, TopoDS_Shell, TopoDS_Solid

Kind = Literal["plane", "cylinder", "cone", "sphere", "torus", "other"]
Vec3 = tuple[float, float, float]

KEY_DIGITS = 4


@dataclass(frozen=True, slots=True)
class Surface:
    """One analytic surface of one solid and the total face area that lies on it.

    `params` are canonical, so equal surfaces have equal params whatever the library:
    plane (normal, offset), cylinder (radius, axis direction, axis point nearest the
    origin), cone (half angle, axis direction, apex), sphere (radius, center), torus
    (major radius, minor radius, axis direction, center), other (face centroid).
    """

    solid: int
    kind: Kind
    params: tuple[float, ...]
    area: float

    def describe(self) -> str:
        values = ", ".join(f"{p:.3f}" for p in self.params)
        return f"{self.kind}({values}) area {self.area:.2f} on solid {self.solid}"


@dataclass(frozen=True, slots=True)
class Solid:
    index: int
    volume: float
    lo: Vec3
    hi: Vec3
    valid: bool
    closed: bool
    surfaces: tuple[Surface, ...]
    shape: TopoDS_Solid


@dataclass(frozen=True, slots=True)
class Model:
    solids: tuple[Solid, ...]

    @property
    def surfaces(self) -> list[Surface]:
        return [s for solid in self.solids for s in solid.surfaces]


def load(path: Path) -> Model | None:
    """Read a STEP file. None means the file is missing or unreadable."""
    if not path.is_file():
        return None
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        return None
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        return None
    return fingerprint(shape)


def fingerprint(shape: TopoDS_Shape) -> Model:
    solids = [TopoDS.Solid_s(s) for s in explore(shape, TopAbs_SOLID)]
    return Model(tuple(solid_print(i, solid) for i, solid in enumerate(solids)))


def explore(shape: TopoDS_Shape, kind: TopAbs_ShapeEnum) -> list[TopoDS_Shape]:
    found: list[TopoDS_Shape] = []
    explorer = TopExp_Explorer(shape, kind)
    while explorer.More():
        found.append(explorer.Current())
        explorer.Next()
    return found


def solid_print(index: int, solid: TopoDS_Solid) -> Solid:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(solid, box, False, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    shells: list[TopoDS_Shell] = [TopoDS.Shell_s(s) for s in explore(solid, TopAbs_SHELL)]
    return Solid(
        index=index,
        volume=props.Mass(),
        lo=(x0, y0, z0),
        hi=(x1, y1, z1),
        valid=BRepCheck_Analyzer(solid).IsValid(),
        closed=bool(shells) and all(BRep_Tool.IsClosed_s(s) for s in shells),
        surfaces=merged_surfaces(index, solid),
        shape=solid,
    )


def merged_surfaces(index: int, solid: TopoDS_Solid) -> tuple[Surface, ...]:
    areas: dict[tuple[Kind, tuple[float, ...]], float] = {}
    for face_shape in explore(solid, TopAbs_FACE):
        face = TopoDS.Face_s(face_shape)
        kind, params = surface_key(face)
        key = (kind, tuple(round(p, KEY_DIGITS) + 0.0 for p in params))
        areas[key] = areas.get(key, 0.0) + face_area(face)
    return tuple(
        Surface(index, kind, params, area) for (kind, params), area in sorted(areas.items())
    )


def face_area(face: TopoDS_Face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.Mass()


def surface_key(face: TopoDS_Face) -> tuple[Kind, tuple[float, ...]]:
    surface = BRepAdaptor_Surface(face)
    kind = surface.GetType()
    if kind == GeomAbs_Plane:
        plane = surface.Plane()
        normal = canonical(plane.Axis().Direction())
        return "plane", (*normal, dot(normal, point(plane.Location())))
    if kind == GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        axis = canonical(cylinder.Axis().Direction())
        return "cylinder", (cylinder.Radius(), *axis, *foot(point(cylinder.Location()), axis))
    if kind == GeomAbs_Cone:
        cone = surface.Cone()
        axis = canonical(cone.Axis().Direction())
        return "cone", (abs(cone.SemiAngle()), *axis, *point(cone.Apex()))
    if kind == GeomAbs_Sphere:
        sphere = surface.Sphere()
        return "sphere", (sphere.Radius(), *point(sphere.Location()))
    if kind == GeomAbs_Torus:
        torus = surface.Torus()
        axis = canonical(torus.Axis().Direction())
        center = point(torus.Location())
        return "torus", (torus.MajorRadius(), torus.MinorRadius(), *axis, *center)
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return "other", point(props.CentreOfMass())


def canonical(direction: gp_Dir) -> Vec3:
    """Flip a direction so its first clearly nonzero component is positive."""
    v = (direction.X(), direction.Y(), direction.Z())
    first = next(c for c in v if abs(c) > 1e-9)
    return v if first > 0 else (-v[0], -v[1], -v[2])


def point(p: gp_Pnt) -> Vec3:
    return (p.X(), p.Y(), p.Z())


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def foot(location: Vec3, axis: Vec3) -> Vec3:
    """The point on the axis line through `location` that is nearest the origin."""
    s = dot(location, axis)
    return (location[0] - s * axis[0], location[1] - s * axis[1], location[2] - s * axis[2])


def boxes_overlap(a: Solid, b: Solid) -> bool:
    return all(a.lo[i] < b.hi[i] and b.lo[i] < a.hi[i] for i in range(3))


def common_volume(a: Solid, b: Solid) -> float:
    """Volume two solids share. Solids that only touch share zero volume."""
    if not boxes_overlap(a, b):
        return 0.0
    common = BRepAlgoAPI_Common(a.shape, b.shape)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(common.Shape(), props)
    return max(props.Mass(), 0.0)


def distance(a: Vec3, b: Vec3) -> float:
    return math.dist(a, b)
