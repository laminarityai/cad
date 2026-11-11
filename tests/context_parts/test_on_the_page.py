from __future__ import annotations

import hashlib
import html
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from cad.context_parts.store import confirmed_parts, part_brep
from cad.operations import reads
from cad.projects.model import ProjectId

if TYPE_CHECKING:
    from conftest import Session

    from cad.operations.model import Tenant

pytestmark = pytest.mark.anyio
TEXT = "A clip that slides onto the rail, at least 0.2 mm clear of it, under 150 g"
UNDER_150 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}


async def brief_with_rail(s: Session) -> tuple[dict[str, Any], dict[str, Any], str]:
    created = await s.call("create_brief", text=TEXT)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[UNDER_150])
    vid = s.variant("result = Box(30, 20, 10)\n")
    part = await s.call(
        "propose_context_part",
        brief_id=created["brief_id"],
        quote="the rail",
        name="rail",
        variant_id=vid,
    )
    return created, part, vid


async def test_a_proposed_part_waits_on_the_page_beside_the_requirements(s: Session) -> None:
    created, part, vid = await brief_with_rail(s)
    asked = await s.call("ask_to_confirm", project_id=created["project_id"])
    status, body = s.get(s.person.url)
    assert part["part_id"] == "part-" + hashlib.sha256(s.rows.rail).hexdigest()[:16]
    assert (part["status"], part["facts"]) == ("waiting", s.rows.rail_facts.model_dump(mode="json"))
    assert asked["status"] == "pending"
    assert asked["items"][1] == {
        "kind": "context_part",
        "part_id": part["part_id"],
        "name": "rail",
        "outcome": "waiting",
        "box_min": [-15, 0, 0],
        "box_max": [15, 20, 10],
        "note": "",
        "newer_revision": None,
    }
    assert status == 200
    assert body.count('<section class="item">') == 2
    assert "Item 2. A part your design must fit with" in body
    assert "rail: a box of 30 by 20 by 10 mm" in body
    assert '<q class="origin">the rail</q>' in body
    assert "The fit check fails a variant that overlaps it and measures the clearance" in body
    assert 'name="edit-1-' not in body
    assert 'name="edit-0-' in body
    reader = cast("Tenant", SimpleNamespace(roots=s.roots))
    [shown] = reads.project(
        reader, reads.ProjectInput(project_id=created["project_id"])
    ).context_parts
    assert (shown.name, shown.variant_id, shown.outcome, shown.size_mm) == (
        "rail",
        vid,
        "waiting",
        (30, 20, 10),
    )


async def test_one_click_confirms_the_requirements_and_the_part(s: Session) -> None:
    created, part, _ = await brief_with_rail(s)
    project = ProjectId(created["project_id"])
    await s.call("ask_to_confirm", project_id=project)
    assert confirmed_parts(s.roots.projects, project) == ()
    posted = s.post(s.person.url, "confirm")
    asked = await s.call("ask_to_confirm", project_id=project)
    listed = await s.call("list_requirements", brief_id=created["brief_id"])
    [confirmed] = confirmed_parts(s.roots.projects, project)
    assert posted[0] == 200
    assert "You confirmed 2 and declined 0" in posted[1]
    assert asked["status"] == "answered"
    assert [i["outcome"] for i in asked["items"]] == ["confirmed", "confirmed"]
    assert listed["confirmed_proposal"] == 1
    assert (confirmed.record.id, confirmed.record.name) == (part["part_id"], "rail")
    assert part_brep(s.roots.projects, confirmed) == s.rows.rail


async def test_a_declined_part_is_asked_again_when_it_is_proposed_again(s: Session) -> None:
    created, part, vid = await brief_with_rail(s)
    project = created["project_id"]
    await s.call("ask_to_confirm", project_id=project)
    s.post(s.person.url, "confirm", "that is the old rail", {"decline-1": "decline"})
    declined = await s.call("ask_to_confirm", project_id=project)
    again = await s.call(
        "propose_context_part",
        brief_id=created["brief_id"],
        quote="the rail",
        name="rail",
        variant_id=vid,
    )
    asked = await s.call("ask_to_confirm", project_id=project)
    body = s.get(s.person.url)[1]
    records = sorted((s.roots.projects / project / "context_parts").glob("*.signed"))
    assert [(i["outcome"], i["note"]) for i in declined["items"]] == [
        ("confirmed", ""),
        ("declined", "that is the old rail"),
    ]
    assert "propose_context_part" in declined["next"]
    assert (again["part_id"], again["status"]) == (part["part_id"], "waiting")
    assert len(records) == 2
    assert [(i["kind"], i["outcome"]) for i in asked["items"]] == [
        ("requirements", "confirmed"),
        ("context_part", "waiting"),
    ]
    assert body.count('<section class="item">') == 1
    assert "A part your design must fit with" in body
    assert confirmed_parts(s.roots.projects, ProjectId(project)) == ()
    assert s.post(s.person.url, "confirm")[0] == 200
    assert len(confirmed_parts(s.roots.projects, ProjectId(project))) == 1


async def test_the_page_refuses_an_edit_to_a_part_and_records_nothing(s: Session) -> None:
    created, _, _ = await brief_with_rail(s)
    await s.call("ask_to_confirm", project_id=created["project_id"])
    status, body = s.post(s.person.url, "confirm", fields={f"edit-1-{'0' * 16}": "12 mm"})
    assert status == 400
    assert html.escape("Item 2. A part your design must fit with has no number to change") in body
    assert not (s.roots.projects / created["project_id"] / "answers").exists()
    assert s.post(s.person.url, "confirm")[0] == 200
