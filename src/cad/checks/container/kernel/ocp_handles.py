import importlib
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Protocol, cast

from cad.checks.container.kernel.protocol import Shape


class Xyz(Protocol):
    def X(self) -> float: ...
    def Y(self) -> float: ...
    def Z(self) -> float: ...


class _Principal(Protocol):
    def Moments(self) -> tuple[float, float, float]: ...
    def FirstAxisOfInertia(self) -> Xyz: ...
    def SecondAxisOfInertia(self) -> Xyz: ...


class _Props(Protocol):
    def Mass(self) -> float: ...
    def CentreOfMass(self) -> Xyz: ...
    def PrincipalProperties(self) -> _Principal: ...


class _Axis(Protocol):
    def Location(self) -> Xyz: ...
    def Direction(self) -> Xyz: ...


class _Cylinder(Protocol):
    def Position(self) -> _Axis: ...
    def Radius(self) -> float: ...


class _Adaptor(Protocol):
    def GetType(self) -> object: ...
    def Cylinder(self) -> _Cylinder: ...


class _FaceProps(Protocol):
    def Normal(self, u: float, v: float, point: Xyz, normal: Xyz) -> None: ...


class _Trsf(Protocol):
    def SetTransformation(self, to: object) -> None: ...


class Movable(Protocol):
    def Moved(self, location: object) -> Shape: ...


class _Explorer(Protocol):
    def More(self) -> bool: ...
    def Current(self) -> Shape: ...
    def Next(self) -> None: ...


class _ShapeList(Protocol):
    def Extent(self) -> int: ...


class _AncestorMap(Protocol):
    def Extent(self) -> int: ...
    def FindKey(self, index: int) -> Shape: ...
    def FindFromIndex(self, index: int) -> _ShapeList: ...


class _Analyzer(Protocol):
    def IsValid(self) -> bool: ...


class _Box(Protocol):
    def IsVoid(self) -> bool: ...
    def IsOpen(self) -> bool: ...
    def Get(self) -> tuple[float, float, float, float, float, float]: ...


class _Tolerance(Protocol):
    def Tolerance(self, shape: Shape, mode: int) -> float:
        """A positive mode gives the largest tolerance, 0 the mean, a negative one the smallest."""
        ...


class _Boolean(Protocol):
    def IsDone(self) -> bool: ...
    def Shape(self) -> Shape: ...


class _Model(Protocol): ...


class _Writer(Protocol):
    def Model(self) -> _Model: ...
    def Transfer(self, shape: Shape, mode: object) -> object: ...
    def Write(self, path: str) -> object: ...


class _Header(Protocol):
    def SetTimeStamp(self, stamp: object) -> None: ...
    def SetName(self, name: object) -> None: ...
    def SetAuthorValue(self, index: int, author: object) -> None: ...
    def SetOrganizationValue(self, index: int, organization: object) -> None: ...
    def SetOriginatingSystem(self, system: object) -> None: ...
    def SetAuthorisation(self, authorisation: object) -> None: ...


class _BRepTool(Protocol):
    @staticmethod
    def Degenerated_s(edge: Shape) -> bool: ...


class _BRepTools(Protocol):
    @staticmethod
    def Read_s(shape: Shape, path: str, builder: object) -> bool: ...

    @staticmethod
    def UVBounds_s(face: Shape) -> tuple[float, float, float, float]: ...


class _TopoDS(Protocol):
    @staticmethod
    def Edge_s(shape: Shape) -> Shape: ...

    @staticmethod
    def Solid_s(shape: Shape) -> Shape: ...

    @staticmethod
    def Face_s(shape: Shape) -> Shape: ...


class _TopExp(Protocol):
    @staticmethod
    def MapShapesAndAncestors_s(
        shape: Shape, of: object, in_: object, into: _AncestorMap
    ) -> None: ...


class _BRepGProp(Protocol):
    @staticmethod
    def VolumeProperties_s(shape: Shape, props: _Props) -> object: ...

    @staticmethod
    def SurfaceProperties_s(shape: Shape, props: _Props) -> object: ...


class _BRepBndLib(Protocol):
    @staticmethod
    def AddOptimal_s(
        shape: Shape, box: _Box, useTriangulation: bool, useShapeTolerance: bool
    ) -> None: ...


class _InterfaceStatic(Protocol):
    @staticmethod
    def SetCVal_s(name: str, value: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class Ocp:
    new_shape: Callable[[], Shape]
    new_builder: Callable[[], object]
    new_explorer: Callable[[Shape, object, object], _Explorer]
    new_ancestor_map: Callable[[], _AncestorMap]
    new_props: Callable[[], _Props]
    new_box: Callable[[], _Box]
    new_analyzer: Callable[[Shape], _Analyzer]
    new_tolerance: Callable[[], _Tolerance]
    new_common: Callable[[Shape, Shape], _Boolean]
    new_writer: Callable[[], _Writer]
    new_header: Callable[[_Model], _Header]
    new_hstring: Callable[[str], object]
    new_adaptor: Callable[[Shape], _Adaptor]
    new_face_props: Callable[[Shape], _FaceProps]
    new_point: Callable[[float, float, float], Xyz]
    new_vector: Callable[[float, float, float], Xyz]
    new_direction: Callable[[float, float, float], object]
    new_frame: Callable[[Xyz, object, object], object]
    new_trsf: Callable[[], _Trsf]
    new_location: Callable[[_Trsf], object]
    brep_tool: _BRepTool
    brep_tools: _BRepTools
    topods: _TopoDS
    topexp: _TopExp
    brep_gprop: _BRepGProp
    brep_bnd_lib: _BRepBndLib
    interface_static: _InterfaceStatic
    plane: object
    cylinder: object
    any_shape: object
    solid: object
    shell: object
    face: object
    edge: object
    vertex: object
    as_is: object
    ret_done: object


def _module(name: str) -> ModuleType:
    return importlib.import_module(f"OCP.{name}")


def load_ocp() -> Ocp:
    topods, brep, top_abs = _module("TopoDS"), _module("BRep"), _module("TopAbs")
    gp, geom_abs = _module("gp"), _module("GeomAbs")
    step_control, header = _module("STEPControl"), _module("APIHeaderSection")
    return Ocp(
        new_shape=cast(Callable[[], Shape], topods.TopoDS_Shape),
        new_builder=cast(Callable[[], object], brep.BRep_Builder),
        new_explorer=cast(
            Callable[[Shape, object, object], _Explorer], _module("TopExp").TopExp_Explorer
        ),
        new_ancestor_map=cast(
            Callable[[], _AncestorMap],
            _module("TopTools").TopTools_IndexedDataMapOfShapeListOfShape,
        ),
        new_props=cast(Callable[[], _Props], _module("GProp").GProp_GProps),
        new_box=cast(Callable[[], _Box], _module("Bnd").Bnd_Box),
        new_analyzer=cast(Callable[[Shape], _Analyzer], _module("BRepCheck").BRepCheck_Analyzer),
        new_tolerance=cast(
            Callable[[], _Tolerance], _module("ShapeAnalysis").ShapeAnalysis_ShapeTolerance
        ),
        new_common=cast(
            Callable[[Shape, Shape], _Boolean], _module("BRepAlgoAPI").BRepAlgoAPI_Common
        ),
        new_writer=cast(Callable[[], _Writer], step_control.STEPControl_Writer),
        new_header=cast(Callable[[_Model], _Header], header.APIHeaderSection_MakeHeader),
        new_hstring=cast(Callable[[str], object], _module("TCollection").TCollection_HAsciiString),
        new_adaptor=cast(Callable[[Shape], _Adaptor], _module("BRepAdaptor").BRepAdaptor_Surface),
        new_face_props=cast(Callable[[Shape], _FaceProps], _module("BRepGProp").BRepGProp_Face),
        new_point=cast(Callable[[float, float, float], Xyz], gp.gp_Pnt),
        new_vector=cast(Callable[[float, float, float], Xyz], gp.gp_Vec),
        new_direction=cast(Callable[[float, float, float], object], gp.gp_Dir),
        new_frame=cast(Callable[[Xyz, object, object], object], gp.gp_Ax3),
        new_trsf=cast(Callable[[], _Trsf], gp.gp_Trsf),
        new_location=cast(Callable[[_Trsf], object], _module("TopLoc").TopLoc_Location),
        brep_tool=cast(_BRepTool, brep.BRep_Tool),
        brep_tools=cast(_BRepTools, _module("BRepTools").BRepTools),
        topods=cast(_TopoDS, topods.TopoDS),
        topexp=cast(_TopExp, _module("TopExp").TopExp),
        brep_gprop=cast(_BRepGProp, _module("BRepGProp").BRepGProp),
        brep_bnd_lib=cast(_BRepBndLib, _module("BRepBndLib").BRepBndLib),
        interface_static=cast(_InterfaceStatic, _module("Interface").Interface_Static),
        plane=geom_abs.GeomAbs_Plane,
        cylinder=geom_abs.GeomAbs_Cylinder,
        any_shape=top_abs.TopAbs_SHAPE,
        solid=top_abs.TopAbs_SOLID,
        shell=top_abs.TopAbs_SHELL,
        face=top_abs.TopAbs_FACE,
        edge=top_abs.TopAbs_EDGE,
        vertex=top_abs.TopAbs_VERTEX,
        as_is=step_control.STEPControl_AsIs,
        ret_done=_module("IFSelect").IFSelect_RetDone,
    )
