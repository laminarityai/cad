"""BRepCheck_Analyzer alone calls a shell with a missing face valid, so the free-edge count is
load-bearing.
"""

from datetime import date

from cad.checks.container.check import DIMENSIONLESS, Subject, finding, measure
from cad.checks.container.kernel import Unreadable
from cad.checks.container.wire import FindingWire, SourceLiteral

ID = "closed_solid"
FORMULA = (
    "pass iff solids = 1 and shapes_outside_solids = 0 and free_edges = 0 and "
    "over_used_edges = 0 and valid = 1, where shapes_outside_solids counts the shells, faces, "
    "edges and vertices that no solid contains, and free_edges and over_used_edges count edges "
    "used by exactly one and by more than two faces of the whole shape, skipping degenerated "
    "edges"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_check___analyzer.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepCheck_Analyzer Class",
        "page": "BRepCheck_Analyzer, detailed description",
        "retrieved": date(2026, 11, 6),
        "standard": None,
        "quote": "A framework to check the overall validity of a shape.",
    },
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_top_exp.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: TopExp Class",
        "page": "TopExp::MapShapesAndAncestors",
        "retrieved": date(2026, 11, 6),
        "standard": None,
        "quote": "For example map all the edges and bind the list of faces.",
    },
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_top_exp___explorer.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: TopExp_Explorer Class",
        "page": "TopExp_Explorer, detailed description",
        "retrieved": date(2026, 11, 6),
        "standard": None,
        "quote": (
            "The Explorer visits all the structure to find shapes of the requested type which "
            "are not contained in the type to avoid."
        ),
    },
)
MEASURES = {
    "solids": DIMENSIONLESS,
    "shapes_outside_solids": DIMENSIONLESS,
    "free_edges": DIMENSIONLESS,
    "over_used_edges": DIMENSIONLESS,
    "valid": DIMENSIONLESS,
}
READS: dict[str, str] = {}
REQUIRES = ()


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return finding("fail", f"the BREP could not be read: {shape.reason}")
    kernel = subject.kernel
    solids = len(kernel.solids(shape))
    outside = kernel.outside_solids(shape)
    valid = kernel.is_valid(shape)
    uses = kernel.edge_uses(shape)
    measured = (
        measure("solids", solids, DIMENSIONLESS),
        measure("shapes_outside_solids", outside, DIMENSIONLESS),
        measure("free_edges", uses.free, DIMENSIONLESS),
        measure("over_used_edges", uses.over_used, DIMENSIONLESS),
        measure("valid", valid, DIMENSIONLESS),
    )
    problems = [
        *([f"found {solids} solids; exactly 1 is required"] if solids != 1 else []),
        *([f"{outside} shells, faces, edges or vertices lie outside any solid"] if outside else []),
        *(["BRepCheck_Analyzer calls the shape invalid"] if not valid else []),
        *([f"{uses.free} edges are used by one face"] if uses.free else []),
        *([f"{uses.over_used} edges are used by more than two faces"] if uses.over_used else []),
    ]
    if problems:
        return finding("fail", "; ".join(problems), *measured)
    return finding("pass", "one valid solid, every edge shared by two faces", *measured)
