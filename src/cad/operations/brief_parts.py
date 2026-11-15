"""The supplied parts a brief's card reads (ADR-0012)."""

from collections.abc import Sequence

from cad.briefs import store as briefs
from cad.briefs.model import ON_PART, Target
from cad.checks import jobs
from cad.context_parts.ids import ContextPartId
from cad.context_parts.model import ContextPartRecord, FromUpload
from cad.context_parts.store import ConfirmedPart, confirmed_parts, fit_targets, part_brep
from cad.records.roots import Roots
from cad.scorecard.supplied import FromOption, Named, Uploaded


def held(roots: Roots, brief_id: str) -> dict[str, Named]:
    """What the confirmed record of each part the brief's project holds says it is, by id."""
    project = briefs.read_brief(roots, brief_id).project
    return {one.record.id: named(one.record) for one in confirmed_parts(roots.projects, project)}


def named(record: ContextPartRecord) -> Named:
    source = record.source
    if isinstance(source, FromUpload):
        return Named(name=record.name, origin=Uploaded(file_name=source.file_name))
    return Named(name=record.name, origin=FromOption(variant_id=source.variant_id))


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
