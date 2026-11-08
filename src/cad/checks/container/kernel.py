import importlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import NamedTuple, Protocol, cast

STEP_TIME_STAMP = "2000-01-01T00:00:00"
STEP_SCHEMA = "AP214IS"


class Shape(Protocol):
    def IsNull(self) -> bool: ...


class _Point(Protocol):
    def X(self) -> float: ...
    def Y(self) -> float: ...
    def Z(self) -> float: ...


class _Props(Protocol):
    def Mass(self) -> float: ...
    def CentreOfMass(self) -> _Point: ...


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


class _TopoDS(Protocol):
    @staticmethod
    def Edge_s(shape: Shape) -> Shape: ...

    @staticmethod
    def Solid_s(shape: Shape) -> Shape: ...


class _TopExp(Protocol):
    @staticmethod
    def MapShapesAndAncestors_s(
        shape: Shape, of: object, in_: object, into: _AncestorMap
    ) -> None: ...


class _BRepGProp(Protocol):
    @staticmethod
    def VolumeProperties_s(shape: Shape, props: _Props) -> object: ...


class _BRepBndLib(Protocol):
    @staticmethod
    def AddOptimal_s(
        shape: Shape, box: _Box, useTriangulation: bool, useShapeTolerance: bool
    ) -> None: ...


class _InterfaceStatic(Protocol):
    @staticmethod
    def SetCVal_s(name: str, value: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class _Ocp:
    new_shape: Callable[[], Shape]
    new_builder: Callable[[], object]
    new_explorer: Callable[[Shape, object, object], _Explorer]
    new_ancestor_map: Callable[[], _AncestorMap]
    new_props: Callable[[], _Props]
    new_box: Callable[[], _Box]
    new_analyzer: Callable[[Shape], _Analyzer]
    new_common: Callable[[Shape, Shape], _Boolean]
    new_writer: Callable[[], _Writer]
    new_header: Callable[[_Model], _Header]
    new_hstring: Callable[[str], object]
    brep_tool: _BRepTool
    brep_tools: _BRepTools
    topods: _TopoDS
    topexp: _TopExp
    brep_gprop: _BRepGProp
    brep_bnd_lib: _BRepBndLib
    interface_static: _InterfaceStatic
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


def _load_ocp() -> _Ocp:
    topods, brep, top_abs = _module("TopoDS"), _module("BRep"), _module("TopAbs")
    step_control, header = _module("STEPControl"), _module("APIHeaderSection")
    return _Ocp(
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
        new_common=cast(
            Callable[[Shape, Shape], _Boolean], _module("BRepAlgoAPI").BRepAlgoAPI_Common
        ),
        new_writer=cast(Callable[[], _Writer], step_control.STEPControl_Writer),
        new_header=cast(Callable[[_Model], _Header], header.APIHeaderSection_MakeHeader),
        new_hstring=cast(Callable[[str], object], _module("TCollection").TCollection_HAsciiString),
        brep_tool=cast(_BRepTool, brep.BRep_Tool),
        brep_tools=cast(_BRepTools, _module("BRepTools").BRepTools),
        topods=cast(_TopoDS, topods.TopoDS),
        topexp=cast(_TopExp, _module("TopExp").TopExp),
        brep_gprop=cast(_BRepGProp, _module("BRepGProp").BRepGProp),
        brep_bnd_lib=cast(_BRepBndLib, _module("BRepBndLib").BRepBndLib),
        interface_static=cast(_InterfaceStatic, _module("Interface").Interface_Static),
        any_shape=top_abs.TopAbs_SHAPE,
        solid=top_abs.TopAbs_SOLID,
        shell=top_abs.TopAbs_SHELL,
        face=top_abs.TopAbs_FACE,
        edge=top_abs.TopAbs_EDGE,
        vertex=top_abs.TopAbs_VERTEX,
        as_is=step_control.STEPControl_AsIs,
        ret_done=_module("IFSelect").IFSelect_RetDone,
    )


@dataclass(frozen=True, slots=True)
class Unreadable:
    reason: str


@dataclass(frozen=True, slots=True)
class StepTooLarge:
    size: int


class EdgeUses(NamedTuple):
    free: int
    over_used: int


class VolumeProps(NamedTuple):
    volume: float  # signed by orientation
    center: tuple[float, float, float]


class Kernel(Protocol):
    def read_brep(self, data: bytes) -> Shape | Unreadable:
        """Never raises. Random bytes, an empty file and a null shape are all `Unreadable`."""
        ...

    def solids(self, shape: Shape) -> tuple[Shape, ...]: ...

    def outside_solids(self, shape: Shape) -> int:
        """Shells, faces, edges and vertices that no solid of the shape contains."""
        ...

    def is_valid(self, shape: Shape) -> bool: ...

    def edge_uses(self, shape: Shape) -> EdgeUses:
        """A seam edge is two uses by one face and so passes. Degenerated edges
        (BRep_Tool.Degenerated_s) are skipped, because a sphere pole is used once and is not a
        hole."""
        ...

    def volume_props(self, shape: Shape) -> VolumeProps: ...

    def extents(self, shape: Shape) -> tuple[float, float, float] | None:
        """Sizes along x, y and z of the axis-aligned bounding box in the shape's own frame, or
        None when the shape has no bounds or unbounded ones. The box is the tightest the kernel
        computes (BRepBndLib.AddOptimal_s from geometry, not from the mesh, with no tolerance gap
        added)."""
        ...

    def common_volume(self, first: Shape, second: Shape) -> float | None: ...

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        """The writer numbers PRODUCT names per process, so a second call raises: one
        container writes one STEP, which keeps the bytes stable."""
        ...


class OcpKernel:
    def __init__(self) -> None:
        self._ocp = _load_ocp()
        self._wrote_step = False

    def read_brep(self, data: bytes) -> Shape | Unreadable:
        if not data:
            return Unreadable("the BREP is empty")
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "variant.brep"
                path.write_bytes(data)
                shape = self._ocp.new_shape()
                read = self._ocp.brep_tools.Read_s(shape, str(path), self._ocp.new_builder())
        except Exception as error:
            return Unreadable(f"{type(error).__name__}: {first_line(str(error))}")
        if not read or shape.IsNull():
            return Unreadable(f"BRepTools.Read_s rejected {len(data)} bytes as not a BREP file")
        return shape

    def solids(self, shape: Shape) -> tuple[Shape, ...]:
        ocp = self._ocp
        return tuple(map(ocp.topods.Solid_s, self._explore(shape, ocp.solid, ocp.any_shape)))

    def outside_solids(self, shape: Shape) -> int:
        ocp = self._ocp
        nesting = (
            (ocp.shell, ocp.solid),
            (ocp.face, ocp.shell),
            (ocp.edge, ocp.face),
            (ocp.vertex, ocp.edge),
        )
        return sum(len(self._explore(shape, kind, container)) for kind, container in nesting)

    def _explore(self, shape: Shape, kind: object, avoid: object) -> list[Shape]:
        """Every `kind` sub-shape that is not inside an `avoid` sub-shape."""
        found: list[Shape] = []
        explorer = self._ocp.new_explorer(shape, kind, avoid)
        while explorer.More():
            found.append(explorer.Current())
            explorer.Next()
        return found

    def is_valid(self, shape: Shape) -> bool:
        return self._ocp.new_analyzer(shape).IsValid()

    def edge_uses(self, shape: Shape) -> EdgeUses:
        ocp = self._ocp
        edges = ocp.new_ancestor_map()
        ocp.topexp.MapShapesAndAncestors_s(shape, ocp.edge, ocp.face, edges)
        free = over_used = 0
        for index in range(1, edges.Extent() + 1):
            if ocp.brep_tool.Degenerated_s(ocp.topods.Edge_s(edges.FindKey(index))):
                continue
            uses = edges.FindFromIndex(index).Extent()
            free += uses == 1
            over_used += uses > 2
        return EdgeUses(free, over_used)

    def volume_props(self, shape: Shape) -> VolumeProps:
        props = self._ocp.new_props()
        self._ocp.brep_gprop.VolumeProperties_s(shape, props)
        center = props.CentreOfMass()
        return VolumeProps(props.Mass(), (center.X(), center.Y(), center.Z()))

    def extents(self, shape: Shape) -> tuple[float, float, float] | None:
        box = self._ocp.new_box()
        self._ocp.brep_bnd_lib.AddOptimal_s(
            shape, box, useTriangulation=False, useShapeTolerance=False
        )
        if box.IsVoid() or box.IsOpen():
            return None
        x0, y0, z0, x1, y1, z1 = box.Get()
        return (x1 - x0, y1 - y0, z1 - z0)

    def common_volume(self, first: Shape, second: Shape) -> float | None:
        common = self._ocp.new_common(first, second)
        return self.volume_props(common.Shape()).volume if common.IsDone() else None

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        if self._wrote_step:
            raise RuntimeError("one container writes one STEP")
        self._wrote_step = True
        ocp = self._ocp
        ocp.interface_static.SetCVal_s("write.step.schema", STEP_SCHEMA)
        writer = ocp.new_writer()
        transferred = writer.Transfer(shape, ocp.as_is)
        # The default header holds the output path and the clock, so two runs would differ.
        header = ocp.new_header(writer.Model())
        header.SetTimeStamp(ocp.new_hstring(STEP_TIME_STAMP))
        header.SetName(ocp.new_hstring("result"))
        header.SetAuthorValue(1, ocp.new_hstring(""))
        header.SetOrganizationValue(1, ocp.new_hstring(""))
        header.SetOriginatingSystem(ocp.new_hstring("cad"))
        header.SetAuthorisation(ocp.new_hstring(""))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.step"
            if transferred != ocp.ret_done or writer.Write(str(path)) != ocp.ret_done:
                raise RuntimeError("STEPControl_Writer could not write the shape")
            size = path.stat().st_size
            return StepTooLarge(size) if size > cap else path.read_bytes()


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "no message")


def ocp_kernel() -> Kernel:
    return OcpKernel()
