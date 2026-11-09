from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from cad.scorecard import score

if TYPE_CHECKING:
    from conftest import Person, Session

pytestmark = pytest.mark.anyio

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
TEXT = "A plate printed in Prusament PLA under 150 g"
SHADOW = "project-prusament-pla"
IN_TABLE = "prusament-pla is in the materials table; use prusament-pla"
UNDER_150: dict[str, Any] = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}


def made_of(material: str, quote: str = "Prusament PLA") -> dict[str, Any]:
    return {"target": {"kind": "made_of", "material": material}, "quote": quote}


async def test_a_project_key_for_a_table_row_is_refused_and_stores_nothing(s: Session) -> None:
    created = await s.call("create_brief", text=TEXT)
    text = await s.text(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[made_of(SHADOW), UNDER_150],
    )
    assert IN_TABLE in text
    listed = await s.call("list_requirements", brief_id=created["brief_id"])
    assert listed["proposals"] == []


async def test_scoring_with_a_project_key_for_a_table_row_is_refused(s: Session) -> None:
    variant_id = (await s.call("build_variant", code=PLATE))["variant_id"]
    text = await s.text("score_variant", variant_id=variant_id, material_key=SHADOW)
    assert IN_TABLE in text
    card = s.roots.briefs.parent / "variants" / variant_id / score.SCORECARD
    assert not card.exists()


async def test_research_for_a_project_key_for_a_table_row_is_refused(s: Session) -> None:
    created = await s.call("create_brief", text=TEXT)
    answer = await s.call(
        "submit_research",
        brief_id=created["brief_id"],
        key=SHADOW,
        field="density",
        url="https://example.org/petg",
        quote="Density 1.28 g/cm3",
    )
    assert answer["result"]["kind"] == "refused"
    assert IN_TABLE in answer["result"]["reason"]


@pytest.mark.parametrize("key", ["Prusament PLA", "prusament pla"])
async def test_research_for_a_key_that_is_not_lowercase_words_is_refused(
    s: Session, key: str
) -> None:
    created = await s.call("create_brief", text=TEXT)
    text = await s.text(
        "submit_research",
        brief_id=created["brief_id"],
        key=key,
        field="density",
        url="https://example.org/pla",
        quote="Density 1.24 g/cm3",
    )
    assert "pattern" in text
    assert "accepted" not in text


async def propose_esun(s: Session) -> dict[str, Any]:
    created = await s.call("create_brief", text="A plate in eSUN PLA Silk under 150 g")
    await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[made_of("esun-pla-silk", "eSUN PLA Silk"), UNDER_150],
    )
    return created


async def test_the_page_names_a_project_material_plainly(s: Session) -> None:
    created = await propose_esun(s)
    await s.call("ask_to_confirm", project_id=created["project_id"])
    _, page = s.get(s.person.url)
    assert "Made of esun-pla-silk" in page
    assert "project-" not in page


async def test_the_card_names_a_project_material_plainly(s: Session, person: Person) -> None:
    person.answer = "confirm"
    created = await propose_esun(s)
    await s.call("ask_to_confirm", project_id=created["project_id"])
    card = await s.call(
        "score_variant",
        variant_id=(await s.call("build_variant", code=PLATE))["variant_id"],
        material_key="esun-pla-silk",
        brief_id=created["brief_id"],
    )
    assert card["material"]["key"] == "project-esun-pla-silk"
    assert card["material"]["set_by"]["statement"] == "Made of esun-pla-silk"
