from datetime import UTC, datetime
from typing import Final

from cad.sandbox.bodies import BODIES, Bodies
from cad.variant_sets.model import BodyChoice, MaterialChoice, Revision
from cad.variants.entry import VariantId

PLATE: Final = "polymaker-fiberon-pa6-cf20"
GEAR: Final = "cliffs-hot-rolled-cs-type-b"
PLATE_AND_GEARS: Final[Bodies] = BODIES.validate_python(
    [{"name": "plate", "solids": (0,)}, {"name": "gear", "solids": (1, 2)}]
)
ONE_NAMED: Final[Bodies] = BODIES.validate_python([{"name": "plate", "solids": (0, 1)}])


def revision(
    materials: tuple[BodyChoice, ...] = (), material: MaterialChoice | None = None
) -> Revision:
    return Revision(
        slot=1,
        code="result = None",
        code_sha256="c" * 64,
        built_as=VariantId("v" * 16),
        joined_at=datetime(2026, 11, 13, tzinfo=UTC),
        material=material,
        materials=materials,
    )
