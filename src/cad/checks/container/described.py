"""The rules for the terms beyond the reviewed phrases. Each reads only normals, principal axes,
centroids, areas, hole axes, openings and whether a point lies in the material."""

import math
from typing import Final

from cad.checks.container.features import (
    FLUSH_TOL_FRACTION,
    Geometry,
    Hole,
    axis_span,
    centroid,
    ends_along,
    extent,
    hole_region,
    holes,
    inner_curves,
    parallel,
    sized,
)
from cad.checks.container.kernel import Arc, FaceInfo, Flat, Point
from cad.checks.container.regions import Disc, Plane, Region, Unresolved
from cad.checks.container.terms import (
    Curve,
    Each,
    EndOf,
    InOneFlatFace,
    OnFarthest,
    OnLargestFlat,
    PartAxis,
)
from cad.checks.container.vectors import add, angle, cross, dot, norm, scale, sub

TIE_FRACTION: Final = 0.01
FACING_TOL_RAD: Final = math.radians(1)
MIDDLE_FRACTION: Final = 0.1
"""The middle disc's radius as a fraction of the square root of the face's area."""
AWAY_FRACTION: Final = 0.01

RANKS: Final[dict[PartAxis, int]] = {"middle": 1, "short": 2}


def end_of(term: EndOf, part: Geometry) -> tuple[Region, ...] | Unresolved:
    found = ends_along(part, axis_span(part.inertia, RANKS[term.axis]))
    if not found:
        return Unresolved(
            f"no flat face that bounds the part faces within 30° of either end of its "
            f"{term.axis} axis"
        )
    return found


def facing_pairs(part: Geometry) -> tuple[tuple[int, int], ...]:
    """Each ordered pair of flat faces whose outward normals are within FACING_TOL_RAD of
    opposite, each in front of the other, with the midpoint of their centroids outside the
    material: a gap the two faces close on."""
    tol = FLUSH_TOL_FRACTION * extent(part.inertia)
    flats = [
        (i, face, face.surface)
        for i, face in enumerate(part.faces)
        if isinstance(face.surface, Flat)
    ]
    pairs: list[tuple[int, int]] = []
    for i, first, a in flats:
        for j, second, b in flats:
            if j <= i:
                continue
            if angle(a.normal, scale(b.normal, -1)) > FACING_TOL_RAD:
                continue
            gap = sub(second.centroid, first.centroid)
            if dot(gap, a.normal) <= tol or dot(gap, b.normal) >= -tol:
                continue
            if part.inside(scale(add(first.centroid, second.centroid), 0.5)):
                continue
            pairs.extend(((i, j), (j, i)))
    return tuple(pairs)


def facing(part: Geometry) -> tuple[Region, ...] | Unresolved:
    pairs = facing_pairs(part)
    if not pairs:
        return Unresolved("no flat face faces another across a gap")
    return tuple(flat_region(part, i) for i, _ in pairs)


def opposite(region: Region, part: Geometry, middle: bool) -> Region:
    (face,) = region.faces
    (other,) = (j for i, j in facing_pairs(part) if i == face)
    return disc(part, other) if middle else flat_region(part, other)


def each(term: Each, part: Geometry) -> tuple[Region, ...] | Unresolved:
    found = curves(term.curve, term.diameter_mm, part)
    if not found:
        return Unresolved(f"the part has no {named(term.curve, term.diameter_mm)}")
    return tuple(hole_region((one,), part.faces) for one in found)


def in_one_flat_face(term: InOneFlatFace, part: Geometry) -> tuple[Region, ...] | Unresolved:
    """For each flat face, the holes of the diameter whose mouths open on it. Every face with
    such a hole must have exactly `count`, and each distinct set is a candidate."""
    found = sized(holes(part.faces, part.inertia), term.diameter_mm)
    tol = FLUSH_TOL_FRACTION * extent(part.inertia)
    by_face: dict[int, set[int]] = {}
    for opening in part.openings():
        arc = next((edge for edge in opening.edges if edge is not None), None)
        if arc is None:
            continue
        for k, hole in enumerate(found):
            if _on_axis(arc, hole, tol):
                by_face.setdefault(opening.face, set()).add(k)
    hole = named("hole", term.diameter_mm)
    if not by_face:
        return Unresolved(f"no flat face has a {hole} opening on it")
    sets: list[frozenset[int]] = []
    for _, mouths in sorted(by_face.items()):
        if len(mouths) != term.count:
            return Unresolved(
                f"the brief names {term.count} holes in one flat face, and a flat face has "
                f"{len(mouths)} {named('hole', term.diameter_mm, plural=True)}"
            )
        if frozenset(mouths) not in sets:
            sets.append(frozenset(mouths))
    return tuple(hole_region(tuple(found[k] for k in sorted(s)), part.faces) for s in sets)


def on_largest_flat(term: OnLargestFlat, support: Region, part: Geometry) -> tuple[Region, ...]:
    flats = [i for i, face in enumerate(part.faces) if isinstance(face.surface, Flat)]
    if not flats:
        return ()
    largest = max(part.faces[i].area for i in flats)
    tied = [i for i in flats if part.faces[i].area >= (1 - TIE_FRACTION) * largest]
    free = [i for i in tied if i not in support.faces]
    return tuple(disc(part, i) if term.middle else flat_region(part, i) for i in free)


def on_farthest(term: OnFarthest, support: Region, part: Geometry) -> tuple[Region, ...]:
    regions = [
        hole_region((one,), part.faces) for one in curves(term.curve, term.diameter_mm, part)
    ]
    free = [region for region in regions if not region.faces & support.faces]
    if not free:
        return ()
    reach = [norm(sub(region.centroid, support.centroid)) for region in free]
    farthest = max(reach)
    return tuple(r for r, d in zip(free, reach, strict=True) if d >= (1 - TIE_FRACTION) * farthest)


def into(load: Region) -> tuple[Point, ...] | Unresolved:
    match load.patches:
        case (Plane(_, normal),) | (Disc(_, normal, _),):
            return (scale(normal, -1),)
        case _:
            return Unresolved("pressing into the face needs a load on one flat face")


def away(support: Region, load: Region, part: Geometry) -> tuple[Point, ...] | Unresolved:
    line = sub(load.centroid, support.centroid)
    length = norm(line)
    if length < AWAY_FRACTION * extent(part.inertia):
        return Unresolved(
            "the load's centroid is within 1% of the part's reach of the support's, so no line "
            "runs away from the supports"
        )
    return (scale(line, 1 / length),)


def curves(curve: Curve, diameter_mm: float | None, part: Geometry) -> tuple[Hole, ...]:
    if curve == "hole":
        return sized(holes(part.faces, part.inertia), diameter_mm)
    return sized(inner_curves(part.faces, part.inertia), diameter_mm)


def flat_region(part: Geometry, index: int) -> Region:
    face = part.faces[index]
    assert isinstance(face.surface, Flat)
    return Region((Plane(face.centroid, face.surface.normal),), face.centroid, frozenset({index}))


def disc(part: Geometry, index: int) -> Region:
    """A disc at the face's centroid whose radius is MIDDLE_FRACTION of the root of its area."""
    face: FaceInfo = part.faces[index]
    assert isinstance(face.surface, Flat)
    radius = MIDDLE_FRACTION * math.sqrt(face.area)
    patch = Disc(face.centroid, face.surface.normal, radius)
    return Region((patch,), centroid([face]), frozenset({index}))


def _on_axis(arc: Arc, hole: Hole, tol: float) -> bool:
    offset = norm(cross(sub(arc.center, hole.origin), hole.axis))
    return parallel(arc.axis, hole.axis) and offset <= tol


def named(curve: Curve, diameter_mm: float | None, plural: bool = False) -> str:
    size = "" if diameter_mm is None else f" of {diameter_mm:g} mm"
    word = "hole" if curve == "hole" else "inner curve"
    return f"{word}{'s' if plural else ''}{size}"
