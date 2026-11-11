import math
from collections.abc import Sequence

from cad.checks.container import anchors
from cad.checks.container.anchors import (
    Bore,
    FarFrom,
    Region,
    Resolved,
    Unresolved,
    resolve,
)
from cad.checks.container.kernel import ocp_kernel
from cad.checks.container.wire import (
    DirectionWire,
    HolesWire,
    LoadCaseWire,
    LoadWire,
    SupportWire,
)
from tests.support.solids import Solid, box, cut, fillet_edges, fuse, rod, through_hole

KERNEL = ocp_kernel()
TOL = 1e-6
ANY: DirectionWire = {"kind": "any"}
ACROSS_HOLES: DirectionWire = {"kind": "across", "axis": "hole_axis"}
ALONG_LONG: DirectionWire = {"kind": "along", "axis": "long"}
LARGEST_FLAT: SupportWire = {"kind": "largest_flat"}
FLAT_END: SupportWire = {"kind": "flat_end"}

PLATE = cut(box(60, 20, 5), through_hole(5.5, 10, 10), through_hole(5.5, 50, 10))
THREE_HOLES = cut(PLATE, through_hole(5.5, 30, 10))
HANGER = cut(PLATE, through_hole(8, 30, 10))
POCKET = fillet_edges(
    box(15, 12, 4, at=(25, 4, 2)),
    2.75,
    lambda a, b: math.isclose(a[0], b[0]) and math.isclose(a[1], b[1]),
)
SLOT = fuse(
    box(10, 5.5, 7, at=(50, 7.25, -1)), rod(2.75, 7, (50, 10, -1)), rod(2.75, 7, (60, 10, -1))
)
FILLETED = cut(box(80, 20, 5), through_hole(5.5, 10, 10), through_hole(5.5, 70, 10), POCKET, SLOT)
COUNTERBORED = cut(
    box(40, 20, 8),
    through_hole(5.5, 10, 10, depth=8),
    rod(5, 4, (10, 10, 5)),
    through_hole(5.5, 30, 10, depth=8),
)
CROSSED = cut(
    box(40, 20, 20), through_hole(5.5, 30, 15, depth=20), rod(2.75, 42, (-1, 5, 10), (1, 0, 0))
)
BAR = box(100, 10, 6)
ROUNDED_BAR = fuse(BAR, rod(5, 6, (100, 5, 0)))
CUBE = box(10, 10, 10)
FLIPPED = cut(box(60, 20, 5), through_hole(5.5, 10, 10), rod(2.75, 7, (50, 10, 6), (0, 0, -1)))
PINNED = fuse(PLATE, rod(2.75, 4, (30, 10, 5)))


def holes(count: int, diameter_mm: float | None = 5.5) -> HolesWire:
    return {"kind": "holes", "count": count, "diameter_mm": diameter_mm}


def far_end(direction: DirectionWire = ANY) -> LoadWire:
    return {"kind": "far_end", "force_n": 49.0, "direction": direction}


def on_holes(count: int, diameter_mm: float | None) -> LoadWire:
    return {
        "kind": "on_holes",
        "count": count,
        "diameter_mm": diameter_mm,
        "force_n": 10.0,
        "direction": ACROSS_HOLES,
    }


def case(support: SupportWire, load: LoadWire | None = None) -> LoadCaseWire:
    return {"support": support, "load": far_end() if load is None else load}


def resolved(solid: Solid, wanted: LoadCaseWire) -> Resolved | Unresolved:
    return resolve(wanted, KERNEL.faces(solid), KERNEL.inertia(solid))


def must(solid: Solid, wanted: LoadCaseWire) -> Resolved:
    found = resolved(solid, wanted)
    assert isinstance(found, Resolved), found
    return found


def reason(solid: Solid, wanted: LoadCaseWire) -> str:
    found = resolved(solid, wanted)
    assert isinstance(found, Unresolved), found
    return found.reason


def held(solid: Solid, support: SupportWire) -> Region:
    found = anchors.support_regions(support, KERNEL.faces(solid), KERNEL.inertia(solid))
    assert not isinstance(found, Unresolved), found
    (region,) = found
    return region


def bores(region: Region | FarFrom) -> list[Bore]:
    assert isinstance(region, Region)
    found = [patch for patch in region.patches if isinstance(patch, Bore)]
    assert len(found) == len(region.patches)
    return found


def bore_ends(bore: Bore) -> list[tuple[float, ...]]:
    return sorted(
        tuple(round(o + t * a, 6) for o, a in zip(bore.origin, bore.axis, strict=True))
        for t in (bore.t0, bore.t1)
    )


def close(a: Sequence[float], b: Sequence[float], tol: float = TOL) -> bool:
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b, strict=True))
