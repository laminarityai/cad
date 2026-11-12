"""STEP and STL files written in code, the way a person's CAD tool would write them."""

import importlib
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from cad.checks.container.kernel import Shape


def _ocp(name: str) -> ModuleType:
    return importlib.import_module(f"OCP.{name}")


def step_bytes(shape: Shape, unit: str = "MM") -> bytes:
    """The shape, which is in millimetres, written into a STEP file that declares `unit`."""
    statics = _ocp("Interface").Interface_Static
    statics.SetCVal_s("write.step.unit", unit)
    try:
        writer = _ocp("STEPControl").STEPControl_Writer()
        writer.Transfer(shape, _ocp("STEPControl").STEPControl_AsIs)
        return _written(writer.Write, "part.step")
    finally:
        statics.SetCVal_s("write.step.unit", "MM")


def named_step_bytes(shape: Shape, name: str) -> bytes:
    application = _ocp("XCAFApp").XCAFApp_Application.GetApplication_s()
    document = _ocp("TDocStd").TDocStd_Document(
        _ocp("TCollection").TCollection_ExtendedString("MDTV-XCAF")
    )
    application.InitDocument(document)
    label = _ocp("XCAFDoc").XCAFDoc_DocumentTool.ShapeTool_s(document.Main()).AddShape(shape)
    extended = _ocp("TCollection").TCollection_ExtendedString(name)
    _ocp("TDataStd").TDataStd_Name.Set_s(label, extended)
    writer = _ocp("STEPCAFControl").STEPCAFControl_Writer()
    assert writer.Transfer(document)
    return _written(writer.Write, "part.step")


def stl_bytes(shape: Shape, deflection: float = 0.1, *, ascii_file: bool = False) -> bytes:
    _ocp("BRepMesh").BRepMesh_IncrementalMesh(shape, deflection)
    writer = _ocp("StlAPI").StlAPI_Writer()
    writer.ASCIIMode = ascii_file
    return _written(lambda path: writer.Write(shape, path), "part.stl")


def _written(write: Callable[[str], object], name: str) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / name
        write(str(path))
        return path.read_bytes()
