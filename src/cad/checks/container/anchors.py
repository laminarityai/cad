"""One resolver for every load case term. Fixed rules over the kernel's face summary turn the
support term into regions, the load term into regions for each support, and the direction term
into a basis for each pair. Every pair is a candidate, and the check keeps the worst."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, assert_never

from cad.checks.container.features import (
    ANGLE_TOL_RAD,
    FLUSH_TOL_FRACTION,
    Hole,
    axis_span,
    bounding_flats,
    coplanar,
    distinct_planes,
    extent,
    hole_region,
    holes,
    long_axis,
    normal_plane,
    parallel,
    projected,
    sized,
)
from cad.checks.container.kernel import FaceInfo, Flat, Inertia, Kernel, Point, Shape
from cad.checks.container.regions import Bore, Candidate, FarFrom, Region, Resolved, Unresolved
from cad.checks.container.terms import (
    Across,
    Along,
    AnyWay,
    Axis,
    Direction,
    FarEnd,
    FlatEnd,
    Holes,
    LargestFlat,
    Load,
    LoadCase,
    OnHoles,
    Support,
)
from cad.checks.container.vectors import angle, dot, norm, scale, sub, unit

AREA_TIE_FRACTION: Final = 1e-6
END_CONE_RAD: Final = math.radians(30)
FAR_CONE_RAD: Final = math.radians(45)
OFF_CENTER_FRACTION: Final = 0.01


@dataclass(frozen=True, slots=True)
class Geometry:
    """The kernel's summary of one solid, which is all the rules read."""

    faces: tuple[FaceInfo, ...]
    inertia: Inertia


def geometry(kernel: Kernel, shape: Shape) -> Geometry:
    return Geometry(kernel.faces(shape), kernel.inertia(shape))


def resolve(case: LoadCase, part: Geometry) -> Resolved | Unresolved:
    supports = support_regions(case.support, part)
    if isinstance(supports, Unresolved):
        return supports
    candidates: list[Candidate] = []
    for support in supports:
        loads = load_regions(case.load, case.support, support, part)
        if isinstance(loads, Unresolved):
            return loads
        for load in loads:
            basis = direction_basis(case.direction, case.support, support, part)
            if isinstance(basis, Unresolved):
                return basis
            candidates.append(Candidate(support, load, basis))
    return Resolved(tuple(candidates))


def support_regions(support: Support, part: Geometry) -> tuple[Region, ...] | Unresolved:
    match support:
        case Holes():
            held = support_holes(support, part)
            return held if isinstance(held, Unresolved) else (hole_region(held),)
        case LargestFlat():
            return largest_flats(part.faces, part.inertia)
        case FlatEnd():
            return flat_ends(part.faces, part.inertia)
        case _:
            assert_never(support)


def load_regions(
    load: Load, support: Support, region: Region, part: Geometry
) -> tuple[Region | FarFrom, ...] | Unresolved:
    match load:
        case FarEnd():
            return far_ends(region, part.faces, part.inertia)
        case OnHoles():
            loaded = load_holes(load, support, part)
            return loaded if isinstance(loaded, Unresolved) else (loaded,)
        case _:
            assert_never(load)


def direction_basis(
    direction: Direction, support: Support, region: Region, part: Geometry
) -> tuple[Point, ...] | Unresolved:
    match direction:
        case AnyWay():
            return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        case Along(axis):
            found = _named_axis(axis, support, region, part)
            return found if isinstance(found, Unresolved) else (found,)
        case Across(axis):
            found = _named_axis(axis, support, region, part)
            return found if isinstance(found, Unresolved) else normal_plane(found)
        case _:
            assert_never(direction)


def far_ends(
    support: Region, faces: Sequence[FaceInfo], inertia: Inertia
) -> tuple[Region | FarFrom, ...] | Unresolved:
    """The whole flat face farthest from the support along each far line, or the line's band
    when no flat face that bounds the part faces along it, as on a rounded tip."""
    lines = far_from(support, inertia)
    if isinstance(lines, Unresolved):
        return lines
    found: list[Region | FarFrom] = []
    for line in lines:
        found.extend(farthest_flats(faces, line.axis, FAR_CONE_RAD, inertia) or (line,))
    return tuple(found)


def far_from(support: Region, inertia: Inertia) -> tuple[FarFrom, ...] | Unresolved:
    toward = sub(inertia.center, support.centroid)
    if norm(toward) > OFF_CENTER_FRACTION * extent(inertia):
        return (FarFrom(support.centroid, unit(toward)),)
    axis = long_axis(inertia)
    if isinstance(axis, Unresolved):
        return Unresolved(
            "the support sits at the part's centre of mass and the part has no unique long "
            "axis, so no end of the part is the far one"
        )
    return (FarFrom(support.centroid, axis), FarFrom(support.centroid, scale(axis, -1)))


def farthest_flats(
    faces: Sequence[FaceInfo], way: Point, cone: float, inertia: Inertia
) -> tuple[Region, ...]:
    """The flat faces that bound the part, face within `cone` of `way`, and whose centroid
    reaches farthest along it, each with the faces flush with it. Faces tied for farthest are
    each a region."""
    tol = FLUSH_TOL_FRACTION * extent(inertia)
    facing = [face for face, flat in bounding_flats(faces, tol) if angle(flat.normal, way) <= cone]
    if not facing:
        return ()
    farthest = max(dot(face.centroid, way) for face in facing)
    tied = [face for face in facing if dot(face.centroid, way) >= farthest - tol]
    return distinct_planes(tied, faces, inertia)


def support_holes(support: Holes, part: Geometry) -> tuple[Hole, ...] | Unresolved:
    found = holes(part.faces, part.inertia)
    return _counted(found, support.count, support.diameter_mm, "support")


def load_holes(load: OnHoles, support: Support, part: Geometry) -> Region | Unresolved:
    held: tuple[Hole, ...] = ()
    if isinstance(support, Holes):
        found = support_holes(support, part)
        if isinstance(found, Unresolved):
            return found
        held = found
    free = tuple(hole for hole in holes(part.faces, part.inertia) if hole not in held)
    counted = _counted(free, load.count, load.diameter_mm, "loaded")
    return counted if isinstance(counted, Unresolved) else hole_region(counted)


def largest_flats(faces: Sequence[FaceInfo], inertia: Inertia) -> tuple[Region, ...] | Unresolved:
    flats = [face for face in faces if isinstance(face.surface, Flat)]
    if not flats:
        return Unresolved("the part has no planar face to sit on")
    largest = max(face.area for face in flats)
    tied = [face for face in flats if face.area >= largest * (1 - AREA_TIE_FRACTION)]
    return distinct_planes(tied, flats, inertia)


def flat_ends(faces: Sequence[FaceInfo], inertia: Inertia) -> tuple[Region, ...] | Unresolved:
    """At each end of the long axis, the farthest flat face that bounds the part and faces within
    END_CONE_RAD of the axis. When spreads tie, any direction in the tied axes' span is a long
    axis, so each bounding face within the cone of that span gives its own end."""
    found = ends_along(faces, inertia, axis_span(inertia, 0))
    if not found:
        return Unresolved(
            "no flat face that bounds the part faces within 30° of either end of the long axis"
        )
    return found


def ends_along(
    faces: Sequence[FaceInfo], inertia: Inertia, span: Sequence[Point]
) -> tuple[Region, ...]:
    tol = FLUSH_TOL_FRACTION * extent(inertia)
    ways: list[Point] = []
    for _, flat in bounding_flats(faces, tol):
        toward = projected(flat.normal, span)
        if norm(toward) < math.cos(END_CONE_RAD):
            continue
        way = unit(toward)
        if not any(angle(way, seen) <= ANGLE_TOL_RAD for seen in ways):
            ways.append(way)
    regions: list[Region] = []
    for way in ways:
        for region in farthest_flats(faces, way, END_CONE_RAD, inertia):
            if not any(coplanar(region.patches[0], seen.patches[0], tol) for seen in regions):
                regions.append(region)
    return tuple(regions)


def _named_axis(name: Axis, support: Support, region: Region, part: Geometry) -> Point | Unresolved:
    if name == "long":
        return long_axis(part.inertia)
    if not isinstance(support, Holes):
        return Unresolved("the hole axis needs a support through holes")
    bores = [patch for patch in region.patches if isinstance(patch, Bore)]
    axis = bores[0].axis
    if not all(parallel(bore.axis, axis) for bore in bores):
        return Unresolved("the support holes are not parallel, so they share no hole axis")
    return axis


def _counted(
    found: tuple[Hole, ...], count: int, diameter_mm: float | None, role: str
) -> tuple[Hole, ...] | Unresolved:
    kept = sized(found, diameter_mm)
    if len(kept) != count:
        size = "" if diameter_mm is None else f" of {diameter_mm:g} mm"
        return Unresolved(f"the brief names {count} {role} holes{size}, the part has {len(kept)}")
    return kept
