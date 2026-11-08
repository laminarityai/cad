from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cad.scorecard.model import AGENT_MEASUREMENT

if TYPE_CHECKING:
    from conftest import Person, Session

pytestmark = pytest.mark.anyio

HOLED_PLATE = (
    "from build123d import *\nresult = Box(40, 20, 3) - Pos(10, 0, 0) * Cylinder(2.1, 3)\n"
)
TEXT = "A mounting plate under 150 g. It bolts on with M4 screws."
ROWS: list[dict[str, Any]] = [
    {
        "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
        "quote": "under 150 g",
    },
    {
        "target": {"kind": "unchecked", "statement": "The holes fit M4 screws"},
        "quote": "It bolts on with M4 screws",
    },
]
HOLE = (
    "bores = [f for f in part.faces() if f.geom_type == GeomType.CYLINDER]\n"
    "report('smallest_hole', min(2 * f.radius for f in bores), 'mm')"
)


async def confirmed(s: Session, person: Person) -> tuple[str, str, str]:
    person.answer = "confirm"
    created = await s.call("create_brief", text=TEXT)
    brief_id = created["brief_id"]
    await s.call("propose_requirements", brief_id=brief_id, requirements=ROWS)
    assert (await s.call("ask_to_confirm", project_id=created["project_id"]))["status"] == (
        "answered"
    )
    listed = await s.call("list_requirements", brief_id=brief_id)
    unchecked = next(
        r["requirement"]["id"]
        for r in listed["proposals"][0]["requirements"]
        if r["requirement"]["target"]["kind"] == "unchecked"
    )
    variant_id = (await s.call("build_variant", code=HOLED_PLATE, brief_id=brief_id))["variant_id"]
    return brief_id, unchecked, variant_id


def own(requirement_id: str, code: str, title: str = "Smallest hole diameter") -> dict[str, str]:
    return {"requirement_id": requirement_id, "title": title, "code": code}


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


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("raise ValueError('agent bug')", "ValueError('agent bug')"),
        ("report('x', float('nan'), 'mm')", "not a finite number"),
        ("report('x', 1.0, 'inch')", "has unit 'inch'"),
        ("report('Bad Name', 1.0, 'mm')", "does not match"),
        ("while True:\n    pass", "timed out after 30 s"),
    ],
)
async def test_a_broken_measurement_fails_with_its_reason_and_no_value(
    s: Session, person: Person, code: str, reason: str
) -> None:
    brief_id, r2, variant_id = await confirmed(s, person)
    card = await s.call(
        "score_variant",
        variant_id=variant_id,
        material_key="prusament-pla",
        brief_id=brief_id,
        own_measurements=[own(r2, code)],
    )
    [row] = card["not_verified"]
    assert row["values"] == []
    assert reason in row["failed"]


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
