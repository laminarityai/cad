"""Placement code written by hand as the agent would write it, and the team preamble that runs it
in the build image. Each placement defines `place(part)`, which calls `candidate(support=...,
load=...)` with build123d faces. The preamble maps each face to its index in the kernel's explorer
order by `IsSame`, as the design note's preamble would.

Every placement reads only areas, normals, surface kinds and centroid differences, so it does not
depend on the frame."""

from dataclasses import dataclass
from typing import Final

from corpus import FORCE_N


@dataclass(frozen=True, slots=True)
class Placement:
    label: str
    part: str
    words: str
    """What the person said about where the part is held and loaded."""
    code: str


EQUAL_ANGLE: Final = """\
def place(part):
    flats = [f for f in part.faces() if f.geom_type == GeomType.PLANE]
    widest = max(f.area for f in flats)
    leg = next(f for f in flats if f.area > 0.99 * widest)
    out = leg.normal_at()
    across = [f for f in flats if f.normal_at().dot(out) < -0.99]
    tip = max(across, key=lambda f: (f.center() - leg.center()).dot(-out))
    candidate(support=[leg], load=[tip])
"""

GUSSET_HELPERS: Final = """\
def rims(part):
    flats = [f for f in part.faces() if f.geom_type == GeomType.PLANE]
    thickness = max(flats, key=lambda f: f.area).normal_at()
    return [f for f in flats if abs(f.normal_at().dot(thickness)) < 0.01]


def far_corner(part, held):
    out = held.normal_at()
    corners = [f for f in part.faces() if f.geom_type == GeomType.CYLINDER]
    return max(corners, key=lambda f: (f.center() - held.center()).dot(-out))


"""

GUSSET_LONG: Final = (
    GUSSET_HELPERS
    + """\
def place(part):
    edge = max(rims(part), key=lambda f: f.area)
    candidate(support=[edge], load=[far_corner(part, edge)])
"""
)

GUSSET_SHORT: Final = (
    GUSSET_HELPERS
    + """\
def place(part):
    edge = min(rims(part), key=lambda f: f.area)
    candidate(support=[edge], load=[far_corner(part, edge)])
"""
)

GUSSET_UNSAID: Final = (
    GUSSET_HELPERS
    + """\
def place(part):
    for edge in rims(part):
        candidate(support=[edge], load=[far_corner(part, edge)])
"""
)

PLACEMENTS: Final[tuple[Placement, ...]] = (
    Placement(
        "equal_angle",
        "equal_angle",
        f"one leg fixed, {FORCE_N:g} N at the end of the other, any way",
        EQUAL_ANGLE,
    ),
    Placement(
        "sb_gusset long edge",
        "sb_gusset",
        f"held along its long edge, {FORCE_N:g} N at the opposite corner, any way",
        GUSSET_LONG,
    ),
    Placement(
        "sb_gusset short edge",
        "sb_gusset",
        f"held along one short edge, {FORCE_N:g} N at the far corner, any way",
        GUSSET_SHORT,
    ),
    Placement(
        "sb_gusset edge not said",
        "sb_gusset",
        f"fixed at one end, {FORCE_N:g} N at the other, any way: each edge held is a candidate",
        GUSSET_UNSAID,
    ),
)

SIDE: Final = """
import json as _json, sys as _sys, time as _time
from build123d import *
_NAMES = {_k: _v for _k, _v in dict(globals()).items() if not _k.startswith("_")}
from OCP.BRepGProp import BRepGProp as _BRepGProp
from OCP.GProp import GProp_GProps as _Props
from OCP.TopAbs import TopAbs_FACE as _FACE
from OCP.TopExp import TopExp_Explorer as _Explorer


def _order(shape):
    found = []
    explorer = _Explorer(shape.wrapped, _FACE)
    while explorer.More():
        found.append(explorer.Current())
        explorer.Next()
    return found


def _fingerprint(order):
    rows = []
    for face in order:
        props = _Props()
        _BRepGProp.SurfaceProperties_s(face, props)
        centre = props.CentreOfMass()
        rows.append([props.Mass(), centre.X(), centre.Y(), centre.Z()])
    return rows


def _index(order, face):
    hits = [i for i, one in enumerate(order) if one.IsSame(face.wrapped)]
    if len(hits) != 1:
        raise ValueError(f"a returned face is the same as {len(hits)} faces of the part")
    return hits[0]


def _place(code, part, order):
    found = []

    def candidate(support, load, middle=False):
        found.append({
            "support": sorted({_index(order, f) for f in support}),
            "load": sorted({_index(order, f) for f in load}),
            "middle": bool(middle),
        })

    names = {**_NAMES, "candidate": candidate}
    start = _time.monotonic()
    try:
        exec(compile(code, "<placement>", "exec"), names)
        names["place"](part)
    except BaseException as error:
        return {"failed": repr(error)[:300], "seconds": _time.monotonic() - start}
    return {"candidates": found, "seconds": _time.monotonic() - start}


_codes = _json.loads(_sys.argv[1])
with open("/tmp/part.brep", "wb") as _file:
    _file.write(_sys.stdin.buffer.read())
_part = import_brep("/tmp/part.brep")
_faces = _order(_part)
_sys.stdout.write(_json.dumps({
    "faces": _fingerprint(_faces),
    "placements": {label: _place(code, _part, _faces) for label, code in _codes.items()},
}))
"""
"""Team code for the build image: the explorer order's face areas and centroids, from the same
OCCT calls the kernel's `faces` makes, and each placement's candidates as explorer indices. It
reads the BREP on stdin and the placements' code as JSON in argv."""
