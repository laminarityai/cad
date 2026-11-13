from __future__ import annotations

from typing import TYPE_CHECKING

from cad.briefs.model import ONE_PER_BRIEF, Brief, Requirement, requirement_id
from cad.briefs.origins import BriefSpan

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cad.briefs import said
    from cad.briefs.kind import Kind
    from cad.briefs.store import BriefState, Draft


def next_set(
    state: BriefState,
    brief: Brief,
    drafts: Sequence[Draft],
    words: said.Words,
    remove: Sequence[str],
) -> tuple[Requirement, ...] | str:
    base = state.carried
    ids = {r.id for r in base}
    outside = next((one for one in remove if one not in ids), None)
    if outside is not None:
        return (
            f"remove: {outside} is not in the set being carried into the next proposal of brief "
            f"{brief.id}, which is the waiting proposal, or the confirmed set when none waits; "
            "list_requirements shows each requirement's id and status"
        )
    kept = tuple(r for r in base if r.id not in remove)
    new = _resolve(brief, drafts, words)
    if isinstance(new, str):
        return new
    held = [r.target for r in kept]
    added = tuple(r for r in new if r.target not in held)
    second = _second_of_a_kind(kept, added)
    if second is not None:
        return second
    if not kept and not added:
        return f"brief {brief.id} would hold no requirement: keep one or propose one"
    return (*kept, *added)


def _second_of_a_kind(kept: Sequence[Requirement], added: Sequence[Requirement]) -> str | None:
    first: dict[Kind, Requirement] = {}
    for one in (*kept, *added):
        kind = one.target.kind
        if kind not in ONE_PER_BRIEF:
            continue
        earlier = first.setdefault(kind, one)
        if earlier is one:
            continue
        if earlier in kept:
            return (
                f"the set being carried holds a {kind}, requirement {earlier.id}, and a brief "
                f"holds one {kind}: to change it, pass its id in remove"
            )
        return f"a set holds at most one {kind}: keep the one the brief states"
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
