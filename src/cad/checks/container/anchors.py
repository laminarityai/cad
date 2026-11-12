import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, assert_never

from cad.checks.container.kernel import FaceInfo, Flat, Inertia, Point, Round
from cad.checks.container.regions import (
    Bore,
    Candidate,
    FarFrom,
    Patch,
    Plane,
    Region,
    Resolved,
    Unresolved,
)
from cad.checks.container.vectors import add, angle, cross, dot, norm, scale, sub, unit
from cad.checks.container.wire import (
    AxisWire,
    DirectionWire,
    HolesWire,
    LoadCaseWire,
    OnHolesWire,
    SupportWire,
)

ANGLE_TOL_RAD: Final = 1e-6
OFFSET_TOL_FRACTION: Final = 1e-6
FULL_TURN_SLACK_RAD: Final = 1e-3
DIAMETER_TOL_MM: Final = 0.05
DIAMETER_TOL_FRACTION: Final = 0.01
AREA_TIE_FRACTION: Final = 1e-6
END_CONE_RAD: Final = math.radians(30)
FAR_CONE_RAD: Final = math.radians(45)
FLUSH_TOL_FRACTION: Final = 1e-4
LONG_TIE_FRACTION: Final = 0.01
OFF_CENTER_FRACTION: Final = 0.01


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
            dot(sub(_along(face_round(face), v), self.origin), self.axis)
            for face in self.bores
            for v in (face_round(face).v0, face_round(face).v1)
        ]
        return Bore(self.origin, self.axis, self.radius, min(ends), max(ends))


def resolve(
    case: LoadCaseWire, faces: Sequence[FaceInfo], inertia: Inertia
) -> Resolved | Unresolved:
    supports = support_regions(case["support"], faces, inertia)
    if isinstance(supports, Unresolved):
        return supports
    basis = direction_basis(case["load"]["direction"], case["support"], faces, inertia)
    if isinstance(basis, Unresolved):
        return basis
    load = case["load"]
    match load["kind"]:
        case "far_end":
            candidates: list[Candidate] = []
            for support in supports:
                ends = far_ends(support, faces, inertia)
                if isinstance(ends, Unresolved):
                    return ends
                candidates.extend(Candidate(support, end) for end in ends)
            return Resolved(tuple(candidates), basis)
        case "on_holes":
            loaded = load_holes(load, case["support"], faces, inertia)
            if isinstance(loaded, Unresolved):
                return loaded
            return Resolved(tuple(Candidate(s, loaded) for s in supports), basis)
        case _:
            assert_never(load["kind"])


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
    facing = [face for face, flat in _bounding_flats(faces, tol) if angle(flat.normal, way) <= cone]
    if not facing:
        return ()
    farthest = max(dot(face.centroid, way) for face in facing)
    tied = [face for face in facing if dot(face.centroid, way) >= farthest - tol]
    return _distinct_planes(tied, faces, inertia)


def support_regions(
    support: SupportWire, faces: Sequence[FaceInfo], inertia: Inertia
) -> tuple[Region, ...] | Unresolved:
    match support["kind"]:
        case "holes":
            held = support_holes(support, faces, inertia)
            return held if isinstance(held, Unresolved) else (_hole_region(held),)
        case "largest_flat":
            return largest_flats(faces, inertia)
        case "flat_end":
            return flat_ends(faces, inertia)
        case _:
            assert_never(support["kind"])


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
            (g for g in groups if _same_line(face_round(g[0]), line, offset_tol)),
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


def support_holes(
    support: HolesWire, faces: Sequence[FaceInfo], inertia: Inertia
) -> tuple[Hole, ...] | Unresolved:
    return _counted(holes(faces, inertia), support["count"], support["diameter_mm"], "support")


def load_holes(
    load: OnHolesWire, support: SupportWire, faces: Sequence[FaceInfo], inertia: Inertia
) -> Region | Unresolved:
    held: tuple[Hole, ...] = ()
    if support["kind"] == "holes":
        found = support_holes(support, faces, inertia)
        if isinstance(found, Unresolved):
            return found
        held = found
    free = tuple(hole for hole in holes(faces, inertia) if hole not in held)
    counted = _counted(free, load["count"], load["diameter_mm"], "loaded")
    return counted if isinstance(counted, Unresolved) else _hole_region(counted)


def largest_flats(faces: Sequence[FaceInfo], inertia: Inertia) -> tuple[Region, ...] | Unresolved:
    flats = [face for face in faces if isinstance(face.surface, Flat)]
    if not flats:
        return Unresolved("the part has no planar face to sit on")
    largest = max(face.area for face in flats)
    tied = [face for face in flats if face.area >= largest * (1 - AREA_TIE_FRACTION)]
    return _distinct_planes(tied, flats, inertia)


def flat_ends(faces: Sequence[FaceInfo], inertia: Inertia) -> tuple[Region, ...] | Unresolved:
    """At each end of the long axis, the farthest flat face that bounds the part and faces within
    END_CONE_RAD of the axis. When spreads tie, any direction in the tied axes' span is a long
    axis, so each bounding face within the cone of that span gives its own end."""
    tol = FLUSH_TOL_FRACTION * extent(inertia)
    span = long_span(inertia)
    ways: list[Point] = []
    for _, flat in _bounding_flats(faces, tol):
        along = _projected(flat.normal, span)
        if norm(along) < math.cos(END_CONE_RAD):
            continue
        way = unit(along)
        if not any(angle(way, seen) <= ANGLE_TOL_RAD for seen in ways):
            ways.append(way)
    regions: list[Region] = []
    for way in ways:
        for region in farthest_flats(faces, way, END_CONE_RAD, inertia):
            if not any(_coplanar(region.patches[0], seen.patches[0], tol) for seen in regions):
                regions.append(region)
    if not regions:
        return Unresolved(
            "no flat face that bounds the part faces within 30° of either end of the long axis"
        )
    return tuple(regions)


def long_axis(inertia: Inertia) -> Point | Unresolved:
    first, *tied = long_span(inertia)
    if tied:
        return Unresolved(
            "the part has no unique long axis: its two largest volume spreads are within 1%"
        )
    return first


def long_span(inertia: Inertia) -> tuple[Point, ...]:
    """The principal axes whose volume spread is within LONG_TIE_FRACTION of the largest."""
    spreads = second_moments(inertia)
    first = max(spreads)
    return tuple(
        axis
        for axis, spread in zip(inertia.axes, spreads, strict=True)
        if first - spread <= LONG_TIE_FRACTION * first
    )


def second_moments(inertia: Inertia) -> tuple[float, ...]:
    half = sum(inertia.moments) / 2
    return tuple(half - moment for moment in inertia.moments)


def direction_basis(
    direction: DirectionWire, support: SupportWire, faces: Sequence[FaceInfo], inertia: Inertia
) -> tuple[Point, ...] | Unresolved:
    match direction["kind"]:
        case "any":
            return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        case "along":
            axis = _named_axis(direction["axis"], support, faces, inertia)
            return axis if isinstance(axis, Unresolved) else (axis,)
        case "across":
            axis = _named_axis(direction["axis"], support, faces, inertia)
            return axis if isinstance(axis, Unresolved) else _normal_plane(axis)
        case _:
            assert_never(direction["kind"])


def extent(inertia: Inertia) -> float:
    return max(high - low for low, high in inertia.spans)


def face_round(face: FaceInfo) -> Round:
    assert isinstance(face.surface, Round)
    return face.surface


def _named_axis(
    name: AxisWire, support: SupportWire, faces: Sequence[FaceInfo], inertia: Inertia
) -> Point | Unresolved:
    if name == "long":
        return long_axis(inertia)
    if support["kind"] != "holes":
        return Unresolved("the hole axis needs a support through holes")
    held = support_holes(support, faces, inertia)
    if isinstance(held, Unresolved):
        return held
    axis = held[0].axis
    if not all(_parallel(hole.axis, axis) for hole in held):
        return Unresolved("the support holes are not parallel, so they share no hole axis")
    return axis


def _counted(
    found: tuple[Hole, ...], count: int, diameter_mm: float | None, role: str
) -> tuple[Hole, ...] | Unresolved:
    kept = found
    sized = ""
    if diameter_mm is not None:
        tol = max(DIAMETER_TOL_MM, DIAMETER_TOL_FRACTION * diameter_mm)
        kept = tuple(hole for hole in found if abs(hole.diameter - diameter_mm) <= tol)
        sized = f" of {diameter_mm:g} mm"
    if len(kept) != count:
        return Unresolved(f"the brief names {count} {role} holes{sized}, the part has {len(kept)}")
    return kept


def _hole_region(found: tuple[Hole, ...]) -> Region:
    bores = [face for hole in found for face in hole.bores]
    return Region(tuple(hole.bore() for hole in found), _centroid(bores))


def _distinct_planes(
    chosen: Sequence[FaceInfo], flats: Sequence[FaceInfo], inertia: Inertia
) -> tuple[Region, ...]:
    tol = FLUSH_TOL_FRACTION * extent(inertia)
    regions: list[Region] = []
    for face in chosen:
        assert isinstance(face.surface, Flat)
        plane = Plane(face.centroid, face.surface.normal)
        if any(_flush(face, region.patches[0], tol) for region in regions):
            continue
        flush = [other for other in flats if _flush(other, plane, tol)]
        regions.append(Region((plane,), _centroid(flush)))
    return tuple(regions)


def _flush(face: FaceInfo, patch: Patch, tol: float) -> bool:
    return isinstance(face.surface, Flat) and _coplanar(
        Plane(face.centroid, face.surface.normal), patch, tol
    )


def _coplanar(plane: Patch, patch: Patch, tol: float) -> bool:
    return (
        isinstance(plane, Plane)
        and isinstance(patch, Plane)
        and angle(plane.normal, patch.normal) <= ANGLE_TOL_RAD
        and abs(dot(sub(plane.point, patch.point), patch.normal)) <= tol
    )


def _bounding_flats(faces: Sequence[FaceInfo], tol: float) -> list[tuple[FaceInfo, Flat]]:
    return [
        (face, face.surface)
        for face in faces
        if isinstance(face.surface, Flat) and face.surface.beyond <= tol
    ]


def _projected(vector: Point, span: Sequence[Point]) -> Point:
    found: Point = (0.0, 0.0, 0.0)
    for axis in span:
        found = add(found, scale(axis, dot(vector, axis)))
    return found


def _same_line(first: Round, second: Round, tol: float) -> bool:
    offset = norm(cross(sub(second.origin, first.origin), first.axis))
    return _parallel(first.axis, second.axis) and offset <= tol


def _parallel(first: Point, second: Point) -> bool:
    return min(angle(first, second), angle(first, scale(second, -1))) <= ANGLE_TOL_RAD


def _normal_plane(axis: Point) -> tuple[Point, Point]:
    helper = min(
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), key=lambda e: abs(dot(e, axis))
    )
    first = unit(cross(axis, helper))
    return first, cross(axis, first)


def _centroid(faces: Sequence[FaceInfo]) -> Point:
    total = sum(face.area for face in faces)
    x, y, z = (sum(face.area * face.centroid[i] for face in faces) / total for i in range(3))
    return (x, y, z)


def _along(line: Round, v: float) -> Point:
    return add(line.origin, scale(line.axis, v))
