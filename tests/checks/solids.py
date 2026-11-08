"""OCP ships no stubs, so its modules come through importlib, as in the kernel."""

import importlib
from collections.abc import Callable
from types import ModuleType
from typing import Any

from cad.checks.container.kernel import Point, Shape

type Solid = Shape


def _ocp(name: str) -> ModuleType:
    return importlib.import_module(f"OCP.{name}")


gp = _ocp("gp")


def box(x: float, y: float, z: float, at: Point = (0, 0, 0)) -> Solid:
    return _ocp("BRepPrimAPI").BRepPrimAPI_MakeBox(gp.gp_Pnt(*at), x, y, z).Shape()


def rod(radius: float, height: float, at: Point, axis: Point = (0, 0, 1)) -> Solid:
    frame = gp.gp_Ax2(gp.gp_Pnt(*at), gp.gp_Dir(*axis))
    return _ocp("BRepPrimAPI").BRepPrimAPI_MakeCylinder(frame, radius, height).Shape()


def cut(solid: Solid, *tools: Solid) -> Solid:
    for tool in tools:
        solid = _ocp("BRepAlgoAPI").BRepAlgoAPI_Cut(solid, tool).Shape()
    return solid


def fuse(solid: Solid, *others: Solid) -> Solid:
    for other in others:
        solid = _ocp("BRepAlgoAPI").BRepAlgoAPI_Fuse(solid, other).Shape()
    return solid


def through_hole(diameter: float, x: float, y: float, depth: float = 5) -> Solid:
    return rod(diameter / 2, depth + 2, (x, y, -1))


def fillet_edges(solid: Solid, radius: float, chosen: Callable[[Point, Point], bool]) -> Solid:
    top_exp, tool = _ocp("TopExp"), _ocp("BRep").BRep_Tool
    maker = _ocp("BRepFilletAPI").BRepFilletAPI_MakeFillet(solid)
    explorer = top_exp.TopExp_Explorer(solid, _ocp("TopAbs").TopAbs_EDGE)
    while explorer.More():
        edge = _ocp("TopoDS").TopoDS.Edge_s(explorer.Current())
        explorer.Next()
        ends = (top_exp.TopExp.FirstVertex_s(edge), top_exp.TopExp.LastVertex_s(edge))
        first, last = (_coords(tool.Pnt_s(end)) for end in ends)
        if chosen(first, last):
            maker.Add(radius, edge)
    maker.Build()
    return maker.Shape()


def turned(solid: Solid, transform: Any) -> Solid:
    return _ocp("BRepBuilderAPI").BRepBuilderAPI_Transform(solid, transform, True).Shape()


def turn_and_move() -> Any:
    rotation = gp.gp_Trsf()
    rotation.SetRotation(gp.gp_Ax1(gp.gp_Pnt(1, 2, 3), gp.gp_Dir(1, 1, 0.3)), 0.7)
    shift = gp.gp_Trsf()
    shift.SetTranslation(gp.gp_Vec(100, -40, 7))
    return shift.Multiplied(rotation)


def apply(transform: Any, point: Point) -> Point:
    return _coords(gp.gp_Pnt(*point).Transformed(transform))


def rotate(transform: Any, vector: Point) -> Point:
    return _coords(gp.gp_Vec(*vector).Transformed(transform))


def _coords(xyz: Any) -> Point:
    return (float(xyz.X()), float(xyz.Y()), float(xyz.Z()))
