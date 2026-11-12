"""One resolver for every load case term. Fixed rules over the kernel's face summary turn the
support term into regions, the load term into regions for each support, and the direction term
into a basis for each pair. Every pair is a candidate, and the check keeps the worst."""

import math
from collections.abc import Sequence
from typing import Final, assert_never

from cad.checks.container import described
from cad.checks.container.features import (
    AREA_TIE_FRACTION,
    Geometry,
    Hole,
    axis_span,
    distinct_planes,
    ends_along,
    extent,
    farthest_flats,
    hole_region,
    holes,
    long_axis,
    normal_plane,
    parallel,
    sized,
)
from cad.checks.container.kernel import FaceInfo, Flat, Inertia, Point
from cad.checks.container.regions import Bore, Candidate, FarFrom, Region, Resolved, Unresolved
from cad.checks.container.terms import (
    Across,
    Along,
    AnyWay,
    Away,
    Axis,
    Direction,
    Each,
    EndOf,
    Facing,
    FarEnd,
    FlatEnd,
    Holes,
    InOneFlatFace,
    Into,
    LargestFlat,
    Load,
    LoadCase,
    OnFarthest,
    OnHoles,
    OnLargestFlat,
    OnOpposite,
    Support,
)
from cad.checks.container.vectors import norm, scale, sub, unit

FAR_CONE_RAD: Final = math.radians(45)
OFF_CENTER_FRACTION: Final = 0.01
CANDIDATE_LIMIT: Final = 4
"""The most candidates a described load case may give. Each is a solve at two mesh sizes."""


def resolve(case: LoadCase, part: Geometry) -> Resolved | Unresolved:
    refused = _refused(case)
    if refused is not None:
        return refused
    supports = support_regions(case.support, part)
    if isinstance(supports, Unresolved):
        return supports
    candidates: list[Candidate] = []
    for support in supports:
        loads = load_regions(case.load, case.support, support, part)
        if isinstance(loads, Unresolved):
            return loads
        for load in loads:
            basis = direction_basis(case.direction, case.support, support, load, part)
            if isinstance(basis, Unresolved):
                return basis
            candidates.append(Candidate(support, load, basis))
    if case.described and len(candidates) > CANDIDATE_LIMIT:
        return Unresolved(
            f"the load case gives {len(candidates)} pairs of support and load, over the limit "
            f"of {CANDIDATE_LIMIT}"
        )
    return Resolved(tuple(candidates))


def support_regions(support: Support, part: Geometry) -> tuple[Region, ...] | Unresolved:
    match support:
        case Holes():
            held = support_holes(support, part)
            return held if isinstance(held, Unresolved) else (hole_region(held, part.faces),)
        case LargestFlat():
            return largest_flats(part.faces, part.inertia)
        case FlatEnd():
            return flat_ends(part.faces, part.inertia)
        case EndOf():
            return described.end_of(support, part)
        case Facing():
            return described.facing(part)
        case Each():
            return described.each(support, part)
        case InOneFlatFace():
            return described.in_one_flat_face(support, part)
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
        case OnLargestFlat():
            flats = described.on_largest_flat(load, region, part)
            return flats or Unresolved("every largest flat face of the part is a support face")
        case OnOpposite():
            return (described.opposite(region, part, load.middle),)
        case OnFarthest():
            found = described.on_farthest(load, region, part)
            named = described.named(load.curve, load.diameter_mm)
            return found or Unresolved(f"the part has no {named} outside the supports")
        case _:
            assert_never(load)


def direction_basis(
    direction: Direction,
    support: Support,
    region: Region,
    load: Region | FarFrom,
    part: Geometry,
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
        case Into():
            assert isinstance(load, Region)
            return described.into(load)
        case Away():
            if isinstance(load, FarFrom):
                return Unresolved("pulling away from the supports needs a load on faces")
            return described.away(region, load, part)
        case _:
            assert_never(direction)


def _refused(case: LoadCase) -> Unresolved | None:
    """The pairings of terms that name nothing, which parsing will refuse."""
    if isinstance(case.load, OnOpposite) and not isinstance(case.support, Facing):
        return Unresolved("a load on the opposite face needs a support on one of two facing faces")
    if isinstance(case.direction, Into) and not isinstance(case.load, OnLargestFlat | OnOpposite):
        return Unresolved("pressing into the face needs a load on a flat face")
    return None


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
    return counted if isinstance(counted, Unresolved) else hole_region(counted, part.faces)


def largest_flats(faces: Sequence[FaceInfo], inertia: Inertia) -> tuple[Region, ...] | Unresolved:
    flats = [face for face in faces if isinstance(face.surface, Flat)]
    if not flats:
        return Unresolved("the part has no planar face to sit on")
    largest = max(face.area for face in flats)
    tied = [face for face in flats if face.area >= largest * (1 - AREA_TIE_FRACTION)]
    return distinct_planes(tied, faces, inertia)


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


def _named_axis(name: Axis, support: Support, region: Region, part: Geometry) -> Point | Unresolved:
    if name == "long":
        return long_axis(part.inertia)
    through_holes = isinstance(support, Holes | InOneFlatFace) or (
        isinstance(support, Each) and support.curve == "hole"
    )
    if not through_holes:
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
