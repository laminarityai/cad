from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import trace_store

from cad.scorecard.model import AGENT_MEASUREMENT
from tests.support.holed_plate import HOLE, confirmed, own

if TYPE_CHECKING:
    from tests.support.browser import Person
    from tests.support.session import Session

pytestmark = pytest.mark.anyio


async def test_an_own_measurement_is_information_beside_identical_team_results(
    s: Session, person: Person
) -> None:
    brief_id, r2, variant_id = await confirmed(s, person)
    args = {"variant_id": variant_id, "material_key": "prusament-pla", "brief_id": brief_id}
    plain = await s.call("score_variant", **args)
    measured = await s.call("score_variant", **args, own_measurements=[own(r2, HOLE)])
    assert "not_verified" not in plain
    assert {k: v for k, v in measured.items() if k != "not_verified"} == plain
    [row] = measured["not_verified"]
    assert row["label"] == AGENT_MEASUREMENT
    assert row["requirement_id"] == r2
    assert row["failed"] is None
    assert row["values"] == [
        {"name": "smallest_hole", "value": {"magnitude": pytest.approx(4.2), "unit": "mm"}}
    ]
    assert not {"verdict", "limit", "comparator", "check_id"} & set(row)
    assert r2 in measured["basis"]["unverified_requirements"]


async def test_a_measurement_of_a_checked_requirement_is_refused(
    s: Session, person: Person
) -> None:
    brief_id, _, variant_id = await confirmed(s, person)
    listed = await s.call("list_requirements", brief_id=brief_id)
    checked = next(
        r["requirement"]["id"]
        for r in listed["proposals"][0]["requirements"]
        if r["requirement"]["target"]["kind"] == "max_mass"
    )
    text = await s.text(
        "score_variant",
        variant_id=variant_id,
        material_key="prusament-pla",
        brief_id=brief_id,
        own_measurements=[own(checked, HOLE)],
    )
    assert "MeasurementRefused" in text
    assert "not an unchecked requirement" in text


async def test_a_measurement_without_a_brief_is_refused(s: Session, person: Person) -> None:
    _, r2, variant_id = await confirmed(s, person)
    text = await s.text(
        "score_variant",
        variant_id=variant_id,
        material_key="prusament-pla",
        own_measurements=[own(r2, HOLE)],
    )
    assert "MeasurementRefused" in text


async def test_the_tracer_reads_a_card_the_server_stored_and_counts_its_measurement(
    s: Session, person: Person, capsys: pytest.CaptureFixture[str]
) -> None:
    brief_id, r2, variant_id = await confirmed(s, person)
    card = await s.call(
        "score_variant",
        variant_id=variant_id,
        material_key="prusament-pla",
        brief_id=brief_id,
        own_measurements=[own(r2, HOLE)],
    )
    root = s.roots.briefs.parent
    transcript = root / "transcript.json"
    call: dict[str, Any] = {
        "type": "tool_use",
        "id": "1",
        "name": "mcp__cad__score_variant",
        "input": {},
    }
    text = {"type": "text", "text": json.dumps(card)}
    shown = {"type": "tool_result", "tool_use_id": "1", "content": [text]}
    transcript.write_text(
        json.dumps(
            [
                {"type": "assistant", "message": {"content": [call]}},
                {"type": "user", "message": {"content": [shown]}},
            ]
        )
    )
    trace = [
        str(transcript),
        "--root",
        str(root / "variants"),
        "--briefs-root",
        str(s.roots.briefs),
        "--projects-root",
        str(s.roots.projects),
    ]
    assert trace_store.main(trace) == 0
    printed = capsys.readouterr().out
    assert "cards unreadable: 0" in printed
    assert "agent measurements: 1, not verified" in printed


async def test_a_flood_of_values_is_capped_in_the_sandbox_and_leaves_other_rows_and_the_part_alone(
    s: Session, person: Person
) -> None:
    brief_id, r2, variant_id = await confirmed(s, person)
    listed = await s.call("list_requirements", brief_id=brief_id)
    r3 = next(
        r["requirement"]["id"]
        for r in listed["proposals"][0]["requirements"]
        if r["requirement"]["target"].get("statement") == "The plate looks tidy"
    )
    flood = (
        "part.wrapped = Box(1, 1, 1).wrapped\n"
        "for i in range(120):\n    report(f'v{i}', float(i), 'mm')"
    )
    card = await s.call(
        "score_variant",
        variant_id=variant_id,
        material_key="prusament-pla",
        brief_id=brief_id,
        own_measurements=[
            own(r2, flood, title="Flood"),
            own(r3, "report('volume', part.volume, 'mm^3')", title="Volume"),
        ],
    )
    flooded, volume = card["not_verified"]
    assert [v["name"] for v in flooded["values"]] == [f"v{i}" for i in range(8)]
    assert flooded["note"].startswith("112 more values were dropped")
    [measured] = volume["values"]
    assert measured["value"]["magnitude"] == pytest.approx(
        40 * 20 * 3 - 3.14159 * 2.1**2 * 3, rel=1e-3
    )
