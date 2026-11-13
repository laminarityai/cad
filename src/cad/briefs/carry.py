from __future__ import annotations

from typing import TYPE_CHECKING

from cad.briefs.keys import LOAD_CASE, TargetKey, target_key
from cad.briefs.model import Brief, Requirement, RequirementId, requirement_id
from cad.briefs.origins import BriefSpan

KEEP_THE_STRICTER = (
    "keep the stricter limit and file the other as an unchecked requirement quoting its words. "
    "The stress check is linear, so its stress and its deflection scale with the force, and the "
    "stricter limit holds the other: for min_safety_factor the larger factor times force, for "
    "max_deflection the smaller deflection over force"
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cad.briefs import said
    from cad.briefs.store import BriefState, Draft


def next_set(
    state: BriefState,
    brief: Brief,
    drafts: Sequence[Draft],
    words: said.Words,
    remove: Sequence[str],
) -> tuple[Requirement, ...] | str:
    ids = {r.id for r in state.carried}
    outside = next((one for one in remove if one not in ids), None)
    if outside is not None:
        return (
            f"remove: {outside} is not in the set being carried into the next proposal of brief "
            f"{brief.id}, which is the waiting proposal, or the confirmed set when none waits; "
            "list_requirements shows each requirement's id and status"
        )
    kept = kept_after(state, remove)
    new = _resolve(brief, drafts, words)
    if isinstance(new, str):
        return new
    held = [r.target for r in kept]
    added = tuple(r for r in new if r.target not in held)
    second = _second_of_a_key(kept, added)
    if second is not None:
        return second
    if not kept and not added:
        return f"brief {brief.id} would hold no requirement: keep one or propose one"
    return (*kept, *added)


def kept_after(state: BriefState, remove: Sequence[str]) -> tuple[Requirement, ...]:
    """The rows of the set being carried that stay in the next proposal."""
    return tuple(r for r in state.carried if r.id not in remove)


def edited(state: BriefState, through: int) -> dict[RequirementId, Requirement]:
    """Each row a person changed on the page in proposals up to number `through`, by the id the
    change gave it, with the row as the agent proposed it. A carried row keeps that id, so it keeps
    the label, and a later edit that lands on the same id leaves an earlier proposal's row alone."""
    return {
        after.id: before
        for one in state.proposals
        if one.proposal.number <= through
        for before, after in zip(one.proposal.requirements, one.requirements, strict=True)
        if before.id != after.id
    }


def _second_of_a_key(kept: Sequence[Requirement], added: Sequence[Requirement]) -> str | None:
    """A set stored before a key held one row may carry two. Only an added row is refused."""
    first: dict[TargetKey, Requirement] = {}
    for one in kept:
        key = target_key(one.target)
        if key is not None:
            first.setdefault(key, one)
    for one in added:
        key = target_key(one.target)
        if key is None:
            continue
        earlier = first.setdefault(key, one)
        if earlier is one:
            continue
        if earlier in kept:
            return (
                f"the set being carried holds a {key.kind}, requirement {earlier.id}, and "
                f"{key.rule}: to change it, pass its id in remove"
            )
        if key.per == LOAD_CASE:
            return f"{key.rule}, and this call holds two: {KEEP_THE_STRICTER}"
        return f"{key.rule}: keep the one the brief states"
    return None


def _resolve(
    brief: Brief, drafts: Sequence[Draft], words: said.Words
) -> tuple[Requirement, ...] | str:
    requirements: list[Requirement] = []
    for index, draft in enumerate(drafts):
        start = brief.text.find(draft.quote) if draft.quote else -1
        if (draft.cited is None or draft.typed) and start < 0:
            return (
                f"requirements[{index}]: the quote does not appear in brief {brief.id}; "
                + words.refusal_hint
            )
        origin = draft.cited or BriefSpan(start=start, end=start + len(draft.quote))
        rid = requirement_id(brief.id, draft.target, origin)
        if any(r.id == rid for r in requirements):
            return f"requirements[{index}] repeats an earlier requirement"
        requirements.append(
            Requirement(id=rid, brief_id=brief.id, target=draft.target, origin=origin)
        )
    return tuple(requirements)
