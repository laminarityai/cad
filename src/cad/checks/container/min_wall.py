import math
import time
from dataclasses import dataclass
from datetime import date

from cad.checks.container import closed_solid
from cad.checks.container.check import (
    CheckModule,
    Quick,
    Subject,
    finding,
    measure,
    no_shape,
    required_pass,
)
from cad.checks.container.inputs import Input
from cad.checks.container.kernel import Across, Lost, Patch, Shape, Unreadable, Walls
from cad.checks.container.wire import FindingWire, SourceLiteral

ID = "min_wall"
FORMULA = (
    "a wall's thickness at a point on a face is how far a ray goes from that point straight into "
    "the material, along the face's inward normal, until it first comes out through a face that "
    "looks back within 60 degrees; a ray that comes out through a face turned further, as near "
    "a corner, gives no reading; a variant of named bodies is measured one solid at a time, "
    "each solid on a grid of its own as if it were alone, and a body's wall is the thinnest "
    "of its solids'; every face of a solid is sampled on a grid of 2 by 2 points, then again with "
    "points no farther apart than the thinnest of those readings and than the closest spacing "
    "whose grid over all the solid's faces fits in 40000 points; from the thinnest point of each "
    "of the at most 32 thinnest faces within 1.5 times the thinnest reading, a compass search "
    "walks to a local minimum; min_wall is the thinnest reading of all; unknown when a ray never "
    "comes out of the material or the kernel cannot follow it, when no ray from a solid crosses "
    "a wall, when a solid has more than 10000 faces or needs more than 250000 rays, or all the "
    "solids together need more than 30 seconds, and with no measured value unless closed_solid "
    "passes"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_int_curves_face___intersector.html",
        "title": "Open CASCADE Technology Reference Manual: IntCurvesFace_Intersector Class",
        "page": "IntCurvesFace_Intersector::WParameter",
        "retrieved": date(2026, 11, 11),
        "standard": None,
        "quote": "Returns the parameter of the ith intersection point on the line.",
    },
)
MEASURES = {"min_wall": "mm"}
TAKES: frozenset[Input] = frozenset()
READS: dict[str, Input] = {}
REQUIRES: tuple[CheckModule, ...] = (closed_solid,)
BUDGET = Quick()
ERROR_BOUNDS = {"min_wall": 0.001}

FIRST_SAMPLES = 2
GRID_POINTS = 40_000
REFINE_WITHIN = 1.5
REFINE_FACES = 32
STOP_FRACTION = 1e-6
MAX_RAYS = 250_000
MAX_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class Sample:
    length: float
    u: float
    v: float


class Halted(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Search:
    """Counts every ray against the caps, so a large part stops early as unknown."""

    def __init__(self, walls: Walls, deadline: float | None = None) -> None:
        self.walls = walls
        self.rays = 0
        self._deadline = time.monotonic() + MAX_SECONDS if deadline is None else deadline

    def length(self, face: int, u: float, v: float) -> float | None:
        if self.rays >= MAX_RAYS:
            raise Halted(f"the part needs more than {MAX_RAYS} rays")
        if time.monotonic() > self._deadline:
            raise Halted(f"the rays took longer than {MAX_SECONDS:g} seconds")
        found = self.walls.reading(face, u, v)
        self.rays += found is not None
        if isinstance(found, Lost):
            raise Halted(found.reason)
        return found.length if isinstance(found, Across) else None

    def thinnest_on(self, face: int, counts: tuple[int, int]) -> Sample | None:
        patch = self.walls.patches[face]
        best: Sample | None = None
        for u in _centres(patch.u0, patch.u1, counts[0]):
            for v in _centres(patch.v0, patch.v1, counts[1]):
                length = self.length(face, u, v)
                if length is not None and (best is None or length < best.length):
                    best = Sample(length, u, v)
        return best

    def refine(self, face: int, start: Sample, counts: tuple[int, int]) -> float:
        """A compass search: step to a neighbour that reads thinner, else halve the step."""
        patch = self.walls.patches[face]
        span_u, span_v = patch.u1 - patch.u0, patch.v1 - patch.v0
        step_u, step_v = span_u / counts[0], span_v / counts[1]
        here = start
        while step_u > span_u * STOP_FRACTION or step_v > span_v * STOP_FRACTION:
            moved = False
            for du, dv in ((step_u, 0.0), (-step_u, 0.0), (0.0, step_v), (0.0, -step_v)):
                length = self.length(face, here.u + du, here.v + dv)
                if length is not None and length < here.length:
                    here, moved = Sample(length, here.u + du, here.v + dv), True
                    break
            if not moved:
                step_u, step_v = step_u / 2, step_v / 2
        return here.length


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    unmet = required_pass(subject, REQUIRES, "measure the walls of")
    if unmet is not None:
        return unmet
    if subject.bodies:
        return _each_body(subject, shape)
    search = Search(subject.kernel.walls(shape))
    try:
        found = thinnest(search)
    except Halted as halted:
        return finding("unknown", f"the walls are not measured: {halted.reason}")
    if found is None:
        return finding("unknown", "no ray from any face crossed a wall")
    wall, spacing = found
    return finding(
        "pass",
        f"thinnest wall {wall:.4g} mm, from {search.rays} rays with samples no farther apart "
        f"than {spacing:.3g} mm",
        measure("min_wall", wall, "mm"),
    )


def _each_body(subject: Subject, shape: Shape) -> FindingWire:
    """Each solid on a grid of its own, as it would be read alone, so a body of many solids is
    never sampled more coarsely. One deadline covers every solid."""
    kernel = subject.kernel
    solids = kernel.solids(shape)
    deadline = time.monotonic() + MAX_SECONDS
    walls: list[tuple[str, float, float]] = []
    for body in subject.bodies:
        found: list[tuple[float, float]] = []
        for solid in (solids[index] for index in body.solids):
            try:
                one = thinnest(Search(kernel.walls(solid), deadline))
            except Halted as halted:
                return finding(
                    "unknown", f"the walls of {body.name} are not measured: {halted.reason}"
                )
            if one is None:
                return finding(
                    "unknown", f"no ray from any face of a solid of {body.name} crossed a wall"
                )
            found.append(one)
        walls.append((body.name, *min(found)))
    name, wall, spacing = min(walls, key=lambda one: one[1])
    return finding(
        "pass",
        f"thinnest wall {wall:.4g} mm, in {name}, with samples no farther apart than "
        f"{spacing:.3g} mm there",
        measure("min_wall", wall, "mm"),
        *(measure(f"min_wall:{body}", thick, "mm") for body, thick, _ in walls),
    )


def thinnest(search: Search) -> tuple[float, float] | None:
    """The thinnest wall and the sample spacing it was found at, or None with no reading."""
    patches = search.walls.patches
    counts = [(FIRST_SAMPLES, FIRST_SAMPLES)] * len(patches)
    best = [search.thinnest_on(face, counts[face]) for face in range(len(patches))]
    first = _least(best)
    if first is None:
        return None
    spacing = min(first, _closest_spacing(patches))
    for face, patch in enumerate(patches):
        wanted = _counts(patch, spacing)
        if wanted != counts[face]:
            counts[face] = wanted
            best[face] = search.thinnest_on(face, wanted)
    second = _least(best)
    if second is None:
        return None
    near = sorted(
        (sample.length, face)
        for face, sample in enumerate(best)
        if sample is not None and sample.length <= REFINE_WITHIN * second
    )
    wall = second
    for _, face in near[:REFINE_FACES]:
        sample = best[face]
        assert sample is not None
        wall = min(wall, search.refine(face, sample, counts[face]))
    return wall, spacing


def _closest_spacing(patches: tuple[Patch, ...]) -> float:
    """The smallest spacing whose grid over every face fits in GRID_POINTS points."""
    if FIRST_SAMPLES**2 * len(patches) > GRID_POINTS:
        raise Halted(f"the part has more than {GRID_POINTS // FIRST_SAMPLES**2} faces")
    low, high = 0.0, max(max(p.length_u, p.length_v) for p in patches) + 1.0
    for _ in range(60):
        middle = (low + high) / 2
        if sum(a * b for a, b in (_counts(p, middle) for p in patches)) > GRID_POINTS:
            low = middle
        else:
            high = middle
    return high


def _counts(patch: Patch, spacing: float) -> tuple[int, int]:
    return (
        max(FIRST_SAMPLES, math.ceil(patch.length_u / spacing)),
        max(FIRST_SAMPLES, math.ceil(patch.length_v / spacing)),
    )


def _least(samples: list[Sample | None]) -> float | None:
    lengths = [sample.length for sample in samples if sample is not None]
    return min(lengths) if lengths else None


def _centres(low: float, high: float, count: int) -> list[float]:
    return [low + (k + 0.5) / count * (high - low) for k in range(count)]
