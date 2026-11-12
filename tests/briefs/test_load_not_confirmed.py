from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.support.loaded_plate import LOAD, PLATE_TEXT, plate, settled

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]


async def test_fea_is_asked_for_a_load_that_awaits_confirm_and_for_an_assumed_one(
    s: Session,
) -> None:
    created = await s.call("create_brief", text=f"{PLATE_TEXT}, holds 10 N")
    load = LOAD
    row = {
        "target": {"kind": "min_safety_factor", "load": load, "factor": 2},
        "quote": "holds 10 N",
    }
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[row])
    card = await settled(
        s, variant_id=await plate(s), material_key="prusament-pla", brief_id=created["brief_id"]
    )
    asked = [one["instance"] for one in card["results"] if one["check_id"] == "fea"]
    assert len(asked) == 1 and asked[0] != ""
    assert [row["instance"] for row in card["awaiting"]] == asked
    [fea] = [one for one in card["results"] if one["check_id"] == "fea"]
    assert fea["kind"] == "measure_only" and "verdict" not in fea
    assert all("verdict" in one for one in card["results"] if one["check_id"] != "fea")
    other = {**load, "load": {**load["load"], "force": {"magnitude": 20, "unit": "N"}}}
    mine = {
        "target": {
            "kind": "max_deflection",
            "load": other,
            "deflection": {"magnitude": 1, "unit": "mm"},
        },
        "why": "a desk shelf",
    }
    await s.call("propose_requirements", brief_id=created["brief_id"], assumptions=[mine])
    again = await settled(
        s, variant_id=await plate(s), material_key="prusament-pla", brief_id=created["brief_id"]
    )
    loads = {one["instance"] for one in again["results"] if one["check_id"] == "fea"}
    assert len(loads) == 2
    assert {row["instance"] for row in again["assumptions"]} <= loads
    assert all(
        one["kind"] == "measure_only" for one in again["results"] if one["check_id"] == "fea"
    )
