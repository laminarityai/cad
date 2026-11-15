"""The supplied parts a build reads, and which of them it may place (ADR-0012)."""

from collections.abc import Sequence
from typing import Annotated, Final

from pydantic import Field

from cad.briefs import store as briefs
from cad.context_parts.ids import PART_ID_PATTERN
from cad.context_parts.store import BadContextPart, ConfirmedPart, confirmed_parts, part_brep
from cad.operations.model import Input, Tenant
from cad.operations.scorecards import fit_parts
from cad.sandbox.builder import Supplied
from cad.sandbox.outcome import PartPlacement, PartUse

MAX_PARTS: Final = 8
MAX_PLACEMENTS: Final = 32
NOTHING_BUILT: Final = "Nothing was built."


class PartInput(Input):
    part_id: Annotated[str, Field(pattern=PART_ID_PATTERN)]
    placements: Annotated[tuple[PartPlacement, ...], Field(max_length=MAX_PLACEMENTS)] = ()


type Parts = Annotated[tuple[PartInput, ...], Field(max_length=MAX_PARTS)]


def supplied(
    tenant: Tenant, brief_id: str | None, asked: Sequence[PartInput]
) -> tuple[Supplied, ...]:
    """Each part the build names, with the confirmed BREP its brief's project holds. A part the
    project has not confirmed is refused, and so is a placement of a part the brief's fit check
    measures, which stays where it was confirmed."""
    if not asked:
        return ()
    if brief_id is None:
        raise BadContextPart(
            f"parts come from a brief's project, so pass brief_id too. {NOTHING_BUILT}"
        )
    named = [one.part_id for one in asked]
    if len(set(named)) < len(named):
        raise BadContextPart(
            f"parts names a part twice: give each part one entry that lists all its placements. "
            f"{NOTHING_BUILT}"
        )
    projects, project = tenant.roots.projects, briefs.read_brief(tenant.roots, brief_id).project
    held: dict[str, ConfirmedPart] = {
        one.record.id: one for one in confirmed_parts(projects, project)
    }
    measured = {one.record.id for one in fit_parts(tenant, brief_id)}
    for one in asked:
        if one.part_id not in held:
            raise BadContextPart(
                f"{one.part_id} is not a confirmed part of project {project}; list_files lists "
                f"the parts it holds. {NOTHING_BUILT}"
            )
        if one.placements and one.part_id in measured:
            raise BadContextPart(
                f"{one.part_id} is a part brief {brief_id} must fit, and the fit check measures "
                f"it where it was confirmed, so a build may read it but not place it. "
                f"{NOTHING_BUILT}"
            )
    return tuple(
        Supplied(
            PartUse(
                part_id=one.part_id,
                project=project,
                brep_sha256=held[one.part_id].record.brep_sha256,
                placements=one.placements,
            ),
            part_brep(projects, held[one.part_id]),
        )
        for one in asked
    )


def uses(parts: Sequence[Supplied]) -> tuple[PartUse, ...]:
    return tuple(one.use for one in parts)


def listed(uses: Sequence[PartUse]) -> tuple[PartInput, ...]:
    """The parts a variant read, as build_variant takes them."""
    return tuple(PartInput(part_id=use.part_id, placements=use.placements) for use in uses)
