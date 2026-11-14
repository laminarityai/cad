from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import pytest

from tests.support.named_bodies import GEAR, PLATE
from tests.support.rows import UNDER_150

if TYPE_CHECKING:
    from tests.support.variant_set_session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]

GEARS_ON_A_PLATE: Final = """
from build123d import *
plate = Box(80, 40, 4)
plate.label, plate.color = "plate", Color("black")
teeth = [Pos(x, 0, 6) * Cylinder(8, 6) for x in (-20, 20)]
gears = Compound(children=teeth, label="gear")
gears.color = Color("gray")
result = Compound(children=[plate, gears])
"""
EACH: Final = [
    {"body": "plate", "key": PLATE, "reason": "carbon fibre keeps the plate stiff and light"},
    {"body": "gear", "key": GEAR, "reason": "steel teeth wear well"},
]


async def unpinned(s: Session) -> tuple[str, str]:
    brief_id = await s.proposed_brief(None, "Steel gears on a plate under 150 g", UNDER_150)
    await s.confirm(brief_id)
    return (await s.call("list_requirements", brief_id=brief_id))["project_id"], brief_id


def by_body(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {one["body"]: one["key"] for one in rows}


async def test_each_body_s_material_is_recorded_on_the_slot_and_scored(s: Session) -> None:
    project, brief_id = await unpinned(s)
    built = await s.call("build_variant", code=GEARS_ON_A_PLATE, brief_id=brief_id, materials=EACH)
    [member] = (await s.call("variant_set", project_id=project, brief_id=brief_id))["members"]
    assert by_body(member["body_materials"]) == {"plate": PLATE, "gear": GEAR}
    card = await s.call("score_variant", variant_id=built["variant_id"], brief_id=brief_id)
    assert "material_key" not in card
    assert by_body(card["body_materials"]) == {"plate": PLATE, "gear": GEAR}
    assert [one["name"] for one in card["bodies"]] == ["plate", "gear"]
    assert card["untested"] == ["How the bodies are joined is not checked."]


async def test_names_that_differ_from_the_code_s_bodies_store_the_variant_and_join_nothing(
    s: Session,
) -> None:
    project, brief_id = await unpinned(s)
    wrong = [{**EACH[0], "body": "base"}, EACH[1]]
    text = await s.refusal(
        "build_variant", code=GEARS_ON_A_PLATE, brief_id=brief_id, materials=wrong
    )
    assert "materials names base, but the code built the bodies plate, gear" in text
    assert "is stored" in text
    assert (await s.call("variant_set", project_id=project, brief_id=brief_id))["members"] == []


async def test_one_material_key_for_two_bodies_is_refused(s: Session) -> None:
    _, brief_id = await unpinned(s)
    text = await s.refusal(
        "build_variant",
        code=GEARS_ON_A_PLATE,
        brief_id=brief_id,
        material_key=PLATE,
        material_reason="it is light",
    )
    assert "the code built the bodies plate, gear, and material_key names" in text
