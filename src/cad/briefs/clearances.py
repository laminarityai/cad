from collections.abc import Collection, Sequence

from cad.briefs.model import MaxClearance, MinClearance
from cad.briefs.store import BadProposal, Draft


def check_proposed(drafts: Sequence[Draft], stored_parts: Collection[str]) -> None:
    for index, draft in enumerate(drafts):
        target = draft.target
        if isinstance(target, MinClearance | MaxClearance) and target.part not in stored_parts:
            raise BadProposal(
                f"requirements[{index}]: {target.part} is not a context part of this brief's "
                "project; propose the part with propose_context_part first and copy its part_id"
            )
