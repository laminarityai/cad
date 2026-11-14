"""Reading a person's STEP or STL file and writing the solids kept from it as a BREP. OCP ships no
stubs, so its modules come through importlib, as in `ocp_handles`."""

import importlib
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol

from cad.checks.container.kernel.protocol import (
    Kept,
    Kernel,
    Shape,
    StepRead,
    Unreadable,
    first_line,
)

MIN_TOLERANCE_MM: Final = 1e-7
MAX_TOLERANCE_MM: Final = 1e-3
SEWING_TOLERANCE_MM: Final = 1e-3
MAX_NAMES: Final = 64
MAX_NAME_CHARS: Final = 120
PLACEHOLDER_NAME: Final = "Open CASCADE STEP translator"


class _Label(Protocol):
    def FindAttribute(self, guid: object, attribute: object) -> bool: ...


class _Labels(Protocol):
    def Length(self) -> int: ...
    def Value(self, index: int) -> _Label: ...


def _ocp(name: str) -> ModuleType:
    return importlib.import_module(f"OCP.{name}")


def read_step(data: bytes) -> StepRead | Unreadable:
    if not data:
        return Unreadable("the file is empty")
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.step"
            path.write_bytes(data)
            return _read_step_file(str(path))
    except Exception as error:
        return Unreadable(f"{type(error).__name__}: {first_line(str(error))}")


def _read_step_file(path: str) -> StepRead | Unreadable:
    _ocp("Interface").Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    reader = _ocp("STEPCAFControl").STEPCAFControl_Reader()
    if reader.ReadFile(path) != _ocp("IFSelect").IFSelect_RetDone:
        return Unreadable("STEPCAFControl_Reader rejected the file as not a readable STEP file")
    application = _ocp("XCAFApp").XCAFApp_Application.GetApplication_s()
    document = _ocp("TDocStd").TDocStd_Document(
        _ocp("TCollection").TCollection_ExtendedString("MDTV-XCAF")
    )
    application.InitDocument(document)
    if not reader.Transfer(document):
        return Unreadable("the STEP file holds nothing the reader can transfer")
    tool = _ocp("XCAFDoc").XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    free = _ocp("TDF").TDF_LabelSequence()
    tool.GetFreeShapes(free)
    shapes = [tool.GetShape_s(free.Value(index)) for index in range(1, free.Length() + 1)]
    shapes = [shape for shape in shapes if not shape.IsNull()]
    if not shapes:
        return Unreadable("the STEP file holds no shape")
    everything = _ocp("TDF").TDF_LabelSequence()
    tool.GetShapes(everything)
    return StepRead(compound(shapes), _names(free, everything))


def _names(*sequences: _Labels) -> tuple[str, ...]:
    attribute = _ocp("TDataStd").TDataStd_Name
    found: dict[str, None] = {}
    for sequence in sequences:
        for index in range(1, sequence.Length() + 1):
            name = attribute()
            if not sequence.Value(index).FindAttribute(attribute.GetID_s(), name):
                continue
            text = " ".join(str(name.Get().ToExtString()).split())
            if text and not text.startswith(PLACEHOLDER_NAME):
                found.setdefault(text[:MAX_NAME_CHARS])
    return tuple(found)[:MAX_NAMES]


def read_stl(kernel: Kernel, data: bytes, scale: float) -> Shape | Unreadable:
    if not data:
        return Unreadable("the file is empty")
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.stl"
            path.write_bytes(data)
            triangles = _ocp("TopoDS").TopoDS_Shape()
            if not _ocp("StlAPI").StlAPI_Reader().Read(triangles, str(path)):
                return Unreadable("StlAPI_Reader rejected the file as not a readable STL file")
        if triangles.IsNull() or not _explore(triangles, "FACE", None):
            return Unreadable("the STL file holds no triangle")
        if scale != 1.0:
            triangles = _scaled(triangles, scale)
        return _solids_from_triangles(kernel, triangles)
    except Exception as error:
        return Unreadable(f"{type(error).__name__}: {first_line(str(error))}")


def _scaled(shape: Shape, factor: float) -> Shape:
    transform = _ocp("gp").gp_Trsf()
    transform.SetScale(_ocp("gp").gp_Pnt(0, 0, 0), factor)
    return _ocp("BRepBuilderAPI").BRepBuilderAPI_Transform(shape, transform, True).Shape()


def _solids_from_triangles(kernel: Kernel, triangles: Shape) -> Shape:
    sewing = _ocp("BRepBuilderAPI").BRepBuilderAPI_Sewing(SEWING_TOLERANCE_MM)
    sewing.Add(triangles)
    sewing.Perform()
    sewn: Shape = sewing.SewedShape()
    made: list[Shape] = []
    for shell in _explore(sewn, "SHELL", None):
        if kernel.edge_uses(shell) == (0, 0):
            maker = _ocp("BRepBuilderAPI").BRepBuilderAPI_MakeSolid(_topods("Shell", shell))
            made.append(maker.Solid())
        else:
            made.append(shell)
    made.extend(_explore(sewn, "FACE", "SHELL"))
    return compound(made)


def keep_solids(kernel: Kernel, shape: Shape) -> Kept:
    free_shells = len(_explore(shape, "SHELL", "SOLID"))
    loose = kernel.outside_solids(shape) - free_shells
    solids = kernel.solids(shape)
    _ocp("ShapeFix").ShapeFix_ShapeTolerance().LimitTolerance(
        shape, MIN_TOLERANCE_MM, MAX_TOLERANCE_MM
    )
    readable = (_readable(kernel, solid) for solid in solids)
    kept = [solid for solid in readable if solid is not None]
    bodies = len(solids) + free_shells
    return Kept(compound(kept) if kept else None, bodies, bodies - len(kept), loose)


def _readable(kernel: Kernel, solid: Shape) -> Shape | None:
    if not kernel.is_valid(solid):
        return None
    if kernel.volume_props(solid).volume < 0:
        fixer = _ocp("ShapeFix").ShapeFix_Solid(_topods("Solid", solid))
        fixer.Perform()
        solid = fixer.Solid()
        if not kernel.is_valid(solid):
            return None
    return solid if kernel.volume_props(solid).volume > 0 else None


def brep_bytes(shape: Shape) -> bytes:
    _ocp("BRepTools").BRepTools.Clean_s(shape)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "kept.brep"
        if not _ocp("BRepTools").BRepTools.Write_s(shape, str(path)):
            raise RuntimeError("BRepTools.Write_s could not write the shape")
        return path.read_bytes()


def compound(shapes: list[Shape]) -> Shape:
    builder = _ocp("BRep").BRep_Builder()
    made = _ocp("TopoDS").TopoDS_Compound()
    builder.MakeCompound(made)
    for shape in shapes:
        builder.Add(made, shape)
    return made


def _topods(kind: str, shape: Shape) -> Shape:
    return getattr(_ocp("TopoDS").TopoDS, f"{kind}_s")(shape)


def _explore(shape: Shape, kind: str, avoid: str | None) -> list[Shape]:
    abstract = _ocp("TopAbs")
    explorer = _ocp("TopExp").TopExp_Explorer(
        shape,
        getattr(abstract, f"TopAbs_{kind}"),
        abstract.TopAbs_SHAPE if avoid is None else getattr(abstract, f"TopAbs_{avoid}"),
    )
    found: list[Shape] = []
    while explorer.More():
        found.append(explorer.Current())
        explorer.Next()
    return found
