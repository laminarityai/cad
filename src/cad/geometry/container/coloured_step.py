"""The STEP of a variant whose build code coloured its faces. The kernel's writer cannot carry a
colour, so this one writes the same shape through OCCT's document writer with each area's
faces coloured, under the same schema and fixed header. OCCT 7.9 writes no name for a face, so
the area names stay on the page."""

import importlib
import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol, cast

from cad.checks.container.kernel import StepTooLarge
from cad.checks.container.kernel.ocp_kernel import STEP_SCHEMA, STEP_TIME_STAMP
from cad.sandbox.wire import AreaReport

DOCUMENT_FORMAT: Final = "XmlOcaf"


class _Face(Protocol):
    wrapped: object


class _Faced(Protocol):
    wrapped: object

    def faces(self) -> Sequence[_Face]: ...


def parse(text: str) -> list[AreaReport]:
    """The host validated the areas before it sent them, so this only reads them back."""
    return cast(list[AreaReport], json.loads(text))


def step_bytes(brep: bytes, areas: list[AreaReport], cap: int) -> bytes | StepTooLarge | None:
    """Every face an area names is coloured in sRGB. Faces are numbered as the mesh numbers
    them. None when an area names a face the shape does not have, so the plain STEP is written
    instead."""
    shape = _faced(brep)
    faces = shape.faces()
    if any(number >= len(faces) for area in areas for number in area["faces"]):
        return None
    xcaf, text = _ocp("XCAFDoc"), _ocp("TCollection")
    document = _ocp("TDocStd").TDocStd_Document(text.TCollection_ExtendedString(DOCUMENT_FORMAT))
    shapes = xcaf.XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    colours = xcaf.XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    root = shapes.AddShape(shape.wrapped, False)
    _ocp("TDataStd").TDataStd_Name.Set_s(root, text.TCollection_ExtendedString("result"))
    for area in areas:
        colour = _colour(area["colour"])
        for number in area["faces"]:
            face = shapes.AddSubShape(root, faces[number].wrapped)
            colours.SetColor(face, colour, xcaf.XCAFDoc_ColorType.XCAFDoc_ColorSurf)
    return _written(document, cap)


def _written(document: object, cap: int) -> bytes | StepTooLarge:
    _ocp("Interface").Interface_Static.SetCVal_s("write.step.schema", STEP_SCHEMA)
    step, text = _ocp("STEPCAFControl"), _ocp("TCollection")
    writer = step.STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    if not writer.Transfer(document, _ocp("STEPControl").STEPControl_AsIs):
        raise RuntimeError("STEPCAFControl_Writer could not transfer the coloured shape")
    header = _ocp("APIHeaderSection").APIHeaderSection_MakeHeader(writer.ChangeWriter().Model())
    header.SetTimeStamp(text.TCollection_HAsciiString(STEP_TIME_STAMP))
    header.SetName(text.TCollection_HAsciiString("result"))
    header.SetAuthorValue(1, text.TCollection_HAsciiString(""))
    header.SetOrganizationValue(1, text.TCollection_HAsciiString(""))
    header.SetOriginatingSystem(text.TCollection_HAsciiString("cad"))
    header.SetAuthorisation(text.TCollection_HAsciiString(""))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "result.step"
        if writer.Write(str(path)) != _ocp("IFSelect").IFSelect_RetDone:
            raise RuntimeError("STEPCAFControl_Writer could not write the coloured shape")
        size = path.stat().st_size
        return StepTooLarge(size) if size > cap else path.read_bytes()


def _colour(hex_colour: str) -> object:
    quantity = _ocp("Quantity")
    red, green, blue = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return quantity.Quantity_Color(red, green, blue, quantity.Quantity_TOC_sRGB)


def _faced(brep: bytes) -> _Faced:
    """Read by build123d, as the mesh is, so face i here is face i on the page."""
    build123d = importlib.import_module("build123d")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.brep"
        path.write_bytes(brep)
        return cast(_Faced, build123d.import_brep(str(path)))


def _ocp(name: str) -> ModuleType:
    return importlib.import_module(f"OCP.{name}")
