from collections.abc import Sequence

from cad.briefs.model import MAX_MATERIAL_KEY_CHARS, MadeOf
from cad.briefs.store import BadProposal, Draft
from cad.tables.materials import PROJECT_PREFIX, MaterialsTable


def resolve(drafts: Sequence[Draft], table: MaterialsTable) -> list[Draft]:
    """The drafts with each made_of key naming its row: a material the table lacks becomes the
    project's own `project-` row, whose values are researched."""
    if sum(isinstance(d.target, MadeOf) for d in drafts) > 1:
        raise BadProposal(
            "a set holds at most one made_of: a part is made of one material; "
            "keep the one the brief names"
        )
    return [_resolved(index, d, table) for index, d in enumerate(drafts)]


def _resolved(index: int, draft: Draft, table: MaterialsTable) -> Draft:
    if not isinstance(draft.target, MadeOf):
        return draft
    key = table.row_key(draft.target.material)
    if len(key) > MAX_MATERIAL_KEY_CHARS:
        room = MAX_MATERIAL_KEY_CHARS - len(PROJECT_PREFIX)
        raise BadProposal(
            f"requirements[{index}]: {draft.target.material!r} has no row in the materials "
            f"table, so its key gains the {PROJECT_PREFIX!r} prefix; name it in at most {room} "
            "characters"
        )
    return Draft(target=MadeOf(material=key), quote=draft.quote)
