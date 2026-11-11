from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from cad.scorecard.material import AGENT_CHOSE

if TYPE_CHECKING:
    from tests.support.variant_set_session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]

PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
THICKER: Final = PLATE + "\n# a thicker wall\n"
NO_DOCKER: Final = "unix:///nonexistent/docker.sock"
UNDER_150: Final = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
PETG: Final = {
    "target": {"kind": "made_of", "material": "prusament-petg"},
    "quote": "PETG",
}
PLA_CHOICE: Final = {
    "material_key": "prusament-pla",
    "material_reason": "PLA is light and prints without warping",
}
PETG_CHOICE: Final = {
    "material_key": "prusament-petg",
    "material_reason": "PETG takes a knock better than PLA",
}


async def unpinned(s: Session) -> tuple[str, str]:
    brief_id = await s.proposed_brief(None, "A plate under 150 g", UNDER_150)
    await s.confirm(brief_id)
    return (await s.call("list_requirements", brief_id=brief_id))["project_id"], brief_id


async def members(s: Session, project_id: str, brief_id: str) -> list[dict[str, Any]]:
    shown = await s.call("variant_set", project_id=project_id, brief_id=brief_id)
    return shown["members"]


def chosen_by_agent(choice: dict[str, str]) -> dict[str, Any]:
    return {
        "key": choice["material_key"],
        "set_by": {
            "kind": "agent_argument",
            "statement": AGENT_CHOSE,
            "reason": choice["material_reason"],
        },
    }


async def test_a_build_with_a_material_and_a_reason_records_the_choice_on_its_slot(
    s: Session,
) -> None:
    project, brief_id = await unpinned(s)
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    assert built["variant_set"]["slot"] == 1
    [member] = await members(s, project, brief_id)
    assert member["material"] == chosen_by_agent(PLA_CHOICE)


async def test_a_build_with_no_material_in_an_unpinned_brief_is_refused_before_any_build(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, brief_id = await unpinned(s)
    monkeypatch.setenv("DOCKER_HOST", NO_DOCKER)
    text = await s.refusal("build_variant", code=PLATE, brief_id=brief_id)
    assert "MaterialMissing" in text
    assert "Never ask the person to choose" in text
    alone = await s.refusal(
        "build_variant", code=PLATE, brief_id=brief_id, material_key="prusament-pla"
    )
    assert "MaterialMissing" in alone
    assert await members(s, project, brief_id) == []


async def test_omitting_the_material_keeps_the_slots_earlier_choice(s: Session) -> None:
    project, brief_id = await unpinned(s)
    await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    edited = await s.call("build_variant", code=THICKER, brief_id=brief_id, slot=1)
    assert (edited["variant_set"]["slot"], edited["variant_set"]["revision"]) == (1, 2)
    [member] = await members(s, project, brief_id)
    assert member["variant_id"] == edited["variant_id"]
    assert member["material"] == chosen_by_agent(PLA_CHOICE)


async def test_each_slot_has_its_own_material(s: Session) -> None:
    project, brief_id = await unpinned(s)
    await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    await s.call("build_variant", code=THICKER, brief_id=brief_id, **PETG_CHOICE)
    shown = await members(s, project, brief_id)
    assert [one["material"] for one in shown] == [
        chosen_by_agent(PLA_CHOICE),
        chosen_by_agent(PETG_CHOICE),
    ]


async def test_the_same_code_with_a_new_material_is_a_new_revision(s: Session) -> None:
    project, brief_id = await unpinned(s)
    first = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    same = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    assert same["variant_set"]["already_member"] is True
    again = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PETG_CHOICE)
    assert again["variant_id"] == first["variant_id"]
    assert (again["variant_set"]["slot"], again["variant_set"]["revision"]) == (1, 2)
    assert again["variant_set"]["already_member"] is False
    [member] = await members(s, project, brief_id)
    assert member["revision"] == 2
    assert member["material"] == chosen_by_agent(PETG_CHOICE)


async def test_scoring_with_the_brief_uses_the_slots_material_and_the_card_says_the_agent_chose(
    s: Session,
) -> None:
    project, brief_id = await unpinned(s)
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    scored = await s.call("score_variant", variant_id=built["variant_id"], brief_id=brief_id)
    assert scored["material_key"] == "prusament-pla"
    assert scored["material"] == chosen_by_agent(PLA_CHOICE)
    read = await s.call("scorecard", variant_id=built["variant_id"], brief_id=brief_id)
    assert read["material"] == scored["material"]
    [member] = await members(s, project, brief_id)
    assert member["card_etag"] == read["etag"]


async def test_a_key_nobody_recorded_is_the_agents_argument_with_no_reason(s: Session) -> None:
    _, brief_id = await unpinned(s)
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    scored = await s.call(
        "score_variant",
        variant_id=built["variant_id"],
        brief_id=brief_id,
        material_key="prusament-petg",
    )
    assert scored["material"]["key"] == "prusament-petg"
    assert scored["material"]["set_by"] == {"kind": "agent_argument", "statement": AGENT_CHOSE}


async def test_a_card_with_no_material_anywhere_is_refused(s: Session) -> None:
    _, brief_id = await unpinned(s)
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    text = await s.refusal("score_variant", variant_id=built["variant_id"])
    assert "MaterialMissing" in text


async def test_a_pinned_brief_takes_its_material_from_the_requirement_and_refuses_another(
    s: Session,
) -> None:
    brief_id = await s.proposed_brief(None, "A PETG plate under 150 g", PETG, UNDER_150)
    await s.confirm(brief_id)
    project = (await s.call("list_requirements", brief_id=brief_id))["project_id"]
    refused = await s.refusal("build_variant", code=PLATE, brief_id=brief_id, **PLA_CHOICE)
    assert "MaterialPinned" in refused
    assert await members(s, project, brief_id) == []
    built = await s.call("build_variant", code=PLATE, brief_id=brief_id)
    assert built["variant_set"]["slot"] == 1
    same = await s.call("build_variant", code=PLATE, brief_id=brief_id, **PETG_CHOICE)
    assert same["variant_set"]["already_member"] is True
    [member] = await members(s, project, brief_id)
    assert member["material"]["key"] == "prusament-petg"
    assert member["material"]["set_by"]["kind"] == "requirement"
