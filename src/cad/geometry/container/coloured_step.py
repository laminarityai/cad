"""The STEP of a variant whose build code coloured its faces or named its bodies. The kernel's
writer carries neither, so this one writes the same shape through OCCT's document writer, under
the same schema and fixed header, with each area's faces coloured. A variant of several bodies is
written as one product per body under the product `result`, each named as its body is. OCCT 7.9
writes no name for a face, so the area names stay on the page."""

import bisect
import importlib
import itertools
import json
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol, cast

from cad.checks.container.kernel import StepTooLarge
from cad.checks.container.kernel.ocp_kernel import STEP_SCHEMA, STEP_TIME_STAMP
from cad.geometry.container.solids import Solid, Solids, solid_faces
from cad.sandbox.wire import AreaReport, BodyReport

DOCUMENT_FORMAT: Final = "XmlOcaf"


class _Face(Protocol):
    wrapped: object


class _Solid(Solid, Protocol):
    wrapped: object


class _Faced(Solids, Protocol):
    wrapped: object

    def faces(self) -> Sequence[_Face]: ...

    def solids(self) -> Sequence[_Solid]: ...


class _Shapes(Protocol):
    def AddShape(self, shape: object, make_assembly: bool) -> object: ...
    def NewShape(self) -> object: ...
    def AddComponent(self, assembly: object, component: object, location: object) -> object: ...
    def AddSubShape(self, root: object, shape: object) -> object: ...
    def UpdateAssemblies(self) -> None: ...


def parse(areas: str, bodies: str) -> tuple[list[AreaReport], list[BodyReport]]:
    """The host validated both lists before it sent them, so this only reads them back."""
    return cast(list[AreaReport], json.loads(areas)), cast(list[BodyReport], json.loads(bodies))


def step_bytes(
    brep: bytes, areas: list[AreaReport], bodies: list[BodyReport], cap: int
) -> bytes | StepTooLarge | None:
    """Every face an area names is coloured in sRGB. Faces are numbered as the mesh numbers
    them. None when an area names a face the shape does not have, or the bodies name a solid the
    shape does not have, so the plain STEP is written instead."""
    shape = _faced(brep)
    faces = shape.faces()
    if any(number >= len(faces) for area in areas for number in area["faces"]):
        return None
    xcaf, text = _ocp("XCAFDoc"), _ocp("TCollection")
    document = _ocp("TDocStd").TDocStd_Document(text.TCollection_ExtendedString(DOCUMENT_FORMAT))
    shapes = cast(_Shapes, xcaf.XCAFDoc_DocumentTool.ShapeTool_s(document.Main()))
    colours = xcaf.XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    holder = _products(shapes, shape, bodies)
    if holder is None:
        return None
    for area in areas:
        colour = _colour(area["colour"])
        for number in area["faces"]:
            face = shapes.AddSubShape(holder(number), faces[number].wrapped)
            colours.SetColor(face, colour, xcaf.XCAFDoc_ColorType.XCAFDoc_ColorSurf)
    return _written(document, cap)


def _named(label: object, name: str) -> None:
    _ocp("TDataStd").TDataStd_Name.Set_s(
        label, _ocp("TCollection").TCollection_ExtendedString(name)
    )


def _products(
    shapes: _Shapes, shape: _Faced, bodies: list[BodyReport]
) -> Callable[[int], object] | None:
    """The shape as one product `result`, or as a product of that name over one product per body.
    The returned function names the product that holds a face, by the face's number."""
    if not bodies:
        root = shapes.AddShape(shape.wrapped, False)
        _named(root, "result")
        return lambda _: root
    solids, counts = shape.solids(), solid_faces(shape)
    if not counts or len(solids) != sum(len(body["solids"]) for body in bodies):
        return None
    top = shapes.NewShape()
    _named(top, "result")
    owner: list[object] = [None] * len(solids)
    builder, topods = _ocp("BRep").BRep_Builder(), _ocp("TopoDS")
    for body in bodies:
        compound = topods.TopoDS_Compound()
        builder.MakeCompound(compound)
        for solid in body["solids"]:
            builder.Add(compound, solids[solid].wrapped)
        product = shapes.AddShape(compound, False)
        _named(product, body["name"])
        shapes.AddComponent(top, product, _ocp("TopLoc").TopLoc_Location())
        for solid in body["solids"]:
            owner[solid] = product
    shapes.UpdateAssemblies()
    starts = list(itertools.accumulate(counts, initial=0))
    return lambda face: owner[bisect.bisect_right(starts, face) - 1]


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
