import math
from datetime import date
from typing import Final

from cad.checks.container.check import DIMENSIONLESS, Subject, finding, measure, no_shape
from cad.checks.container.kernel import Unreadable
from cad.checks.container.wire import FindingWire, SourceLiteral

ID = "interference"
THRESHOLD_MM3: Final = 0.001
FORMULA = (
    "pass iff, for every pair of solids, the volume of their common part is at most 0.001 mm^3; "
    "one solid has no pairs and passes with bodies = 1"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_algo_a_p_i___common.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepAlgoAPI_Common Class",
        "page": "BRepAlgoAPI_Common, detailed description",
        "retrieved": date(2026, 11, 6),
        "standard": None,
        "quote": (
            "The class provides Boolean common operation between arguments and tools "
            "(Boolean Intersection)."
        ),
    },
)
MEASURES = {
    "bodies": DIMENSIONLESS,
    "interfering_pairs": DIMENSIONLESS,
    "max_common_volume": "mm^3",
    "common_volume": "mm^3",
}
REQUIRES = ()


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    kernel = subject.kernel
    bodies = kernel.solids(shape)
    if not bodies:
        return finding("unknown", "the shape has no solid to intersect")
    interfering: list[tuple[int, int, float]] = []
    undone: list[tuple[int, int]] = []
    largest = 0.0
    for first in range(len(bodies)):
        for second in range(first + 1, len(bodies)):
            common = kernel.common_volume(bodies[first], bodies[second])
            if common is None or not math.isfinite(common):
                undone.append((first, second))
                continue
            largest = max(largest, common)
            if common > THRESHOLD_MM3:
                interfering.append((first, second, common))
    measured = (
        measure("bodies", len(bodies), DIMENSIONLESS),
        measure("interfering_pairs", len(interfering), DIMENSIONLESS),
        measure("max_common_volume", largest, "mm^3"),
        *(measure(f"common_volume:{a}-{b}", volume, "mm^3") for a, b, volume in interfering),
    )
    skipped = "; ".join(f"solids {a} and {b} could not be intersected" for a, b in undone)
    if interfering:
        overlaps = "; ".join(
            f"solids {a} and {b} share {volume:g} mm^3" for a, b, volume in interfering
        )
        return finding("fail", overlaps + (f"; {skipped}" if skipped else ""), *measured)
    if undone:
        return finding("unknown", skipped, *measured)
    if len(bodies) == 1:
        return finding("pass", "one solid has no pair to intersect", *measured)
    return finding("pass", f"no two of {len(bodies)} solids share volume", *measured)
