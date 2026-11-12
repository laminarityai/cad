import base64
import json
import math
from collections.abc import Iterable, Sequence
from typing import Final, Literal, TypedDict

from cad.checks.container import anchors, features
from cad.checks.container.channel import serve
from cad.checks.container.kernel import (
    FaceInfo,
    Flat,
    Kernel,
    Point,
    Shape,
    Unreadable,
    ocp_kernel,
)
from cad.checks.container.regions import Plane, Unresolved
from cad.checks.container.vectors import angle, dot, sub
from cad.checks.container.whole_solids import unmeasurable

MAX_HOLES: Final = 64
MAX_FLATS: Final = 16
FORMATS: Final = ("brep", "step", "stl")


class ReadAs(TypedDict):
    """The header line before the bytes. `scale` multiplies every coordinate: 25.4 reads an STL
    the person said is in inches as millimetres."""

    format: Literal["brep", "step", "stl"]
    scale: float


class HoleWire(TypedDict):
    diameter_mm: float
    center: list[float]
    axis: list[float]
    solid: int


class FlatWire(TypedDict):
    normal: list[float]
    area_mm2: float
    centroid: list[float]
    solid: int


class LeftOutWire(TypedDict):
    bodies: int
    unreadable: int
    loose: int


class PartWire(TypedDict):
    """`brep` is the base64 BREP of the solids kept from a STEP or STL file, and None for a BREP
    read as it is."""

    kind: Literal["part"]
    solids: int
    volume_mm3: float
    box_min: list[float]
    box_max: list[float]
    holes: list[HoleWire]
    flats: list[FlatWire]
    names: list[str]
    left_out: LeftOutWire | None
    brep: str | None


class RefusedWire(TypedDict):
    kind: Literal["refused"]
    reason: str


type IngestWire = PartWire | RefusedWire


def main() -> None:
    serve(lambda _, stdin: answer(ocp_kernel(), stdin))


def answer(kernel: Kernel, stdin: bytes) -> IngestWire:
    """The header line, then the bytes it says how to read."""
    line, _, data = stdin.partition(b"\n")
    try:
        header = json.loads(line)
        scale = float(header["scale"])
        form = header["format"]
    except (ValueError, KeyError, TypeError):
        return _refused("the request has no readable header line")
    if form not in FORMATS or not math.isfinite(scale) or scale <= 0:
        return _refused("the request header names a format or a scale that is not allowed")
    return facts(kernel, {"format": form, "scale": scale}, data)


def facts(kernel: Kernel, read_as: ReadAs, data: bytes) -> IngestWire:
    names: list[str] = []
    match read_as["format"]:
        case "brep":
            shape = kernel.read_brep(data)
            if isinstance(shape, Unreadable):
                return _refused(f"the BREP cannot be read: {shape.reason}")
            kept = None
        case "step":
            read = kernel.read_step(data)
            if isinstance(read, Unreadable):
                return _refused(f"the STEP file cannot be read: {read.reason}")
            shape, names = read.shape, list(read.names)
            kept = kernel.keep_solids(shape)
        case "stl":
            shape = kernel.read_stl(data, read_as["scale"])
            if isinstance(shape, Unreadable):
                return _refused(f"the STL file cannot be read: {shape.reason}")
            kept = kernel.keep_solids(shape)
    left_out: LeftOutWire | None = None
    if kept is not None:
        if kept.solids is None:
            return _refused(
                f"the file has no solid that can be read: {kept.bodies} bodies, none readable"
            )
        shape = kept.solids
        left_out = {"bodies": kept.bodies, "unreadable": kept.unreadable, "loose": kept.loose}
    problem = unmeasurable(kernel, shape)
    if problem is not None:
        return _refused(f"the shape {problem}")
    corners = kernel.bounds(shape)
    if corners is None:
        return _refused("the shape has no bounding box")
    low, high = corners
    volume = kernel.volume_props(shape).volume
    if not all(map(math.isfinite, (volume, *low, *high))):
        return _refused("the volume or the bounding box is not a finite number")
    solids = kernel.solids(shape)
    return {
        "kind": "part",
        "solids": len(solids),
        "volume_mm3": volume,
        "box_min": _listed(low),
        "box_max": _listed(high),
        "holes": _holes(kernel, solids),
        "flats": _flats(kernel, solids),
        "names": names,
        "left_out": left_out,
        "brep": None if kept is None else base64.b64encode(kernel.brep_bytes(shape)).decode(),
    }


def _holes(kernel: Kernel, solids: Sequence[Shape]) -> list[HoleWire]:
    found: list[HoleWire] = []
    for index, solid in enumerate(solids):
        faces, inertia = kernel.faces(solid), kernel.inertia(solid)
        for hole in features.holes(faces, inertia):
            wire: HoleWire = {
                "diameter_mm": hole.diameter,
                "center": _listed(hole.origin),
                "axis": _listed(hole.axis),
                "solid": index,
            }
            if _finite(wire["diameter_mm"], *wire["center"], *wire["axis"]):
                found.append(wire)
    return found[:MAX_HOLES]


def _flats(kernel: Kernel, solids: Sequence[Shape]) -> list[FlatWire]:
    found: list[FlatWire] = []
    for index, solid in enumerate(solids):
        faces, inertia = kernel.faces(solid), kernel.inertia(solid)
        regions = anchors.largest_flats(faces, inertia)
        if isinstance(regions, Unresolved):
            continue
        tol = features.FLUSH_TOL_FRACTION * features.extent(inertia)
        for region in regions:
            plane = region.patches[0]
            assert isinstance(plane, Plane)
            wire: FlatWire = {
                "normal": _listed(plane.normal),
                "area_mm2": _flush_area(faces, plane, tol),
                "centroid": _listed(region.centroid),
                "solid": index,
            }
            if _finite(wire["area_mm2"], *wire["normal"], *wire["centroid"]):
                found.append(wire)
    return found[:MAX_FLATS]


def _flush_area(faces: Iterable[FaceInfo], plane: Plane, tol: float) -> float:
    """The area of the planar faces on the plane, the same faces the region's centroid weighs."""
    return sum(
        face.area
        for face in faces
        if isinstance(face.surface, Flat)
        and angle(face.surface.normal, plane.normal) <= features.ANGLE_TOL_RAD
        and abs(dot(sub(face.centroid, plane.point), plane.normal)) <= tol
    )


def _finite(*numbers: float) -> bool:
    return all(map(math.isfinite, numbers))


def _listed(point: Point) -> list[float]:
    return [float(one) for one in point]


def _refused(reason: str) -> RefusedWire:
    return {"kind": "refused", "reason": reason}
