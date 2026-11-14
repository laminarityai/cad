"""A requirement may name one body of the variant, and one that names none reads as on trunk."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pydantic import TypeAdapter

from cad.briefs.edits import apply_edits
from cad.briefs.model import BriefId, Requirement, Target, requirement_id
from cad.briefs.origins import BriefSpan
from cad.briefs.words import describe
from cad.confirmations.answers import Edit

if TYPE_CHECKING:
    from tests.support.session import Session

TARGETS = TypeAdapter[Target](Target)
BRIEF = BriefId("0123456789abcdef")
ORIGIN = BriefSpan(start=0, end=4)
GRAMS = {"magnitude": 20, "unit": "g"}
TRUNK_IDS = [
    ({"kind": "max_mass", "mass": GRAMS}, "9e1978b83ece39cd"),
    ({"kind": "min_mass", "mass": GRAMS}, "c6818f94aff5ad04"),
    ({"kind": "made_of", "material": "prusament-pla"}, "55282823ce5a44e8"),
    (
        {
            "kind": "measure_limit",
            "check_id": "min_wall",
            "measure": "min_wall",
            "comparator": "at_least",
            "limit": {"magnitude": 1, "unit": "mm"},
        },
        "0b2524c455884ced",
    ),
    ({"kind": "plain_holes", "diameter": {"magnitude": 5, "unit": "mm"}}, "75fef43bf11e7375"),
    ({"kind": "fastener_holes", "size": "M5", "fit": "clearance", "count": 2}, "966ea86495c81ba6"),
]


def requirement(target: dict[str, Any]) -> Requirement:
    parsed = TARGETS.validate_python(target)
    rid = requirement_id(BRIEF, parsed, ORIGIN)
    return Requirement(id=rid, brief_id=BRIEF, target=parsed, origin=ORIGIN)


@pytest.mark.parametrize(("target", "trunk"), TRUNK_IDS)
def test_a_target_that_names_no_body_keeps_the_id_and_bytes_it_had_on_trunk(
    target: dict[str, Any], trunk: str
) -> None:
    one = requirement(target)
    assert one.id == trunk
    assert "body" not in one.model_dump_json()


@pytest.mark.parametrize(("target", "trunk"), TRUNK_IDS)
def test_the_body_is_part_of_what_the_person_confirms(target: dict[str, Any], trunk: str) -> None:
    plate, gear = (requirement({**target, "body": name}) for name in ("plate", "gear"))
    assert len({trunk, plate.id, gear.id}) == 3
    assert describe(plate).startswith("plate: ")


def test_a_person_s_edit_of_the_number_keeps_the_body() -> None:
    plate = requirement({"kind": "max_mass", "mass": GRAMS, "body": "plate"})
    applied = apply_edits([plate], [Edit(row=plate.id, text="25 g")])
    assert not isinstance(applied, str)
    assert describe(applied[0]) == "plate: mass at most 25 g"


def test_an_envelope_cannot_name_a_body() -> None:
    edges = [{"magnitude": edge, "unit": "mm"} for edge in (40, 30, 20)]
    with pytest.raises(ValueError, match="body"):
        TARGETS.validate_python({"kind": "envelope", "edges": edges, "body": "plate"})


@pytest.mark.anyio
async def test_a_brief_holds_one_max_mass_per_body(s: Session) -> None:
    text = "the plate weighs at most 20 g and the whole part at most 50 g"
    brief_id = (await s.call("create_brief", text=text))["brief_id"]
    rows: list[dict[str, Any]] = [
        {"target": {"kind": "max_mass", "mass": GRAMS, "body": "plate"}, "quote": "at most 20 g"},
        {"target": {"kind": "max_mass", "mass": {"magnitude": 50, "unit": "g"}}, "quote": "50 g"},
    ]
    proposed = await s.call("propose_requirements", brief_id=brief_id, requirements=rows)
    assert [one["plain"] for one in proposed["requirements"]] == [
        "plate: mass at most 20 g",
        "Mass at most 50 g",
    ]
    again = {**rows[0], "target": {**rows[0]["target"], "mass": {"magnitude": 30, "unit": "g"}}}
    said = await s.text("propose_requirements", brief_id=brief_id, requirements=[again])
    assert "one max_mass per body" in said


@pytest.mark.anyio
async def test_each_made_of_asks_for_the_research_its_own_material_needs(s: Session) -> None:
    text = "an acme-silk plate with acme-matte gears"
    brief_id = (await s.call("create_brief", text=text))["brief_id"]
    rows: list[dict[str, Any]] = [
        {"target": {"kind": "made_of", "material": key, "body": body}, "quote": quote}
        for key, body, quote in (
            ("acme-silk-pla", "plate", "acme-silk plate"),
            ("acme-matte-pla", "gear", "acme-matte gears"),
        )
    ]
    proposed = await s.call("propose_requirements", brief_id=brief_id, requirements=rows)
    assert sorted({one["key"] for one in proposed["research"]}) == [
        "project-acme-matte-pla",
        "project-acme-silk-pla",
    ]
