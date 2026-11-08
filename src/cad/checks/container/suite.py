from typing import Final

from cad.checks.container import closed_solid, extents, interference, mass
from cad.checks.container.check import CheckModule

CHECKS: Final[tuple[CheckModule, ...]] = (closed_solid, interference, mass, extents)
