import math
from collections.abc import Sequence
from datetime import date

from cad.checks.container import closed_solid
from cad.checks.container.anchors import (
    ANGLE_TOL_RAD,
    FULL_TURN_SLACK_RAD,
    OFFSET_TOL_FRACTION,
    Hole,
    extent,
    holes,
)
from cad.checks.container.check import (
    DIMENSIONLESS,
    CheckModule,
    Quick,
    Subject,
    finding,
    measure,
    no_shape,
    required_pass,
)
from cad.checks.container.inputs import Input
from cad.checks.container.kernel import Arc, Opening, Point, Unreadable
from cad.checks.container.vectors import angle, cross, norm, scale, sub
from cad.checks.container.wire import FindingWire, SourceLiteral

ID = "holes"
FORMULA = (
    "a hole is the concave cylindrical faces about one axis line whose angles add up to a full "
    "turn, so a counterbore's coaxial faces are one hole; its diameter is twice the smallest "
    "radius among them; every inner boundary of a flat face whose walls run into the material "
    "is an opening, and an opening is explained when it is one full circle, coaxial with a hole "
    "and no narrower than that hole; hole_diameter:i lists the holes from the narrowest, "
    "hole_count their number and unclassified_openings the openings no hole explains, which are "
    "not round holes, as a slot, a polygon and an oval are not; unknown, with the diameters "
    "kept, when any opening is unclassified, and unknown with no measured value unless "
    "closed_solid passes"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_tools.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepTools Class",
        "page": "BRepTools::OuterWire",
        "retrieved": date(2026, 11, 11),
        "standard": None,
        "quote": "Returns the outer most wire of <F>. Returns a Null wire if <F> has no wires.",
    },
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_adaptor___curve.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepAdaptor_Curve Class",
        "page": "BRepAdaptor_Curve::GetType",
        "retrieved": date(2026, 11, 11),
        "standard": None,
        "quote": (
            "Returns the type of the curve in the current interval: Line, Circle, Ellipse, "
            "Hyperbola, Parabola, BezierCurve, BSplineCurve, OtherCurve."
        ),
    },
)
MEASURES = {
    "hole_count": DIMENSIONLESS,
    "hole_diameter": "mm",
    "unclassified_openings": DIMENSIONLESS,
}
TAKES: frozenset[Input] = frozenset()
READS: dict[str, Input] = {}
REQUIRES: tuple[CheckModule, ...] = (closed_solid,)
BUDGET = Quick()
ERROR_BOUNDS: dict[str, float] = {}


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    unmet = required_pass(subject, REQUIRES, "look for holes in")
    if unmet is not None:
        return unmet
    kernel = subject.kernel
    inertia = kernel.inertia(shape)
    found = holes(kernel.faces(shape), inertia)
    tol = OFFSET_TOL_FRACTION * extent(inertia)
    open_ended = sum(not explained(one, found, tol) for one in kernel.openings(shape))
    diameters = sorted(hole.diameter for hole in found)
    measured = (
        measure("hole_count", len(diameters), DIMENSIONLESS),
        *(measure(f"hole_diameter:{at}", size, "mm") for at, size in enumerate(diameters)),
        measure("unclassified_openings", open_ended, DIMENSIONLESS),
    )
    sizes = ", ".join(f"{size:g}" for size in diameters) or "none"
    if open_ended:
        return finding(
            "unknown",
            f"{open_ended} openings are not round holes (a slot, a polygon, an oval or a circle "
            f"no hole explains), so the holes are not all measured; round holes in mm: {sizes}",
            *measured,
        )
    return finding("pass", f"{len(diameters)} round holes, diameters in mm: {sizes}", *measured)


def explained(opening: Opening, found: Sequence[Hole], tol: float) -> bool:
    circle = whole_circle(opening, tol)
    return circle is not None and any(
        _coaxial(circle, hole, tol) and circle.radius >= hole.radius - tol for hole in found
    )


def whole_circle(opening: Opening, tol: float) -> Arc | None:
    """The circle an opening is, when its edges are arcs of one circle that add up to a full
    turn; None for any other opening."""
    arcs = [edge for edge in opening.edges if edge is not None]
    if not arcs or len(arcs) != len(opening.edges):
        return None
    first = arcs[0]
    same = all(
        _parallel(arc.axis, first.axis)
        and norm(sub(arc.center, first.center)) <= tol
        and abs(arc.radius - first.radius) <= tol
        for arc in arcs
    )
    if not same or sum(arc.sweep for arc in arcs) < 2 * math.pi - FULL_TURN_SLACK_RAD:
        return None
    return first


def _coaxial(circle: Arc, hole: Hole, tol: float) -> bool:
    offset = norm(cross(sub(circle.center, hole.origin), hole.axis))
    return _parallel(circle.axis, hole.axis) and offset <= tol


def _parallel(first: Point, second: Point) -> bool:
    return min(angle(first, second), angle(first, scale(second, -1))) <= ANGLE_TOL_RAD
