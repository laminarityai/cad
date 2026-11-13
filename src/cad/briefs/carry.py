"""The requirements a new proposal holds: the confirmed set, less the ones the agent names in
remove, then each draft, found in the brief. A person's Confirm is the only way one leaves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cad.briefs.model import Brief, MadeOf, Requirement, requirement_id
from cad.briefs.origins import BriefSpan

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
    """The next proposal's requirements, or why the store refuses them."""
    known = {r.id for p in state.proposals for r in (*p.proposal.requirements, *p.requirements)}
    unknown = next((one for one in remove if one not in known), None)
    if unknown is not None:
        return (
            f"remove: {unknown} is not a requirement of brief {brief.id}; "
            "list_requirements shows each requirement's id"
        )
    confirmed = state.confirmed
    kept = tuple(r for r in confirmed.requirements if r.id not in remove) if confirmed else ()
    new = _resolve(brief, drafts, words)
    if isinstance(new, str):
        return new
    held = [r.target for r in kept]
    added = tuple(r for r in new if r.target not in held)
    material = next((r for r in kept if isinstance(r.target, MadeOf)), None)
    if material is not None and any(isinstance(r.target, MadeOf) for r in added):
        return (
            f"the confirmed set holds a made_of, requirement {material.id}, and a part is made "
            "of one material: to change it, pass its id in remove"
        )
    if not kept and not added:
        return f"brief {brief.id} would hold no requirement: keep one or propose one"
    return (*kept, *added)


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
