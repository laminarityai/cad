from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import pytest

from cad.context_parts.store import confirmed_parts, fitted_by
from cad.projects.model import ProjectId

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio

BOX: Final = "A box for SD cards"
LID: Final = "A lid for slot 1 that fits snugly on top"
SOLID: Final = {"target": {"kind": "closed_solid"}, "quote": "A box"}
CHOICE: Final = {"material_key": "prusament-pla", "material_reason": "stiff and easy to print"}
OLD_BOX: Final = b"the box as the person confirmed it"
LIGHTER_BOX: Final = b"the box with less plastic"


@dataclass(frozen=True)
class Fitted:
    project: ProjectId
    box: str
    lid: str
    part: str
    old: str


async def box_with_a_fitted_lid(s: Session) -> Fitted:
    created = await s.call("create_brief", text=BOX)
    box, project = created["brief_id"], ProjectId(created["project_id"])
    await s.call("propose_requirements", brief_id=box, requirements=[SOLID])
    s.person.answer = "confirm"
    await s.call("ask_to_confirm", project_id=project)
    old = s.variant("result = Box(40, 30, 20)\n", OLD_BOX)
    await s.call("build_variant", code="result = Box(40, 30, 20)\n", brief_id=box, slot=1, **CHOICE)
    lid = (await s.call("create_brief", text=LID, project_id=project))["brief_id"]
    part = await s.call(
        "propose_context_part", brief_id=lid, quote="slot 1", name="SD card box", variant_id=old
    )
    clearance = {
        "target": {
            "kind": "min_clearance",
            "part": part["part_id"],
            "clearance": {"magnitude": 0.2, "unit": "mm"},
        },
        "quote": "fits snugly",
    }
    await s.call("propose_requirements", brief_id=lid, requirements=[clearance])
    await s.call("ask_to_confirm", project_id=project)
    return Fitted(project, box, lid, part["part_id"], old)


async def lighter(s: Session, fitted: Fitted) -> tuple[str, dict[str, Any]]:
    new = s.variant("result = Box(40, 30, 16)\n", LIGHTER_BOX)
    built = await s.call(
        "build_variant", code="result = Box(40, 30, 16)\n", brief_id=fitted.box, slot=1
    )
    return new, built


def part_item(asked: dict[str, Any]) -> dict[str, Any]:
    [item] = [one for one in asked["items"] if one["kind"] == "context_part"]
    return item


async def test_revising_the_slot_a_part_came_from_says_the_part_is_out_of_date(
    s: Session,
) -> None:
    fitted = await box_with_a_fitted_lid(s)
    new, built = await lighter(s, fitted)
    asked = await s.call("ask_to_confirm", project_id=fitted.project)
    assert built["variant_set"]["revision"] == 2
    assert built["context_parts_out_of_date"] == [fitted.part]
    assert part_item(asked)["outcome"] == "confirmed"
    assert part_item(asked)["newer_revision"] == {
        "brief_id": fitted.box,
        "slot": 1,
        "variant_id": new,
    }
    [measured] = confirmed_parts(s.roots.projects, fitted.project)
    assert measured.record.source.variant_id == fitted.old


async def test_proposing_the_newer_revision_updates_the_part_and_keeps_its_requirements(
    s: Session,
) -> None:
    fitted = await box_with_a_fitted_lid(s)
    new, _ = await lighter(s, fitted)
    s.person.answer = None
    update = await s.call(
        "propose_context_part",
        brief_id=fitted.lid,
        quote="slot 1",
        name="SD card box",
        variant_id=new,
    )
    waiting = await s.call("ask_to_confirm", project_id=fitted.project)
    _, page = s.get(s.person.url)
    [still_measured] = confirmed_parts(s.roots.projects, fitted.project)
    assert (update["part_id"], update["status"]) == (fitted.part, "waiting")
    assert part_item(waiting)["outcome"] == "waiting"
    assert "SD card box, a newer revision of the part you confirmed" in page
    assert still_measured.record.source.variant_id == fitted.old

    s.post(s.person.url, "confirm")
    asked = await s.call("ask_to_confirm", project_id=fitted.project)
    listed = await s.call("list_requirements", brief_id=fitted.lid)
    [measured] = confirmed_parts(s.roots.projects, fitted.project)
    assert (part_item(asked)["outcome"], part_item(asked)["newer_revision"]) == ("confirmed", None)
    assert (measured.record.id, measured.record.source.variant_id) == (fitted.part, new)
    assert [p["proposal"] for p in listed["proposals"]] == [1]
    assert listed["proposals"][0]["status"] == "confirmed"


async def test_a_declined_update_leaves_the_confirmed_geometry_measured(s: Session) -> None:
    fitted = await box_with_a_fitted_lid(s)
    new, _ = await lighter(s, fitted)
    s.person.answer = "decline"
    await s.call(
        "propose_context_part",
        brief_id=fitted.lid,
        quote="slot 1",
        name="SD card box",
        variant_id=new,
    )
    asked = await s.call("ask_to_confirm", project_id=fitted.project)
    [measured] = confirmed_parts(s.roots.projects, fitted.project)
    assert measured.record.source.variant_id == fitted.old
    assert part_item(asked)["outcome"] == "declined"


async def confirm_update(s: Session, fitted: Fitted, variant_id: str) -> dict[str, Any]:
    s.person.answer = "confirm"
    proposed = await s.call(
        "propose_context_part",
        brief_id=fitted.lid,
        quote="slot 1",
        name="SD card box",
        variant_id=variant_id,
    )
    await s.call("ask_to_confirm", project_id=fitted.project)
    return proposed


async def test_a_slot_built_back_to_the_confirmed_first_geometry_updates_the_part_again(
    s: Session,
) -> None:
    fitted = await box_with_a_fitted_lid(s)
    new, _ = await lighter(s, fitted)
    await confirm_update(s, fitted, new)
    back = await s.call(
        "build_variant", code="result = Box(40, 30, 20)\n", brief_id=fitted.box, slot=1
    )
    assert back["context_parts_out_of_date"] == [fitted.part]
    again = await confirm_update(s, fitted, fitted.old)
    asked = await s.call("ask_to_confirm", project_id=fitted.project)
    [measured] = confirmed_parts(s.roots.projects, fitted.project)
    assert again["part_id"] == fitted.part
    assert (measured.record.id, measured.record.source.variant_id) == (fitted.part, fitted.old)
    assert part_item(asked)["newer_revision"] is None


async def test_an_older_revision_is_not_called_newer_and_waits_for_the_person(
    s: Session,
) -> None:
    fitted = await box_with_a_fitted_lid(s)
    new, _ = await lighter(s, fitted)
    await confirm_update(s, fitted, new)
    s.person.answer = None
    older = await s.call(
        "propose_context_part",
        brief_id=fitted.lid,
        quote="slot 1",
        name="SD card box",
        variant_id=fitted.old,
    )
    await s.call("ask_to_confirm", project_id=fitted.project)
    _, page = s.get(s.person.url)
    [measured] = confirmed_parts(s.roots.projects, fitted.project)
    assert older["status"] == "waiting"
    assert "a newer revision of the part you confirmed" not in page
    assert measured.record.source.variant_id == new


async def test_a_part_is_fitted_by_the_brief_it_was_proposed_for_and_not_its_own(
    s: Session,
) -> None:
    fitted = await box_with_a_fitted_lid(s)
    assert fitted_by(s.roots.projects, fitted.project, fitted.box) == ()
    [part] = fitted_by(s.roots.projects, fitted.project, fitted.lid)
    assert part.record.id == fitted.part
