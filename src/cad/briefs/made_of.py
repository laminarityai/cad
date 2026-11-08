from collections.abc import Collection, Sequence

from cad.briefs.model import MadeOf
from cad.briefs.store import BadProposal, Draft


def check_proposed(drafts: Sequence[Draft], known_keys: Collection[str]) -> None:
    named = [(i, d.target.material) for i, d in enumerate(drafts) if isinstance(d.target, MadeOf)]
    for index, key in named:
        if key not in known_keys:
            raise BadProposal(
                f"requirements[{index}]: {key!r} is not a material key; "
                "copy one exactly from list_materials, or leave made_of out"
            )
    if len(named) > 1:
        raise BadProposal(
            "a set holds at most one made_of: a part is made of one material; "
            "keep the one the brief names"
        )
