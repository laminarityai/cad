import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, assert_never

from cad.checks.container.kernel import FaceInfo, Flat, Inertia, Point, Round
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
END_ANGLE_TOL_RAD: Final = 1e-3
FLUSH_TOL_FRACTION: Final = 1e-4
LONG_TIE_FRACTION: Final = 0.01
FAR_FRACTION: Final = 0.005
OFF_CENTER_FRACTION: Final = 0.01


@dataclass(frozen=True, slots=True)
class Bore:
    """The cylinder at `radius` around origin + t * axis, for t from t0 to t1."""

    origin: Point
    axis: Point
    radius: float
    t0: float
    t1: float


@dataclass(frozen=True, slots=True)
class Plane:
    point: Point
    normal: Point
    """Unit, pointing out of the material."""


type Patch = Bore | Plane


@dataclass(frozen=True, slots=True)
class Region:
    patches: tuple[Patch, ...]
    centroid: Point
    """The area-weighted centroid of the faces the anchor selected."""


@dataclass(frozen=True, slots=True)
class FarFrom:
    center: Point
    axis: Point
    """Unit, from the support toward the part's centre of mass."""

    def reach(self, point: Point) -> float:
        return dot(sub(point, self.center), self.axis)

    def cutoff(self, surface: Sequence[Point]) -> float:
        return (1 - FAR_FRACTION) * max(self.reach(point) for point in surface)


@dataclass(frozen=True, slots=True)
class Candidate:
    support: Region
    load: Region | FarFrom


@dataclass(frozen=True, slots=True)
class Resolved:
    candidates: tuple[Candidate, ...]
    basis: tuple[Point, ...]
    """An orthonormal basis of the directions the load may take."""


@dataclass(frozen=True, slots=True)
class Unresolved:
    reason: str


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
                ends = far_from(support, inertia)
                if isinstance(ends, Unresolved):
                    return ends
                candidates.extend(Candidate(support, far) for far in ends)
            return Resolved(tuple(candidates), basis)
        case "on_holes":
            loaded = load_holes(load, case["support"], faces, inertia)
            if isinstance(loaded, Unresolved):
                return loaded
            return Resolved(tuple(Candidate(s, loaded) for s in supports), basis)
        case _:
            assert_never(load["kind"])


def far_from(support: Region, inertia: Inertia) -> tuple[FarFrom, ...] | Unresolved:
    toward = sub(inertia.center, support.centroid)
    if norm(toward) > OFF_CENTER_FRACTION * extent(inertia):
        return (FarFrom(support.centroid, unit(toward)),)
    long = long_axis(inertia)
    if isinstance(long, Unresolved):
        return Unresolved(
            "the support sits at the part's centre of mass and the part has no unique long "
            "axis, so no end of the part is the far one"
        )
    _, axis = long
    return (FarFrom(support.centroid, axis), FarFrom(support.centroid, scale(axis, -1)))


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
    long = long_axis(inertia)
    if isinstance(long, Unresolved):
        return long
    index, axis = long
    tol = FLUSH_TOL_FRACTION * extent(inertia)
    regions: list[Region] = []
    for sign, extreme in ((1.0, inertia.spans[index][1]), (-1.0, inertia.spans[index][0])):
        outward = scale(axis, sign)
        at_end = [
            face
            for face in faces
            if isinstance(face.surface, Flat)
            and angle(face.surface.normal, outward) <= END_ANGLE_TOL_RAD
            and abs(dot(sub(face.centroid, inertia.center), axis) - extreme) <= tol
        ]
        if at_end:
            regions.extend(_distinct_planes(at_end, at_end, inertia))
    if not regions:
        return Unresolved("neither end of the long axis is a flat face")
    return tuple(regions)


def long_axis(inertia: Inertia) -> tuple[int, Point] | Unresolved:
    spreads = sorted(((s, i) for i, s in enumerate(second_moments(inertia))), reverse=True)
    (first, index), (second, _) = spreads[0], spreads[1]
    if first - second <= LONG_TIE_FRACTION * first:
        return Unresolved(
            "the part has no unique long axis: its two largest volume spreads are within 1%"
        )
    return index, inertia.axes[index]


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
        long = long_axis(inertia)
        return long if isinstance(long, Unresolved) else long[1]
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
    return (
        isinstance(face.surface, Flat)
        and isinstance(patch, Plane)
        and angle(face.surface.normal, patch.normal) <= ANGLE_TOL_RAD
        and abs(dot(sub(face.centroid, patch.point), patch.normal)) <= tol
    )


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
