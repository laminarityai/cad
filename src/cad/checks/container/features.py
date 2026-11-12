"""What the load case terms read off a part: holes, flat faces, principal axes and extent. Each
reads only normals, axes, centroids and areas, never the model's frame."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from cad.checks.container.kernel import FaceInfo, Flat, Inertia, Point, Round
from cad.checks.container.regions import Bore, Patch, Plane, Region, Unresolved
from cad.checks.container.vectors import add, angle, cross, dot, norm, scale, sub, unit

ANGLE_TOL_RAD: Final = 1e-6
OFFSET_TOL_FRACTION: Final = 1e-6
FULL_TURN_SLACK_RAD: Final = 1e-3
DIAMETER_TOL_MM: Final = 0.05
DIAMETER_TOL_FRACTION: Final = 0.01
FLUSH_TOL_FRACTION: Final = 1e-4
LONG_TIE_FRACTION: Final = 0.01


@dataclass(frozen=True, slots=True)
class Hole:
    origin: Point
    axis: Point
    radius: float
    bores: tuple[FaceInfo, ...]
    """The faces at the smallest radius, which a bolt bears on."""

    @property
    def diameter(self) -> float:
        return 2 * self.radius

    def bore(self) -> Bore:
        ends = [
            dot(sub(along(face_round(face), v), self.origin), self.axis)
            for face in self.bores
            for v in (face_round(face).v0, face_round(face).v1)
        ]
        return Bore(self.origin, self.axis, self.radius, min(ends), max(ends))


def holes(faces: Sequence[FaceInfo], inertia: Inertia) -> tuple[Hole, ...]:
    """Concave cylindrical faces grouped by axis line. A group is a hole when its angular spans
    add up to a full turn, so a fillet or a slot end is not one and a counterbore's coaxial faces
    are one hole."""
    offset_tol = OFFSET_TOL_FRACTION * extent(inertia)
    groups: list[list[FaceInfo]] = []
    for face in faces:
        if not (isinstance(face.surface, Round) and face.surface.concave):
            continue
        line = face.surface
        group = next(
            (g for g in groups if same_line(face_round(g[0]), line, offset_tol)),
            None,
        )
        if group is None:
            groups.append([face])
        else:
            group.append(face)
    found: list[Hole] = []
    for group in groups:
        if sum(face_round(face).span for face in group) < 2 * math.pi - FULL_TURN_SLACK_RAD:
            continue
        smallest = min(face_round(face).radius for face in group)
        bores = tuple(f for f in group if face_round(f).radius - smallest <= offset_tol)
        first = face_round(group[0])
        found.append(Hole(first.origin, first.axis, smallest, bores))
    return tuple(found)


def sized(found: tuple[Hole, ...], diameter_mm: float | None) -> tuple[Hole, ...]:
    if diameter_mm is None:
        return found
    return tuple(hole for hole in found if matches(hole.diameter, diameter_mm))


def matches(diameter: float, wanted_mm: float) -> bool:
    return abs(diameter - wanted_mm) <= max(DIAMETER_TOL_MM, DIAMETER_TOL_FRACTION * wanted_mm)


def hole_region(found: tuple[Hole, ...]) -> Region:
    bores = [face for hole in found for face in hole.bores]
    return Region(tuple(hole.bore() for hole in found), centroid(bores))


def long_axis(inertia: Inertia) -> Point | Unresolved:
    first, *tied = axis_span(inertia, 0)
    if tied:
        return Unresolved(
            "the part has no unique long axis: its two largest volume spreads are within 1%"
        )
    return first


def axis_span(inertia: Inertia, rank: int) -> tuple[Point, ...]:
    """The principal axes whose volume spread is within LONG_TIE_FRACTION of the spread ranked
    `rank` from the largest: rank 0 is the long axis, 1 the middle and 2 the short."""
    spreads = second_moments(inertia)
    ranked = sorted(spreads, reverse=True)[rank]
    return tuple(
        axis
        for axis, spread in zip(inertia.axes, spreads, strict=True)
        if abs(ranked - spread) <= LONG_TIE_FRACTION * max(ranked, spread)
    )


def second_moments(inertia: Inertia) -> tuple[float, ...]:
    half = sum(inertia.moments) / 2
    return tuple(half - moment for moment in inertia.moments)


def extent(inertia: Inertia) -> float:
    return max(high - low for low, high in inertia.spans)


def face_round(face: FaceInfo) -> Round:
    assert isinstance(face.surface, Round)
    return face.surface


def distinct_planes(
    chosen: Sequence[FaceInfo], flats: Sequence[FaceInfo], inertia: Inertia
) -> tuple[Region, ...]:
    """A region for each plane among `chosen`, with every face of `flats` flush with it."""
    tol = FLUSH_TOL_FRACTION * extent(inertia)
    regions: list[Region] = []
    for face in chosen:
        assert isinstance(face.surface, Flat)
        plane = Plane(face.centroid, face.surface.normal)
        if any(flush(face, region.patches[0], tol) for region in regions):
            continue
        level = [other for other in flats if flush(other, plane, tol)]
        regions.append(Region((plane,), centroid(level)))
    return tuple(regions)


def flush(face: FaceInfo, patch: Patch, tol: float) -> bool:
    return isinstance(face.surface, Flat) and coplanar(
        Plane(face.centroid, face.surface.normal), patch, tol
    )


def coplanar(plane: Patch, patch: Patch, tol: float) -> bool:
    return (
        isinstance(plane, Plane)
        and isinstance(patch, Plane)
        and angle(plane.normal, patch.normal) <= ANGLE_TOL_RAD
        and abs(dot(sub(plane.point, patch.point), patch.normal)) <= tol
    )


def bounding_flats(faces: Sequence[FaceInfo], tol: float) -> list[tuple[FaceInfo, Flat]]:
    return [
        (face, face.surface)
        for face in faces
        if isinstance(face.surface, Flat) and face.surface.beyond <= tol
    ]


def projected(vector: Point, span: Sequence[Point]) -> Point:
    found: Point = (0.0, 0.0, 0.0)
    for axis in span:
        found = add(found, scale(axis, dot(vector, axis)))
    return found


def same_line(first: Round, second: Round, tol: float) -> bool:
    offset = norm(cross(sub(second.origin, first.origin), first.axis))
    return parallel(first.axis, second.axis) and offset <= tol


def parallel(first: Point, second: Point) -> bool:
    return min(angle(first, second), angle(first, scale(second, -1))) <= ANGLE_TOL_RAD


def normal_plane(axis: Point) -> tuple[Point, Point]:
    helper = min(
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), key=lambda e: abs(dot(e, axis))
    )
    first = unit(cross(axis, helper))
    return first, cross(axis, first)


def centroid(faces: Sequence[FaceInfo]) -> Point:
    total = sum(face.area for face in faces)
    x, y, z = (sum(face.area * face.centroid[i] for face in faces) / total for i in range(3))
    return (x, y, z)


def along(line: Round, v: float) -> Point:
    return add(line.origin, scale(line.axis, v))
