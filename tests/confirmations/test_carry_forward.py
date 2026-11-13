from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import pytest

from cad.briefs import store
from cad.briefs.model import BriefId, MinMass, Proposal, Requirement, requirement_id
from cad.briefs.origins import BriefSpan
from cad.records import signed
from tests.confirmations.test_conflict_warning import CUBE, CUBE_TEXT, PLA, min_mass

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio
REMOVE_PLA: Final = "Remove: Made of Prusament PLA"


async def confirmed_cube(s: Session) -> dict[str, Any]:
    created = await s.call("create_brief", text=CUBE_TEXT)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[CUBE, PLA])
    s.person.answer = "confirm"
    await s.call("ask_to_confirm", project_id=created["project_id"])
    s.person.answer = None
    return created


async def in_force(s: Session, brief_id: str) -> list[str]:
    listed = await s.call("list_requirements", brief_id=brief_id)
    confirmed = listed["proposals"][listed["confirmed_proposal"] - 1]
    return sorted(row["plain"] for row in confirmed["requirements"])


async def page(s: Session, project_id: str) -> str:
    await s.call("ask_to_confirm", project_id=project_id)
    status, body = s.get(s.person.url)
    assert status == 200
    return body


async def id_of(s: Session, brief_id: str, kind: str) -> str:
    listed = await s.call("list_requirements", brief_id=brief_id)
    rows = listed["proposals"][listed["confirmed_proposal"] - 1]["requirements"]
    return next(
        row["requirement"]["id"] for row in rows if row["requirement"]["target"]["kind"] == kind
    )


async def test_confirming_a_narrower_proposal_keeps_what_was_confirmed_before(s: Session) -> None:
    created = await confirmed_cube(s)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[min_mass(5)])
    s.person.answer = "confirm"
    await s.call("ask_to_confirm", project_id=created["project_id"])
    assert await in_force(s, created["brief_id"]) == [
        "Fits inside a box of 20 mm x 20 mm x 20 mm",
        "Made of Prusament PLA",
        "Mass at least 5 g",
    ]


async def test_the_page_shows_the_carried_requirements_beside_the_new_one(s: Session) -> None:
    created = await confirmed_cube(s)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[min_mass(5)])
    body = await page(s, created["project_id"])
    for quote in ("fits in a 20 mm cube", "PLA", "at least 50 g"):
        assert f'<q class="origin">{html.escape(quote)}</q>' in body
    assert "Remove:" not in body


async def test_a_named_removal_is_its_own_row_and_waits_for_confirm(s: Session) -> None:
    created = await confirmed_cube(s)
    pla = await id_of(s, created["brief_id"], "made_of")
    proposed = await s.call("propose_requirements", brief_id=created["brief_id"], remove=[pla])
    assert [row["plain"] for row in proposed["requirements"]] == [
        "Fits inside a box of 20 mm x 20 mm x 20 mm"
    ]
    body = await page(s, created["project_id"])
    assert body.count(REMOVE_PLA) == 1
    assert "Made of Prusament PLA" in await in_force(s, created["brief_id"])
    s.person.answer = "confirm"
    await s.call("ask_to_confirm", project_id=created["project_id"])
    assert await in_force(s, created["brief_id"]) == ["Fits inside a box of 20 mm x 20 mm x 20 mm"]


async def test_a_declined_removal_keeps_the_requirement(s: Session) -> None:
    created = await confirmed_cube(s)
    pla = await id_of(s, created["brief_id"], "made_of")
    await s.call("propose_requirements", brief_id=created["brief_id"], remove=[pla])
    s.person.answer = "decline"
    await s.call("ask_to_confirm", project_id=created["project_id"])
    assert "Made of Prusament PLA" in await in_force(s, created["brief_id"])


def store_mass_alone(s: Session, brief_id: str) -> None:
    """A proposal as the store wrote it before it carried the confirmed set forward."""
    target = MinMass.model_validate({"mass": {"magnitude": 5, "unit": "g"}})
    start = CUBE_TEXT.index("at least 50 g")
    origin = BriefSpan(start=start, end=start + len("at least 50 g"))
    requirement = Requirement(
        id=requirement_id(BriefId(brief_id), target, origin),
        brief_id=BriefId(brief_id),
        target=target,
        origin=origin,
    )
    signed.append(
        signed.Store(s.roots.briefs, "brief"),
        s.roots.briefs / brief_id / store.PROPOSALS,
        lambda number: f"{brief_id}/proposal/{number}",
        lambda existing: (
            Proposal(
                brief_id=BriefId(brief_id),
                number=len(existing) + 1,
                requirements=(requirement,),
                created_at=datetime.now(UTC),
            )
            .model_dump_json()
            .encode()
        ),
    )


async def test_a_proposal_stored_without_the_confirmed_rows_lists_each_as_a_removal(
    s: Session,
) -> None:
    created = await confirmed_cube(s)
    store_mass_alone(s, created["brief_id"])
    body = await page(s, created["project_id"])
    assert body.count("Remove: ") == 2
    assert body.count(REMOVE_PLA) == 1


async def test_removing_a_requirement_the_brief_never_had_is_refused(s: Session) -> None:
    created = await confirmed_cube(s)
    said = await s.text(
        "propose_requirements", brief_id=created["brief_id"], remove=["0123456789abcdef"]
    )
    assert "0123456789abcdef is not a requirement of brief" in said


async def test_a_second_material_needs_the_confirmed_one_removed(s: Session) -> None:
    created = await confirmed_cube(s)
    petg = {"target": {"kind": "made_of", "material": "prusament-petg"}, "quote": "PLA"}
    said = await s.text("propose_requirements", brief_id=created["brief_id"], requirements=[petg])
    assert "pass its id in remove" in said
    pla = await id_of(s, created["brief_id"], "made_of")
    proposed = await s.call(
        "propose_requirements", brief_id=created["brief_id"], requirements=[petg], remove=[pla]
    )
    assert "Made of Prusament PETG" in [row["plain"] for row in proposed["requirements"]]
