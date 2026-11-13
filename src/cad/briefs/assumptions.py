"""What the agent assumed for a brief: values the person did not state.

An assumption is a signed, numbered record beside the proposals. The agent writes and replaces
it freely and the newest set wins. It is never on the confirmation page and no verdict rests on
it: the scorecard lists it apart, with the measure beside the assumed value.
"""

from collections.abc import Callable, Collection, Sequence
from datetime import UTC, datetime
from typing import Annotated, Final

from pydantic import Field, ValidationError

from cad.briefs import clearances, described
from cad.briefs.model import MAX_REQUIREMENTS, MAX_STATEMENT_CHARS, BriefId, Target, limits
from cad.briefs.store import BadProposal, TamperedBrief, read_brief
from cad.frozen import Frozen
from cad.records import files, signed
from cad.records.roots import Roots

ASSUMPTIONS: Final = "assumptions"
MAX_ASSUMPTIONS: Final = MAX_REQUIREMENTS
NOT_A_VALUE: Final = (
    "an assumption is a number a check measures, and this target holds none. Choose a material "
    "with material_key when you build"
)


class Assumption(Frozen):
    target: Target
    why: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]


class AssumptionSet(Frozen):
    """One whole numbered set of the agent's assumptions for a brief. Never edited once stored."""

    brief_id: BriefId
    number: Annotated[int, Field(ge=1)]
    assumptions: tuple[Assumption, ...]
    created_at: datetime


def assume(
    roots: Roots, raw_id: str, items: Sequence[Assumption], stored_parts: Collection[str]
) -> AssumptionSet | None:
    """Store `items` as the brief's newest set, which replaces the one in force. Returns the set
    in force. Writing the set already in force, or an empty set when none is, stores nothing."""
    brief = read_brief(roots, raw_id)
    for index, item in enumerate(items):
        if not limits(item.target):
            raise BadProposal(f"assumptions[{index}]: {NOT_A_VALUE}")
    clearances.check_proposed([one.target for one in items], stored_parts, "assumptions")
    described.refuse_assumed([one.target for one in items])
    directory = roots.briefs / brief.id / ASSUMPTIONS

    def next_set(existing: tuple[bytes, ...]) -> bytes | None:
        held = _parsed(existing, brief.id)
        if tuple(items) == (held[-1].assumptions if held else ()):
            return None
        return (
            AssumptionSet(
                brief_id=brief.id,
                number=len(existing) + 1,
                assumptions=tuple(items),
                created_at=datetime.now(UTC),
            )
            .model_dump_json()
            .encode()
        )

    try:
        directory.mkdir(exist_ok=True)
        signed.append(signed.Store(roots.briefs, "brief"), directory, _slot(brief.id), next_set)
    except signed.Contended as error:
        raise BadProposal(
            f"brief {brief.id} is being given assumptions concurrently; try again"
        ) from error
    except signed.Tampered as error:
        raise TamperedBrief(_report(brief.id)) from error
    return in_force(roots, brief.id)


def in_force(roots: Roots, raw_id: str) -> AssumptionSet | None:
    """The newest set of assumptions, or None when the agent never made one."""
    brief = read_brief(roots, raw_id)
    directory = roots.briefs / brief.id / ASSUMPTIONS
    if not files.is_directory(directory):
        return None
    records = signed.read_numbered(signed.Store(roots.briefs, "brief"), directory, _slot(brief.id))
    if records is None:
        raise TamperedBrief(_report(brief.id))
    held = _parsed(records, brief.id)
    return held[-1] if held else None


def _parsed(records: tuple[bytes, ...], brief_id: BriefId) -> tuple[AssumptionSet, ...]:
    try:
        held = tuple(AssumptionSet.model_validate_json(record) for record in records)
    except ValidationError as error:
        raise TamperedBrief(_report(brief_id)) from error
    if any(one.brief_id != brief_id or one.number != n for n, one in enumerate(held, start=1)):
        raise TamperedBrief(_report(brief_id))
    return held


def _slot(brief_id: BriefId) -> Callable[[int], str]:
    return lambda number: f"{brief_id}/assumption/{number}"


def _report(brief_id: BriefId) -> str:
    return (
        f"brief {brief_id}'s assumptions failed the server's integrity check, so the brief cannot "
        "be used; create a new brief to carry on"
    )
