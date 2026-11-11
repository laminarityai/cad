from collections.abc import Collection, Sequence

from cad.briefs.model import MaxClearance, MinClearance, Target
from cad.briefs.store import BadProposal


def check_proposed(
    targets: Sequence[Target], stored_parts: Collection[str], label: str = "requirements"
) -> None:
    for index, target in enumerate(targets):
        if isinstance(target, MinClearance | MaxClearance) and target.part not in stored_parts:
            raise BadProposal(
                f"{label}[{index}]: {target.part} is not a context part of this brief's "
                "project; propose the part with propose_context_part first and copy its part_id"
            )
