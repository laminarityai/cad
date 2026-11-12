from collections.abc import Collection, Sequence

from cad.briefs.model import ON_PART, Target
from cad.briefs.store import BadProposal


def check_proposed(
    targets: Sequence[Target], stored_parts: Collection[str], label: str = "requirements"
) -> None:
    for index, target in enumerate(targets):
        if isinstance(target, ON_PART) and target.part not in stored_parts:
            raise BadProposal(
                f"{label}[{index}]: {target.part} is not a context part of this brief's "
                "project; copy a part_id from list_files, or propose a variant with "
                "propose_context_part first"
            )
