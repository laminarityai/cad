"""A person's change to one requirement's number, typed on the confirmation page.

The page stores the typed text in the signed PageAnswer (`cad.confirmations.answers.Edit`). This
module turns that text into the requirement the person confirmed. The page runs it before it
records the answer, and the brief store runs it again on every read, so what checks read is
exactly what the person typed. Only the number changes: the kind and the brief span stay.
"""

import re
from collections.abc import Sequence
from typing import Final, assert_never

import pint
from pydantic import ValidationError

from cad.briefs.model import (
    ClosedSolid,
    Envelope,
    MaxMass,
    MinMass,
    Requirement,
    Unchecked,
    amount,
    describe,
    requirement_id,
)
from cad.confirmations.answers import Edit
from cad.tables.materials import UNITS

AMOUNT: Final = re.compile(r"\s*([0-9]+(?:\.[0-9]+)?|\.[0-9]+)\s*([^\s0-9.].*?)?\s*")
EDGES: Final = re.compile(r"[x\u00d7]", re.IGNORECASE)  # x or the multiplication sign


def placeholder(requirement: Requirement) -> str | None:
    """What the page shows in the row's empty edit field, or None when the row has no number."""
    target = requirement.target
    match target:
        case ClosedSolid() | Unchecked():
            return None
        case MaxMass() | MinMass():
            return amount(target.mass)
        case Envelope():
            return " x ".join(amount(edge) for edge in target.edges)
        case _:
            assert_never(target)


def apply_edits(
    requirements: Sequence[Requirement], edits: Sequence[Edit]
) -> tuple[Requirement, ...] | str:
    """The requirements with each edit applied, or a message for the person refusing them."""
    by_row = {edit.row: edit.text for edit in edits}
    known = {r.id for r in requirements}
    if len(by_row) != len(edits) or not set(by_row) <= known:
        return "This page changed since it opened. Ask the agent to open it again."
    changed: list[Requirement] = []
    for requirement in requirements:
        text = by_row.get(requirement.id)
        one = requirement if text is None else _edited(requirement, text)
        if isinstance(one, str):
            return f"{describe(requirement)}: {one}"
        changed.append(one)
    if len({r.id for r in changed}) != len(changed):
        return "Two rows would say the same thing. Change one of them, or decline."
    return tuple(changed)


def _edited(requirement: Requirement, text: str) -> Requirement | str:
    target = requirement.target
    try:
        match target:
            case ClosedSolid() | Unchecked():
                return "this row has no number to change"
            case MaxMass() | MinMass():
                [mass] = _quantities(text, count=1)
                new = type(target).model_validate({"mass": mass})
            case Envelope():
                edges = _quantities(text, count=3)
                new = Envelope.model_validate({"edges": edges})
            case _:
                assert_never(target)
    except _Unreadable as error:
        return str(error)
    except ValidationError as error:
        return _first_message(error)
    return requirement.model_copy(
        update={
            "target": new,
            "id": requirement_id(requirement.brief_id, new, requirement.origin),
        }
    )


class _Unreadable(Exception):
    pass


def _quantities(text: str, count: int) -> list[pint.Quantity]:
    """`count` amounts separated by "x". A bare number takes the unit written after the last."""
    parts = EDGES.split(text) if count > 1 else [text]
    matches = [AMOUNT.fullmatch(part) for part in parts]
    if len(parts) != count or any(m is None for m in matches):
        shape = "an amount with its unit, such as 120 g" if count == 1 else "three lengths"
        example = "" if count == 1 else ", such as 120 x 80 x 40 mm"
        raise _Unreadable(f"write {shape}{example}")
    found = [(m.group(1), m.group(2)) for m in matches if m is not None]
    last_unit = found[-1][1]
    if last_unit is None:
        raise _Unreadable("say the unit too, such as 120 g or 40 mm")
    try:
        return [UNITS.Quantity(float(number), unit or last_unit) for number, unit in found]
    except (pint.PintError, AttributeError, TypeError, ValueError) as error:
        raise _Unreadable(f"{last_unit!r} is not a unit this page knows") from error


def _first_message(error: ValidationError) -> str:
    message = str(error.errors()[0]["msg"])
    return message.removeprefix("Value error, ")
