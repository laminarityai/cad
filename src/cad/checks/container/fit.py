import math
from datetime import date
from typing import Final

from cad.checks.container import interference
from cad.checks.container.check import (
    DIMENSIONLESS,
    Background,
    CheckModule,
    Subject,
    finding,
    measure,
    no_shape,
)
from cad.checks.container.inputs import Input
from cad.checks.container.kernel import Unreadable
from cad.checks.container.whole_solids import unmeasurable
from cad.checks.container.wire import FindingWire, SourceLiteral

ID = "fit"
TOUCHING_MM: Final = 1e-7
CLEARANCE_DIGITS: Final = 6
FORMULA = (
    "against one confirmed context part: overlap_volume is the sum over every pair of a context "
    "solid and a variant solid of the volume of their common part; when it is over 0.001 mm^3 "
    "the verdict is fail and min_clearance is 0, otherwise min_clearance is the least minimum "
    "distance over the pairs, rounded to 1e-6 mm, and under 1e-7 mm reads as 0; unknown when "
    "interference does not pass, either shape has sub-shapes outside its solids, a solid "
    "BRepCheck calls invalid or a tolerance over 0.001 mm, or a Boolean or distance is not done"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_algo_a_p_i___common.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepAlgoAPI_Common Class",
        "page": "BRepAlgoAPI_Common, detailed description",
        "retrieved": date(2026, 11, 8),
        "standard": None,
        "quote": (
            "The class provides Boolean common operation between arguments and tools "
            "(Boolean Intersection)."
        ),
    },
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_extrema___dist_shape_shape.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepExtrema_DistShapeShape Class",
        "page": "BRepExtrema_DistShapeShape, detailed description",
        "retrieved": date(2026, 11, 8),
        "standard": None,
        "quote": (
            "This class provides tools to compute minimum distance between two Shapes "
            "(Compound,CompSolid, Solid, Shell, Face, Wire, Edge, Vertex)."
        ),
    },
)
MEASURES = {
    "overlap_volume": "mm^3",
    "min_clearance": "mm",
    "context_solids": DIMENSIONLESS,
    "variant_solids": DIMENSIONLESS,
}
TAKES: frozenset[Input] = frozenset()
READS: dict[str, Input] = {}
REQUIRES: tuple[CheckModule, ...] = (interference,)
BUDGET = Background(wall_seconds=60, memory_mb=2048, tmpfs_mb=256)
ERROR_BOUNDS: dict[str, float] = {}


def run(subject: Subject) -> FindingWire:
    shape, context = subject.shape, subject.context
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    if context is None:
        return finding("unknown", "the host sent no context part to measure against")
    if isinstance(context, Unreadable):
        return finding("unknown", f"the context part cannot be read: {context.reason}")
    own = subject.reported[interference.ID]
    if own["verdict"] != "pass":
        return finding(
            "unknown",
            f"interference is {own['verdict']}, so the variant's own solids may overlap and "
            f"their common part with the context part cannot be trusted: {own['reason']}",
        )
    kernel = subject.kernel
    for side, one in (("variant", shape), ("context part", context)):
        problem = unmeasurable(kernel, one)
        if problem is not None:
            return finding("unknown", f"the {side} {problem}")
    parts, variant = kernel.solids(context), kernel.solids(shape)
    pairs = [(a, b) for a in range(len(parts)) for b in range(len(variant))]
    counts = (
        measure("context_solids", len(parts), DIMENSIONLESS),
        measure("variant_solids", len(variant), DIMENSIONLESS),
    )
    overlap = 0.0
    for a, b in pairs:
        common = kernel.common_volume(parts[a], variant[b])
        if common is None or not math.isfinite(common):
            return finding(
                "unknown", f"context solid {a} and variant solid {b} could not be intersected"
            )
        overlap += common
    overlapped = measure("overlap_volume", overlap, "mm^3")
    if overlap > interference.THRESHOLD_MM3:
        return finding(
            "fail",
            f"the variant shares {overlap:g} mm^3 with the context part",
            overlapped,
            measure("min_clearance", 0.0, "mm"),
            *counts,
        )
    distances: list[float] = []
    for a, b in pairs:
        distance = kernel.min_distance(parts[a], variant[b])
        if distance is None or not math.isfinite(distance):
            return finding(
                "unknown",
                f"the distance from context solid {a} to variant solid {b} could not be measured",
                overlapped,
                *counts,
            )
        distances.append(distance)
    nearest = min(distances)
    clearance = 0.0 if nearest < TOUCHING_MM else round(nearest, CLEARANCE_DIGITS)
    return finding(
        "pass",
        f"no overlap with the context part; the least clearance is {clearance:g} mm",
        overlapped,
        measure("min_clearance", clearance, "mm"),
        *counts,
    )
