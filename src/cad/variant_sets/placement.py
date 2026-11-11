from dataclasses import dataclass

from cad.scorecard.material import MaterialPinned
from cad.tables.materials import MaterialsTable
from cad.variant_sets.model import (
    MAX_MEMBERS,
    MaterialChoice,
    MaterialMissing,
    Member,
    SetFull,
    SlotRefused,
)

CHOOSE = (
    "No confirmed requirement names the material, so choose one: pick a row from list_materials, "
    "or name a material the table lacks and research it, and pass material_key and a one-line "
    "material_reason. Never ask the person to choose."
)


@dataclass(frozen=True, slots=True)
class Placement:
    slot: int
    revision: int
    unchanged: bool


def choose(
    pinned: str | None,
    previous: MaterialChoice | None,
    key: str | None,
    reason: str | None,
    table: MaterialsTable,
) -> MaterialChoice | None:
    """The material the new revision records. None when the person's made_of fixes it."""
    if pinned is not None:
        if key is not None and table.row_key(key) != pinned:
            raise MaterialPinned(
                f"material_key {key!r} differs from the material the user confirmed, {pinned!r}. "
                "Build again without material_key. Nothing was built."
            )
        return None
    if key is None and reason is None:
        if previous is None:
            raise MaterialMissing(CHOOSE)
        return previous
    if key is None or reason is None:
        raise MaterialMissing(f"material_key and material_reason go together. {CHOOSE}")
    return MaterialChoice(key=table.row_key(key), reason=reason)


def shown(held: tuple[Member, ...], sha256: str, slot: int | None) -> Member | None:
    """The member `slot` names, or with no slot the member already showing this code."""
    if slot is None:
        return next((m for m in held if m.latest.code_sha256 == sha256), None)
    return next((m for m in held if m.slot == slot), None)


def place(
    held: tuple[Member, ...], sha256: str, material: MaterialChoice | None, slot: int | None
) -> Placement:
    """Where code goes in a set. Raises SetFull when new code has no slot to take."""
    if slot is None:
        return _unslotted(held, sha256, material)
    if not 1 <= slot <= MAX_MEMBERS:
        raise SlotRefused(f"slot {slot} is not a slot: a set has slots 1 to {MAX_MEMBERS}")
    twin = next((m for m in held if m.slot != slot and m.latest.code_sha256 == sha256), None)
    if twin is not None:
        raise SlotRefused(
            f"this code is already what slot {twin.slot} shows, so it cannot also be slot {slot}. "
            "Change the code, or build it with that slot."
        )
    current = next((m for m in held if m.slot == slot), None)
    if current is None:
        return Placement(slot, 1, unchanged=False)
    return _revising(current, sha256, material)


def _revising(current: Member, sha256: str, material: MaterialChoice | None) -> Placement:
    unchanged = _same(current, sha256, material)
    count = len(current.revisions)
    return Placement(current.slot, count if unchanged else count + 1, unchanged)


def _same(member: Member, sha256: str, material: MaterialChoice | None) -> bool:
    latest = member.latest
    chosen = None if latest.material is None else latest.material.key
    return latest.code_sha256 == sha256 and chosen == (None if material is None else material.key)


def _unslotted(held: tuple[Member, ...], sha256: str, material: MaterialChoice | None) -> Placement:
    holder = shown(held, sha256, None)
    if holder is not None:
        return _revising(holder, sha256, material)
    taken = {m.slot for m in held}
    free = next((n for n in range(1, MAX_MEMBERS + 1) if n not in taken), None)
    if free is None:
        raise SetFull
    return Placement(free, 1, unchanged=False)
