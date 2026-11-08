from datetime import date

from cad.checks.container import closed_solid
from cad.checks.container.check import CheckModule, Subject, finding, measure, no_shape
from cad.checks.container.kernel import Unreadable
from cad.checks.container.wire import FindingWire, SourceLiteral

ID = "extents"
FORMULA = (
    "extent along each of x, y and z = max - min of the axis-aligned bounding box of the shape "
    "in the BREP's own frame, built from the shape's geometry with no tolerance gap added; the "
    "sorted extents are the same three numbers from smallest to largest; unknown, with no "
    "measured value, unless closed_solid passes"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_bnd_lib.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepBndLib Class",
        "page": "BRepBndLib::AddOptimal",
        "retrieved": date(2026, 11, 7),
        "standard": None,
        "quote": (
            "This algorithm builds precise bounding box, which differs from exact geometry "
            "boundaries of shape only on shape entities tolerances"
        ),
    },
)
MEASURES = {
    "extent": "mm",
    "sorted_extent": "mm",
}
READS: dict[str, str] = {}
REQUIRES: tuple[CheckModule, ...] = (closed_solid,)
SORTED_NAMES = ("smallest", "middle", "largest")


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    for required in REQUIRES:
        found = required.run(subject)
        if found["verdict"] != "pass":
            return finding(
                "unknown",
                f"{required.ID} is {found['verdict']}, so there is no one solid to "
                f"measure: {found['reason']}",
            )
    extents = subject.kernel.extents(shape)
    if extents is None:
        return finding("unknown", "the kernel found no finite bounding box for the shape")
    x, y, z = extents
    return finding(
        "pass",
        f"{x:g} x {y:g} x {z:g} mm along x, y and z",
        measure("extent:x", x, "mm"),
        measure("extent:y", y, "mm"),
        measure("extent:z", z, "mm"),
        *(
            measure(f"sorted_extent:{name}", value, "mm")
            for name, value in zip(SORTED_NAMES, sorted(extents), strict=True)
        ),
    )
