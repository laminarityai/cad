"""Host solids and helpers for the described load case terms."""

from cad.checks.container.anchors import resolve
from cad.checks.container.features import geometry
from cad.checks.container.regions import Resolved, Unresolved
from cad.checks.container.terms import (
    Away,
    Each,
    Facing,
    LoadCase,
    OnFarthest,
    OnOpposite,
)
from tests.support.anchors import KERNEL, L_BRACKET
from tests.support.solids import Solid, box, cut, rod, through_hole


def clamp(gap: float) -> Solid:
    """A C frame 60 x 20 x 50 mm open toward +x, its jaws 15 mm thick across a gap of `gap`."""
    jaw = (50 - gap) / 2
    return cut(box(60, 20, 50), box(50, 22, gap, at=(15, -1, jaw)))


CLAMP = clamp(20)
HOOK = cut(
    box(60, 20, 10),
    through_hole(5, 8, 10, depth=10),
    through_hole(5, 22, 10, depth=10),
    rod(6, 12, (60, 10, -1)),
)
"""Held by 2 holes of 5 mm, with a half-round notch of 12 mm at its far end as its curl."""
RAIL_HOOK = cut(box(60, 20, 10), rod(6, 12, (0, 10, -1)), rod(6, 12, (60, 10, -1)))
"""A half-round notch of 12 mm at each end."""
TWO_LEGS = cut(
    L_BRACKET,
    *(rod(2.25, 7, (-1, 15, z), (1, 0, 0)) for z in (-12, -35)),
    through_hole(4.5, 50, 15),
    through_hole(4.5, 80, 15),
)
"""An L bracket with 2 holes of 4.5 mm through each leg."""
THIRD_HOLE = cut(TWO_LEGS, through_hole(4.5, 65, 15))
FIVE_HOLES = cut(box(100, 20, 5), *(through_hole(5.5, x, 10) for x in (10, 30, 50, 70, 90)))
PLATE_80 = box(80, 40, 6)
CUBOID = box(80, 30, 30)
"""Its middle and short spreads tie."""
POCKETED = cut(PLATE_80, box(20, 20, 3, at=(30, 10, -1)))
"""Its top face is its one largest flat face."""
RAIL = rod(5, 100, (0, 0, 0), (1, 0, 0))

HUNG = LoadCase(Each("inner_curve", None), OnFarthest("inner_curve", None), Away())
CLAMPED = LoadCase(Facing(), OnOpposite(middle=False), Away())


def resolved(solid: Solid, case: LoadCase) -> Resolved | Unresolved:
    return resolve(case, geometry(KERNEL, solid))


def must(solid: Solid, case: LoadCase) -> Resolved:
    found = resolved(solid, case)
    assert isinstance(found, Resolved), found
    return found


def reason(solid: Solid, case: LoadCase) -> str:
    found = resolved(solid, case)
    assert isinstance(found, Unresolved), found
    return found.reason
