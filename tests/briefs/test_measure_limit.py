from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import TypeAdapter, ValidationError

from cad.briefs.bindable import BINDABLE
from cad.briefs.model import Target
from cad.checks.report import SPECS

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio

TARGET = TypeAdapter[Target](Target)
TEXT = "A fan plate, under 30 cm³ of material, bolts on with M4 screws"
VOLUME_AT_MOST_30: dict[str, Any] = {
    "target": {
        "kind": "measure_limit",
        "check_id": "mass",
        "measure": "volume",
        "comparator": "at_most",
        "limit": {"magnitude": 30, "unit": "cm^3"},
    },
    "quote": "under 30 cm³ of material",
}
PLATE_20_CM3 = "from build123d import Box\nresult = Box(40, 25, 20)\n"
PLATE_40_CM3 = "from build123d import Box\nresult = Box(40, 25, 40)\n"


def limit_target(**changes: Any) -> dict[str, Any]:
    return {**VOLUME_AT_MOST_30["target"], **changes}


@pytest.mark.parametrize(
    "raw",
    [
        limit_target(check_id="extents", measure="sorted_extent:largest"),
        limit_target(check_id="mass", measure="mass"),
        limit_target(check_id="made_of", measure="volume"),
        limit_target(limit={"magnitude": 30, "unit": "g"}),
        limit_target(limit={"magnitude": 30, "unit": "mm"}),
        limit_target(limit={"magnitude": 0, "unit": "cm^3"}),
        limit_target(limit={"magnitude": -1, "unit": "cm^3"}),
        limit_target(limit={"magnitude": "nan", "unit": "cm^3"}),
        limit_target(limit={"magnitude": 30, "unit": "bogusunit"}),
        limit_target(comparator="about"),
        limit_target(formula="volume * 2"),
    ],
)
def test_a_limit_the_team_catalogue_cannot_hold_is_refused(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TARGET.validate_python(raw)


def test_every_bindable_measure_is_one_a_team_check_reports_in_the_same_unit() -> None:
    measures = {spec.id: spec.measures for spec in SPECS}
    assert BINDABLE
    for (check_id, measure), bound in BINDABLE.items():
        assert check_id in measures, f"{check_id} is not a registered check"
        assert measures[check_id][measure] == bound.unit


async def confirmed_brief(s: Session) -> str:
    s.person.answer = "confirm"
    brief = await s.call("create_brief", text=TEXT)
    proposed = await s.call(
        "propose_requirements", brief_id=brief["brief_id"], requirements=[VOLUME_AT_MOST_30]
    )
    assert proposed["requirements"][0]["plain"] == (
        "The volume of material in the part is at most 30 cm³"
    )
    assert proposed["requirements"][0]["check"] == "mass"
    assert (await s.call("ask_to_confirm", project_id=brief["project_id"]))["status"] == "answered"
    return brief["brief_id"]


async def volume_row(s: Session, brief_id: str, code: str) -> dict[str, Any]:
    built = await s.call("build_variant", code=code)
    card = await s.call(
        "score_variant",
        variant_id=built["variant_id"],
        material_key="prusament-pla",
        brief_id=brief_id,
    )
    [row] = card["basis"]["requirements"]
    return row


async def test_a_plate_under_the_confirmed_volume_passes_and_one_over_it_fails(s: Session) -> None:
    brief_id = await confirmed_brief(s)
    light = await volume_row(s, brief_id, PLATE_20_CM3)
    heavy = await volume_row(s, brief_id, PLATE_40_CM3)
    assert (light["kind"], light["check_id"], light["verdict"]) == ("checked", "mass", "pass")
    assert (heavy["kind"], heavy["check_id"], heavy["verdict"]) == ("checked", "mass", "fail")
    assert light["comparisons"] == [
        {
            "measure": "volume",
            "comparator": "at_most",
            "limit": {"magnitude": 30.0, "unit": "cm³"},
            "verdict": "pass",
        }
    ]
    assert heavy["comparisons"][0]["verdict"] == "fail"
    assert heavy["reason"] == "The measured value does not meet the confirmed limit."


async def test_the_page_says_in_the_servers_words_what_decides_the_limit(s: Session) -> None:
    brief = await s.call("create_brief", text=TEXT)
    await s.call(
        "propose_requirements", brief_id=brief["brief_id"], requirements=[VOLUME_AT_MOST_30]
    )
    await s.call("ask_to_confirm", project_id=brief["project_id"])
    status, body = s.get(s.person.url)
    assert status == 200
    assert "The volume of material in the part is at most 30 cm³" in body
    assert "Decided by the mass check, which measures the volume of material in the part" in body
    assert f'<q class="origin">{html.escape(VOLUME_AT_MOST_30["quote"])}</q>' in body


async def test_a_measure_the_catalogue_lacks_is_refused_when_proposed(s: Session) -> None:
    brief = await s.call("create_brief", text=TEXT)
    refused = await s.text(
        "propose_requirements",
        brief_id=brief["brief_id"],
        requirements=[
            {
                "target": limit_target(check_id="extents", measure="sorted_extent:largest"),
                "quote": "under 30 cm³ of material",
            }
        ],
    )
    assert "no limit can bind to extents:sorted_extent:largest" in refused
    assert "mass:volume" in refused
