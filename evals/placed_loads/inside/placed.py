"""Runs in the analysis image. Turns a placement's face indices into the reviewed check's regions,
adds the mirror gate's candidates as the design note words it, and runs today's `fea` check with
these candidates passed in as a test resolver."""

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, TypedDict

from cad.checks.container import anchors, described, fea, terms
from cad.checks.container.check import Subject
from cad.checks.container.features import Geometry, centroid, holes, indices
from cad.checks.container.inputs import Inputs
from cad.checks.container.kernel import Curved, FaceInfo, Flat, Kernel, Round, Shape
from cad.checks.container.regions import (
    Bore,
    Candidate,
    Patch,
    Plane,
    Region,
    Resolved,
    Unresolved,
)
from cad.checks.container.runner import BrepFem
from cad.checks.container.vectors import Point, angle, norm, sub
from cad.checks.container.wire import FindingWire, LoadCaseWire, ValueWire

ALIKE_FRACTION: Final = described.TIE_FRACTION
ALIKE_RAD: Final = described.FACING_TOL_RAD
ANY_WAY: Final[tuple[Point, ...]] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
UNUSED_CASE: Final[LoadCaseWire] = {
    "support": {"kind": "largest_flat"},
    "load": {"kind": "far_end", "force_n": 1.0, "direction": {"kind": "any"}},
}
"""`fea.assessed` passes its case only to `anchors.resolve`, which the test resolver replaces."""


class CandidateWire(TypedDict):
    support: list[int]
    load: list[int]
    middle: bool


@dataclass(frozen=True, slots=True)
class Look:
    """A region the mirror gate compares: one face, or the bores of one hole."""

    faces: frozenset[int]
    centroid: Point
    direction: Point
    """The outward normal of a flat face, or the axis of a round face or a hole."""
    axis: bool
    """An axis has no sense, so the angle to it is folded into 0 to 90 degrees."""


def region(part: Geometry, faces: Sequence[int], middle: bool) -> Region | Unresolved:
    """A flat face gives a `Plane`, a round face a `Bore`, and a curved face no patch."""
    if middle:
        if len(faces) != 1 or not isinstance(part.faces[faces[0]].surface, Flat):
            return Unresolved("a press on the middle needs one flat face")
        return described.disc(part, faces[0])
    patches: list[Patch] = []
    for i in faces:
        face = part.faces[i]
        match face.surface:
            case Flat(normal):
                patches.append(Plane(face.centroid, normal))
            case Round(origin, axis, radius, v0, v1, _, _):
                patches.append(Bore(origin, axis, radius, v0, v1))
            case Curved():
                return Unresolved(f"face {i} is curved, so it has no patch")
    chosen = [part.faces[i] for i in faces]
    return Region(tuple(patches), centroid(chosen), frozenset(faces))


def share(part: Geometry, faces: frozenset[int]) -> float:
    return sum(part.faces[i].area for i in faces) / sum(face.area for face in part.faces)


def looks(part: Geometry, faces: frozenset[int]) -> tuple[Look, ...]:
    """The look-alikes of a region that is one face or the bores of one hole, itself first. Any
    other region has none but itself."""
    found = holes(part.faces, part.inertia)
    for hole in found:
        if indices(part.faces, hole.bores) != faces:
            continue
        alike = [h for h in found if h is not hole and _near(h.diameter, hole.diameter)]
        return tuple(
            Look(indices(part.faces, h.bores), centroid(h.bores), h.axis, True)
            for h in (hole, *alike)
        )
    own = _look(part, faces)
    if len(faces) != 1:
        return (own,)
    (i,) = faces
    alike = [j for j, other in enumerate(part.faces) if j != i and _alike(part.faces[i], other)]
    return (own, *(_look(part, frozenset({j})) for j in alike))


type Pair = tuple[Look, Look]


def mirrored(part: Geometry, support: frozenset[int], load: frozenset[int]) -> list[Pair]:
    """Each look-alike pair whose centroid distance is within 1% of the placed pair's and whose
    angle between directions is within 1 degree of it, the placed pair first."""
    supports = looks(part, support)
    loads = looks(part, load)
    distance, turn = _pair(supports[0], loads[0])
    pairs: list[Pair] = [(supports[0], loads[0])]
    for s in supports:
        for ld in loads:
            if (s, ld) == pairs[0] or s.faces & ld.faces:
                continue
            d, a = _pair(s, ld)
            if abs(d - distance) <= ALIKE_FRACTION * distance and abs(a - turn) <= ALIKE_RAD:
                pairs.append((s, ld))
    return pairs


def _pair(support: Look, load: Look) -> tuple[float, float]:
    turn = angle(support.direction, load.direction)
    if support.axis or load.axis:
        turn = min(turn, math.pi - turn)
    return norm(sub(support.centroid, load.centroid)), turn


def _look(part: Geometry, faces: frozenset[int]) -> Look:
    chosen = [part.faces[i] for i in sorted(faces)]
    first = chosen[0].surface
    match first:
        case Flat(normal):
            return Look(faces, centroid(chosen), normal, False)
        case Round(_, axis, _, _, _, _, _):
            return Look(faces, centroid(chosen), axis, True)
        case Curved():
            return Look(faces, centroid(chosen), (0.0, 0.0, 0.0), True)


def _alike(face: FaceInfo, other: FaceInfo) -> bool:
    if type(face.surface) is not type(other.surface) or isinstance(face.surface, Curved):
        return False
    if not _near(other.area, face.area):
        return False
    if isinstance(face.surface, Round) and isinstance(other.surface, Round):
        return _near(other.surface.radius, face.surface.radius)
    return True


def _near(value: float, reference: float) -> bool:
    return abs(value - reference) <= ALIKE_FRACTION * reference


def solved(
    kernel: Kernel,
    brep: bytes,
    shape: Shape,
    candidates: Sequence[Candidate],
    values: dict[str, ValueWire],
    force_n: float,
) -> tuple[FindingWire, float]:
    """Today's `fea` check, from the material through the gates, on these candidates."""
    resolved = Resolved(tuple(candidates))

    def test_resolver(case: terms.LoadCase, part: Geometry) -> Resolved | Unresolved:
        return resolved

    anchors.resolve = test_resolver
    subject = Subject(kernel, BrepFem(brep), shape, Inputs(fea.TAKES, values, ()), {})
    start = time.monotonic()
    found = fea.assessed(subject, shape, terms.of_wire(UNUSED_CASE), force_n)
    return found, time.monotonic() - start
