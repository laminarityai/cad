from typing import Any

import pytest
from pydantic import TypeAdapter

from cad.briefs.edits import apply_edits, placeholder
from cad.briefs.model import (
    BriefId,
    BriefSpan,
    Requirement,
    Target,
    describe,
    requirement_id,
)
from cad.confirmations.answers import Edit

TARGETS = TypeAdapter[Target](Target)
BRIEF = BriefId("0123456789abcdef")
LIGHT = {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}
HEAVY = {"kind": "min_mass", "mass": {"magnitude": 20, "unit": "g"}}
BOX = {"kind": "envelope", "edges": [{"magnitude": e, "unit": "mm"} for e in (120, 80, 40)]}
SOLID = {"kind": "closed_solid"}


def requirement(target: dict[str, Any], start: int = 0) -> Requirement:
    parsed = TARGETS.validate_python(target)
    origin = BriefSpan(start=start, end=start + 5)
    return Requirement(
        id=requirement_id(BRIEF, parsed, origin), brief_id=BRIEF, target=parsed, origin=origin
    )


def changed(target: dict[str, Any], text: str) -> str:
    """The plain words of the requirement after the edit, or the refusal."""
    one = requirement(target)
    applied = apply_edits([one], [Edit(row=one.id, text=text)])
    return applied if isinstance(applied, str) else describe(applied[0])


@pytest.mark.parametrize(
    ("target", "text", "words"),
    [
        (LIGHT, "120 g", "Mass at most 120 g"),
        (LIGHT, " 0.2kg ", "Mass at most 0.2 kg"),
        (HEAVY, "25 g", "Mass at least 25 g"),
        (BOX, "200 x 100 x 50 mm", "Fits inside a box of 200 mm x 100 mm x 50 mm"),
        (BOX, "50 \u00d7 200 \u00d7 100 mm", "Fits inside a box of 200 mm x 100 mm x 50 mm"),
        (BOX, "20 cm x 100 mm x 5cm", "Fits inside a box of 20 cm x 100 mm x 5 cm"),
    ],
)
def test_a_typed_number_becomes_the_requirement(
    target: dict[str, Any], text: str, words: str
) -> None:
    assert changed(target, text) == words


@pytest.mark.parametrize(
    ("target", "text", "refusal"),
    [
        (LIGHT, "120", "say the unit too"),
        (LIGHT, "under 100 g", "write an amount with its unit"),
        (LIGHT, "120 mm", "expected a [mass] quantity"),
        (LIGHT, "0 g", "above zero"),
        (LIGHT, "120 blorps", "not a unit this page knows"),
        (BOX, "200 x 100 mm", "write three lengths"),
        (BOX, "200 x 100 x 50", "say the unit too"),
        (SOLID, "yes", "this row has no number to change"),
    ],
)
def test_a_number_that_cannot_be_read_is_refused_naming_the_row(
    target: dict[str, Any], text: str, refusal: str
) -> None:
    message = changed(target, text)
    assert message.startswith(describe(requirement(target)) + ": ")
    assert refusal in message


def test_an_edit_keeps_the_kind_and_span_and_gets_the_id_of_what_it_now_says() -> None:
    light, box = requirement(LIGHT), requirement(BOX, start=10)
    applied = apply_edits([light, box], [Edit(row=light.id, text="120 g")])
    assert not isinstance(applied, str)
    lighter, same = applied
    assert same == box
    assert (lighter.target.kind, lighter.origin) == (light.target.kind, light.origin)
    assert (
        lighter.id == requirement({"kind": "max_mass", "mass": {"magnitude": 120, "unit": "g"}}).id
    )
    assert lighter.id != light.id


def test_an_edit_to_the_number_already_shown_changes_nothing() -> None:
    light = requirement(LIGHT)
    assert apply_edits([light], [Edit(row=light.id, text="150 g")]) == (light,)


def test_an_edit_naming_no_row_of_the_proposal_is_refused() -> None:
    light = requirement(LIGHT)
    assert "page changed" in str(apply_edits([light], [Edit(row="f" * 16, text="120 g")]))


def test_an_edit_that_makes_two_rows_the_same_is_refused() -> None:
    first, second = (
        requirement(LIGHT),
        requirement({"kind": "max_mass", "mass": {"magnitude": 120, "unit": "g"}}),
    )
    assert "same thing" in str(apply_edits([first, second], [Edit(row=first.id, text="120 g")]))


def test_only_rows_with_a_number_offer_a_field() -> None:
    friendly = {"kind": "unchecked", "statement": "looks friendly"}
    assert [placeholder(requirement(t)) for t in (LIGHT, BOX, SOLID, friendly)] == [
        "150 g",
        "120 mm x 80 mm x 40 mm",
        None,
        None,
    ]
