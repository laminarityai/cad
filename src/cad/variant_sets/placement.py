from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from cad.sandbox.bodies import Bodies
from cad.scorecard.material import MaterialPinned, Pins, pin_for
from cad.tables.materials import MaterialsTable
from cad.variant_sets.model import (
    MAX_MEMBERS,
    BodiesMissing,
    BodyChoice,
    BodyMaterialsRefused,
    Chosen,
    MaterialChoice,
    MaterialMissing,
    Member,
    Option,
    Revision,
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


EACH_BODY = (
    "pass materials with an entry for each body the code built, its body name, a key and a "
    "one-line reason"
)


def choose_each(
    pinned: Pins,
    previous: Revision | None,
    bodies: Bodies | None,
    single: tuple[str | None, str | None],
    asked: Sequence[BodyChoice],
    table: MaterialsTable,
) -> Chosen:
    """What a revision records, given the bodies the code built, None before the build. A body
    with no entry in `asked` keeps the choice the slot's previous revision made for a body of that
    name. `single` is the material_key and material_reason, for a variant of one body. A body the
    person's made_of names records nothing, as the made_of sets it."""
    key, reason = single
    refuse_unpinned(pinned, [(one.body, one.key) for one in asked], table, "Build")
    every = pinned.get(None)
    if every is not None:
        return Chosen(material=choose(every, None, key, reason, table))
    asked = [one for one in asked if one.body not in pinned]
    if asked and (key is not None or reason is not None):
        raise BodyMaterialsRefused(
            "pass material_key and material_reason, or materials, not both. Nothing was built."
        )
    before = None if previous is None else previous.material
    kept = () if previous is None else previous.materials
    if bodies is None:
        if asked or (kept and key is None and reason is None):
            return Chosen(materials=tuple(asked) or kept)
        if pinned and key is None and reason is None:
            return Chosen()
        return Chosen(material=choose(None, before, key, reason, table))
    if not bodies:
        if asked:
            raise BodyMaterialsRefused(
                "the code built one unnamed body, so pass material_key and material_reason, not "
                "materials"
            )
        return Chosen(material=choose(None, before, key, reason, table))
    names = [body.name for body in bodies if body.name not in pinned]
    return Chosen(materials=_each(names, before, kept, single, asked, table))


def _each(
    names: Sequence[str],
    before: MaterialChoice | None,
    kept: Sequence[BodyChoice],
    single: tuple[str | None, str | None],
    asked: Sequence[BodyChoice],
    table: MaterialsTable,
) -> tuple[BodyChoice, ...]:
    """The choice of each named body no made_of names."""
    if not names:
        return ()
    if single != (None, None):
        if len(names) > 1:
            raise BodyMaterialsRefused(
                f"the code built the bodies {', '.join(names)}, and material_key names the "
                f"material of a variant of one body: {EACH_BODY}"
            )
        one = choose(None, None, *single, table)
        assert one is not None
        return (BodyChoice(body=names[0], key=one.key, reason=one.reason),)
    stray = [one.body for one in asked if one.body not in names]
    if stray:
        raise BodyMaterialsRefused(
            f"materials names {', '.join(stray)}, but the code built the bodies "
            f"{', '.join(names)}: name each body as its label does"
        )
    held = {one.body: one for one in kept}
    if before is not None and len(names) == 1:
        held = {names[0]: BodyChoice(body=names[0], key=before.key, reason=before.reason)}
    held |= {one.body: one for one in asked}
    missing = [name for name in names if name not in held]
    if missing:
        raise MaterialMissing(
            f"no material is chosen for the bodies {', '.join(missing)}, and no confirmed "
            f"requirement names one: {EACH_BODY}. Never ask the person to choose"
        )
    return tuple(held[name] for name in names)


def refuse_lacking(named: Sequence[str], bodies: Bodies | None) -> None:
    """Refuses a build that lacks a body a confirmed requirement names. Before the build, None."""
    if bodies is None:
        return
    built = {body.name for body in bodies}
    wanted = list(dict.fromkeys(named))
    lacking = [name for name in wanted if name not in built]
    if lacking:
        raise BodiesMissing(
            f"the person confirmed requirements on the bodies {', '.join(wanted)}, and this build "
            f"has no body named {', '.join(lacking)}. Label a body with each of those names and "
            "build again. Nothing joined the variant set"
        )


def refuse_unpinned(
    pinned: Pins,
    asked: Sequence[tuple[str, str]],
    table: MaterialsTable,
    again: Literal["Build", "Start"],
) -> None:
    """Refuses an entry of materials, a body and its key, that differs from the made_of fixing
    that body."""
    for body, key in asked:
        pin = pin_for(pinned, body)
        if pin is None or table.row_key(key) == pin:
            continue
        nothing = "Nothing was built." if again == "Build" else "No run was started."
        what = f"the {body} is" if body in pinned else "the part is"
        every = "" if body in pinned else ", which pins every body"
        raise MaterialPinned(
            f"materials names {key} for {body}, but the user confirmed that {what} made of "
            f"{pin!r}{every}. {again} again without that entry. {nothing}"
        )


def shown(held: tuple[Member, ...], sha256: str, slot: int | None) -> Member | None:
    """The member `slot` names, or with no slot the member already showing this code."""
    if slot is None:
        return next((m for m in held if m.latest.code_sha256 == sha256), None)
    return next((m for m in held if m.slot == slot), None)


@dataclass(frozen=True, slots=True)
class Design:
    chosen: Chosen
    option: Option | None


def place(held: tuple[Member, ...], sha256: str, design: Design, slot: int | None) -> Placement:
    """Where code goes in a set. Raises SetFull when new code has no slot to take."""
    if slot is None:
        return _unslotted(held, sha256, design)
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
    return _revising(current, sha256, design)


def _revising(current: Member, sha256: str, design: Design) -> Placement:
    unchanged = _same(current, sha256, design)
    count = len(current.revisions)
    return Placement(current.slot, count if unchanged else count + 1, unchanged)


def _same(member: Member, sha256: str, design: Design) -> bool:
    latest = member.latest
    asked = design.chosen
    return (
        latest.code_sha256 == sha256
        and _keys(latest.material, latest.materials) == _keys(asked.material, asked.materials)
        and latest.option == design.option
    )


def _keys(
    material: MaterialChoice | None, materials: Sequence[BodyChoice]
) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    return (
        None if material is None else material.key,
        tuple((one.body, one.key) for one in materials),
    )


def _unslotted(held: tuple[Member, ...], sha256: str, design: Design) -> Placement:
    holder = shown(held, sha256, None)
    if holder is not None:
        return _revising(holder, sha256, design)
    taken = {m.slot for m in held}
    free = next((n for n in range(1, MAX_MEMBERS + 1) if n not in taken), None)
    if free is None:
        raise SetFull
    return Placement(free, 1, unchanged=False)
