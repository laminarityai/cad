import subprocess
import sys
from pathlib import Path
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


# Every text the page has accepted. A stored answer keeps the person's text and the store reads
# it again on every read, so a text that stopped reading the same would make an old confirmed
# brief read as tampered. Add to this list; never remove from it or change a line.
ACCEPTED = [
    (LIGHT, "120 g", "Mass at most 120 g"),
    (LIGHT, " 0.2kg ", "Mass at most 0.2 kg"),
    (LIGHT, "100 g", "Mass at most 100 g"),
    (LIGHT, "150 g", "Mass at most 150 g"),
    (HEAVY, "25 g", "Mass at least 25 g"),
    (BOX, "200 x 100 x 50 mm", "Fits inside a box of 200 mm x 100 mm x 50 mm"),
    (BOX, "50 \u00d7 200 \u00d7 100 mm", "Fits inside a box of 200 mm x 100 mm x 50 mm"),
    (BOX, "20 cm x 100 mm x 5cm", "Fits inside a box of 20 cm x 100 mm x 5 cm"),
    (LIGHT, "120 G", "Mass at most 120 g"),
    (LIGHT, "1.5 KG", "Mass at most 1.5 kg"),
    (LIGHT, "2 lb", "Mass at most 2 lb"),
    (LIGHT, "3 lbs", "Mass at most 3 lb"),
    (LIGHT, "8 oz", "Mass at most 8 oz"),
    (LIGHT, "120 grams", "Mass at most 120 g"),
    (LIGHT, "150.001 g", "Mass at most 150.001 g"),
    (LIGHT, ".5 kg", "Mass at most 0.5 kg"),
    (BOX, "120 X 80 X 40 MM", "Fits inside a box of 120 mm x 80 mm x 40 mm"),
    (BOX, "1 x 0.5 x 0.25 m", "Fits inside a box of 1 m x 0.5 m x 0.25 m"),
    (BOX, "6 x 4 x 2 in", "Fits inside a box of 6 in x 4 in x 2 in"),
    (BOX, "6 x 4 x 2 inches", "Fits inside a box of 6 in x 4 in x 2 in"),
]


@pytest.mark.parametrize(("target", "text", "words"), ACCEPTED)
def test_every_text_the_page_accepted_still_reads_the_same(
    target: dict[str, Any], text: str, words: str
) -> None:
    assert changed(target, text) == words


@pytest.mark.parametrize(
    ("target", "text", "refusal"),
    [
        (LIGHT, "120", "Say the unit too, such as 120 g."),
        (LIGHT, "under 100 g", "Write a number and a unit, such as 120 g."),
        (LIGHT, "120 mm", "mm is a length, not a mass. Write a mass, such as 120 g."),
        (LIGHT, "0 g", "Write a number above zero."),
        (LIGHT, "120 blorps", '"blorps" is not a unit this page reads. Use g, kg, lb or oz.'),
        (LIGHT, "120 gr", '"gr" is not a unit this page reads. Use g, kg, lb or oz.'),
        (LIGHT, "120 Gg", '"Gg" is not a unit this page reads.'),
        (LIGHT, "120 planck_mass", "Write a number and a unit, such as 120 g."),
        (LIGHT, "120 kg*percent", "Write a number and a unit, such as 120 g."),
        (LIGHT, "120 count*g", "Write a number and a unit, such as 120 g."),
        (LIGHT, "1e3 g", "Write the number with digits and a decimal point only, such as 1200 g."),
        (LIGHT, "1,200 g", "Write the number with digits and a decimal point only"),
        (LIGHT, "150.0000001 g", "Use at most 6 digits"),
        (BOX, "200 x 100 mm", "Write three lengths and a unit, such as 120 x 80 x 40 mm."),
        (BOX, "200 x 100 x 50", "Say the unit too, such as 120 x 80 x 40 mm."),
        (
            BOX,
            "1 x 1 x 1 lightyear",
            '"lightyear" is not a unit this page reads. Use mm, cm, m or in.',
        ),
        (BOX, "1 x 1 x 1 g", "g is a mass, not a length. Write a length, such as 40 mm."),
        (SOLID, "yes", "This row has no number to change."),
    ],
)
def test_a_number_that_cannot_be_read_is_refused_naming_the_row(
    target: dict[str, Any], text: str, refusal: str
) -> None:
    message = changed(target, text)
    assert message.startswith(describe(requirement(target)) + ": ")
    assert refusal in message
    assert "[" not in message and "gauss" not in message and "molar" not in message


@pytest.mark.parametrize(
    "text",
    ["120 g's", '120 g"', "120 g (", "120 g/0", "120 g**0", "120 g-))", "120 g^2"],
)
def test_unit_arithmetic_is_refused_before_pint_reads_it(text: str) -> None:
    message = changed(LIGHT, text)
    assert message == "Mass at most 150 g: Write a number and a unit, such as 120 g."


def test_a_huge_exponent_is_refused_in_bounded_time() -> None:
    code = "from test_edits import LIGHT, changed;print(changed(LIGHT, '120 g**9**9**9'))"
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert "Write a number and a unit" in done.stdout


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
