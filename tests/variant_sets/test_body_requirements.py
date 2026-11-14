from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import pytest

from tests.support.named_bodies import GEAR, PLATE

if TYPE_CHECKING:
    from tests.support.variant_set_session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]

TEXT: Final = (
    "Steel gears on a carbon plate. The plate is at least 20 g, the gear has a 5 mm hole, "
    "and the spacer is at most 100 g."
)
GEARS_ON_A_HOLED_PLATE: Final = """
from build123d import *
plate = Box(80, 40, 4) - Cylinder(2.5, 4)
plate.label = "plate"
teeth = [Pos(x, 0, 6) * Cylinder(8, 6) for x in (-20, 20)]
result = Compound(children=[plate, Compound(children=teeth, label="gear")])
"""
EACH: Final = [
    {"body": "plate", "key": PLATE, "reason": "carbon fibre keeps the plate stiff and light"},
    {"body": "gear", "key": GEAR, "reason": "steel teeth wear well"},
]
GRAMS: Final = "g"


def on(body: str, target: dict[str, Any], quote: str) -> dict[str, Any]:
    return {"target": {**target, "body": body}, "quote": quote}


ROWS: Final = [
    on("plate", {"kind": "min_mass", "mass": {"magnitude": 20, "unit": GRAMS}}, "at least 20 g"),
    on("gear", {"kind": "plain_holes", "diameter": {"magnitude": 5, "unit": "mm"}}, "a 5 mm hole"),
    on("spacer", {"kind": "max_mass", "mass": {"magnitude": 100, "unit": GRAMS}}, "at most 100 g"),
]
WHOLE: Final = [
    {**one, "target": {k: v for k, v in one["target"].items() if k != "body"}} for one in ROWS[:2]
]


async def verdicts(s: Session, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    brief_id = await s.proposed_brief(None, TEXT, *rows)
    await s.confirm(brief_id)
    built = await s.call(
        "build_variant", code=GEARS_ON_A_HOLED_PLATE, brief_id=brief_id, materials=EACH
    )
    card = await s.call("score_variant", variant_id=built["variant_id"], brief_id=brief_id)
    return {one["statement"]: one for one in card["basis"]["requirements"]}


async def test_a_requirement_on_a_body_reads_that_body_and_not_the_whole_variant(
    s: Session,
) -> None:
    whole = await verdicts(s, WHOLE)
    assert {one: row["verdict"] for one, row in whole.items()} == {
        "Mass at least 20 g": "pass",
        "A hole of 5 mm, within ±0.05 mm": "pass",
    }
    each = await verdicts(s, ROWS[:2])
    assert {one: row["verdict"] for one, row in each.items()} == {
        "plate: mass at least 20 g": "fail",
        "gear: a hole of 5 mm, within ±0.05 mm": "fail",
    }
    [mass] = each["plate: mass at least 20 g"]["comparisons"]
    assert mass["measure"] == "mass:plate"


async def test_a_requirement_on_a_body_the_variant_lacks_never_passes(s: Session) -> None:
    rows = await verdicts(s, ROWS[2:])
    spacer = rows["spacer: mass at most 100 g"]
    assert spacer["verdict"] == "unknown"
    assert "no body named spacer" in spacer["reason"]


async def test_a_made_of_on_one_body_pins_that_body_and_leaves_the_other_to_the_agent(
    s: Session,
) -> None:
    pinned = on("plate", {"kind": "made_of", "material": PLATE}, "PA6-CF20")
    brief_id = await s.proposed_brief(None, "A PA6-CF20 plate with steel gears", pinned)
    await s.confirm(brief_id)
    other = [{**EACH[0], "key": GEAR}, EACH[1]]
    refused = await s.refusal(
        "build_variant", code=GEARS_ON_A_HOLED_PLATE, brief_id=brief_id, materials=other
    )
    assert "the user confirmed that the plate is made of" in refused
    built = await s.call(
        "build_variant", code=GEARS_ON_A_HOLED_PLATE, brief_id=brief_id, materials=EACH[1:]
    )
    card = await s.call("score_variant", variant_id=built["variant_id"], brief_id=brief_id)
    assert {one["body"]: (one["key"], one["set_by"]["kind"]) for one in card["body_materials"]} == {
        "plate": (PLATE, "requirement"),
        "gear": (GEAR, "agent_argument"),
    }
