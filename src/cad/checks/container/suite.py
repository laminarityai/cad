from collections.abc import Iterable
from typing import Final

from cad.checks.container import closed_solid, extents, fea, fit, holes, interference, mass
from cad.checks.container.check import CheckModule

CHECKS: Final[tuple[CheckModule, ...]] = (
    closed_solid,
    interference,
    mass,
    extents,
    holes,
    fea,
    fit,
)


def with_requirements(check_ids: Iterable[str]) -> tuple[CheckModule, ...]:
    by_id = {check.ID: check for check in CHECKS}
    wanted: set[str] = set()
    pending: list[CheckModule] = [by_id[check_id] for check_id in check_ids]
    while pending:
        check = pending.pop()
        wanted.add(check.ID)
        pending.extend(check.REQUIRES)
    return tuple(check for check in CHECKS if check.ID in wanted)
