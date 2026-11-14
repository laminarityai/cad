from collections.abc import Sequence
from dataclasses import replace

from cad.briefs.model import MAX_MATERIAL_KEY_CHARS, MadeOf
from cad.briefs.store import BadProposal, Draft
from cad.tables.materials import PROJECT_PREFIX, MaterialsTable


def with_row_keys(drafts: Sequence[Draft], table: MaterialsTable) -> list[Draft]:
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
    return replace(draft, target=MadeOf(material=key, body=draft.target.body))
