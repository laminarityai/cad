"""A brief holds one row per kind and subject, and a carried row keeps what the person did to it."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from cad.briefs import store
from cad.briefs.model import BriefId, MinMass, Proposal, Requirement, requirement_id
from cad.briefs.origins import BriefSpan
from cad.records import signed
from tests.support.cube import CUBE_TEXT, PLA
from tests.support.load_cases import hole_hook
from tests.support.stress import WORDS, deflection

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio


def sag(mm: float) -> dict[str, Any]:
    row = deflection(hole_hook())
    return {**row, "target": {**row["target"], "deflection": {"magnitude": mm, "unit": "mm"}}}


async def test_a_new_limit_on_the_same_load_case_replaces_the_old_one(s: Session) -> None:
    brief_id = (await s.call("create_brief", text=WORDS))["brief_id"]
    first = await s.call("propose_requirements", brief_id=brief_id, requirements=[sag(2)])
    said = await s.text("propose_requirements", brief_id=brief_id, requirements=[sag(3)])
    assert "one max_deflection per load case" in said and "pass its id in remove" in said
    old = first["requirements"][0]["requirement"]["id"]
    replaced = await s.call(
        "propose_requirements", brief_id=brief_id, requirements=[sag(3)], remove=[old]
    )
    [one] = replaced["requirements"]
    assert one["requirement"]["target"]["deflection"]["magnitude"] == 3


def mass_row(brief_id: str, grams: float) -> Requirement:
    target = MinMass.model_validate({"mass": {"magnitude": grams, "unit": "g"}})
    start = CUBE_TEXT.index("at least 50 g")
    origin = BriefSpan(start=start, end=start + len("at least 50 g"))
    rid = requirement_id(BriefId(brief_id), target, origin)
    return Requirement(id=rid, brief_id=BriefId(brief_id), target=target, origin=origin)


def store_two_masses(s: Session, brief_id: str) -> None:
    """A set stored before a brief held one min_mass, as the store holds it."""
    rows = (mass_row(brief_id, 5), mass_row(brief_id, 6))
    signed.append(
        signed.Store(s.roots.briefs, "brief"),
        s.roots.briefs / brief_id / store.PROPOSALS,
        lambda number: f"{brief_id}/proposal/{number}",
        lambda existing: (
            Proposal(
                brief_id=BriefId(brief_id),
                number=len(existing) + 1,
                requirements=rows,
                created_at=datetime.now(UTC),
            )
            .model_dump_json()
            .encode()
        ),
    )


async def test_a_stored_set_with_two_of_a_kind_takes_an_addition(s: Session) -> None:
    created = await s.call("create_brief", text=CUBE_TEXT)
    store_two_masses(s, created["brief_id"])
    proposed = await s.call(
        "propose_requirements", brief_id=created["brief_id"], requirements=[PLA]
    )
    assert [row["plain"] for row in proposed["requirements"]] == [
        "Mass at least 5 g",
        "Mass at least 6 g",
        "Made of Prusament PLA",
    ]


async def edited_to_120(s: Session) -> str:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    latest = store.read_state(s.roots, brief.brief_id).latest
    assert latest is not None
    [light] = latest.requirement_ids
    assert s.post(s.person.url, "confirm", fields={f"edit-0-{light}": "120 g"})[0] == 200
    await s.call("propose_requirements", brief_id=brief.brief_id, requirements=[s.rows.shelf])
    return brief.brief_id


async def test_a_carried_row_keeps_the_label_of_the_persons_edit(s: Session) -> None:
    brief_id = await edited_to_120(s)
    listed = await s.call("list_requirements", brief_id=brief_id)
    mass, shelf = listed["proposals"][-1]["requirements"]
    assert mass["plain"] == "Mass at most 120 g"
    assert mass["edited_by_user"] == {"proposed": "150 g", "confirmed": "120 g"}
    assert shelf["edited_by_user"] is None


async def test_the_card_marks_the_carried_row_and_the_persons_edit(s: Session) -> None:
    brief_id = await edited_to_120(s)
    project_id = store.read_brief(s.roots, brief_id).project
    await s.call("ask_to_confirm", project_id=project_id)
    body = s.get(s.person.url)[1]
    assert body.count("You confirmed this before") == 1
    assert "you changed it from 150 g" in body
