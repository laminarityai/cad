"""The supplied parts a brief's card reads (ADR-0012)."""

from collections.abc import Sequence

from cad.briefs import store as briefs
from cad.briefs.model import ON_PART, Target
from cad.checks import jobs
from cad.context_parts.ids import ContextPartId
from cad.context_parts.store import ConfirmedPart, confirmed_parts, fit_targets, part_brep
from cad.records.roots import Roots


def held(roots: Roots, brief_id: str) -> frozenset[str]:
    """The id of each part the brief's project confirmed."""
    project = briefs.read_brief(roots, brief_id).project
    return frozenset(one.record.id for one in confirmed_parts(roots.projects, project))


def measured(roots: Roots, brief_id: str, targets: Sequence[Target]) -> tuple[ConfirmedPart, ...]:
    """The parts the brief's fit check measures, given the targets its card shows."""
    project = briefs.read_brief(roots, brief_id).project
    named = frozenset(one.part for one in targets if isinstance(one, ON_PART))
    return fit_targets(roots.projects, project, brief_id, named)


def context(
    roots: Roots, brief_id: str, targets: Sequence[Target]
) -> dict[ContextPartId, jobs.PartBrep]:
    return {
        part.record.id: jobs.PartBrep(part.record.brep_sha256, part_brep(roots.projects, part))
        for part in measured(roots, brief_id, targets)
    }
