from dataclasses import dataclass

from cad.variant_sets.model import MAX_MEMBERS, Member, SetFull, SlotRefused


@dataclass(frozen=True, slots=True)
class Placement:
    slot: int
    revision: int
    unchanged: bool


def place(held: tuple[Member, ...], sha256: str, slot: int | None) -> Placement:
    """Where code goes in a set. Raises SetFull when new code has no slot to take."""
    if slot is None:
        return _unslotted(held, sha256)
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
    if current.latest.code_sha256 == sha256:
        return Placement(slot, len(current.revisions), unchanged=True)
    return Placement(slot, len(current.revisions) + 1, unchanged=False)


def _unslotted(held: tuple[Member, ...], sha256: str) -> Placement:
    shown = next((m for m in held if m.latest.code_sha256 == sha256), None)
    if shown is not None:
        return Placement(shown.slot, len(shown.revisions), unchanged=True)
    taken = {m.slot for m in held}
    free = next((n for n in range(1, MAX_MEMBERS + 1) if n not in taken), None)
    if free is None:
        raise SetFull
    return Placement(free, 1, unchanged=False)
