"""Whether a proposed agent_limit requirement can hold its check to the person's number."""

from collections.abc import Sequence
from pathlib import Path

from cad.agent_checks.formula import dimension_of
from cad.agent_checks.model import UNITS
from cad.agent_checks.store import checks_of
from cad.briefs.model import AgentLimit, Target
from cad.briefs.store import BadProposal
from cad.projects.model import ProjectId


def check_proposed(
    projects: Path, project: ProjectId, brief_id: str, targets: Sequence[Target]
) -> None:
    """Raises BadProposal for the first agent_limit that names no check of this brief, or whose
    comparator or limit does not fit the check."""
    held = {one.sha256: one.check for one in checks_of(projects, project)}
    for index, target in enumerate(targets):
        if not isinstance(target, AgentLimit):
            continue
        check = held.get(target.check_sha256)
        problem = None
        if check is None:
            problem = (
                f"names agent-written check {target.check_sha256}, which project {project} does "
                "not hold: write_check stores one and returns its check_sha256"
            )
        elif check.brief_id != brief_id:
            problem = f"names a check written for brief {check.brief_id}, not {brief_id}"
        elif target.comparator is not check.comparator:
            problem = f"has comparator {target.comparator}, but the check is {check.comparator}"
        elif check.limit_source is not None and target.limit is not None:
            problem = (
                f"gives a limit, but the check reads its limit from source {check.limit_source}: "
                "pass limit null"
            )
        elif target.limit is None and check.limit_source is None:
            problem = "gives no limit, and the check's sources write none: pass the person's number"
        elif target.limit is not None and target.limit.dimensionality != dimension_of(
            UNITS[check.unit]
        ):
            problem = f"gives its limit in {target.limit.units:~}, not a unit like {check.unit}"
        if problem is not None:
            raise BadProposal(f"requirements[{index}] {problem}")
