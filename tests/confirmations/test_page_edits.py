from __future__ import annotations

import html
from typing import TYPE_CHECKING

import pytest

from cad.briefs import store
from cad.confirmations import answers
from cad.confirmations.answers import Edit
from cad.confirmations.page import DECLINE_EDITS
from cad.projects.model import ProjectId

if TYPE_CHECKING:
    from conftest import Session

pytestmark = pytest.mark.anyio


def row_ids(s: Session, brief_id: str) -> list[str]:
    return [r.id for r in store.read_state(s.roots, brief_id).proposals[-1].proposal.requirements]


async def test_a_person_changes_one_number_and_confirms_in_one_visit(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150, s.rows.envelope, s.rows.shelf)
    light, box, shelf = row_ids(s, brief.brief_id)
    await s.ask(brief)
    page = s.get(s.person.url)[1]
    assert f'name="edit-0-{light}" placeholder="150 g"' in page
    assert f'name="edit-0-{box}" placeholder="120 mm x 80 mm x 40 mm"' in page
    assert f"edit-0-{shelf}" not in page
    status, _ = s.post(s.person.url, "confirm", fields={f"edit-0-{light}": "120 g"})
    assert status == 200
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    rows = listed["proposals"][0]["requirements"]
    assert [(r["plain"], r["status"]) for r in rows] == [
        ("Mass at most 120 g", "confirmed"),
        ("Fits inside a box of 120 mm x 80 mm x 40 mm", "confirmed"),
        ("holds a 2 kg shelf", "confirmed"),
    ]
    assert rows[0]["requirement"]["id"] != light
    confirmed = store.confirmed_requirements(s.roots, brief.brief_id)
    assert confirmed is not None
    assert [r.id for r in confirmed.requirements] == [r["requirement"]["id"] for r in rows]
    [(_, answered)] = answers.read_ledger(s.roots.projects, ProjectId(brief.project_id)).answers
    assert answered.answers[0].edits == (Edit(row=light, text="120 g"),)
    asked = await s.ask(brief)
    assert [i["outcome"] for i in asked["items"]] == ["confirmed"]


async def test_each_brief_on_one_page_takes_its_own_edit(s: Session) -> None:
    first = await s.proposed(s.rows.under_150)
    second = await s.proposed(s.rows.envelope, project_id=first.project_id)
    [light], [box] = row_ids(s, first.brief_id), row_ids(s, second.brief_id)
    await s.ask(first)
    edits = {f"edit-0-{light}": "100 g", f"edit-1-{box}": "200 x 100 x 50 mm"}
    assert s.post(s.person.url, "confirm", fields=edits)[0] == 200
    plain = [
        (await s.call("list_requirements", brief_id=b.brief_id))["proposals"][0]["requirements"][0]
        for b in (first, second)
    ]
    assert [r["plain"] for r in plain] == [
        "Mass at most 100 g",
        "Fits inside a box of 200 mm x 100 mm x 50 mm",
    ]


async def test_an_edit_sent_under_another_briefs_index_is_refused(s: Session) -> None:
    first = await s.proposed(s.rows.under_150)
    await s.proposed(s.rows.envelope, project_id=first.project_id)
    [light] = row_ids(s, first.brief_id)
    await s.ask(first)
    status, body = s.post(s.person.url, "confirm", fields={f"edit-1-{light}": "100 g"})
    assert (status, "This page changed" in body) == (400, True)
    assert answers.read_ledger(s.roots.projects, ProjectId(first.project_id)).answers == ()


async def test_a_number_the_page_cannot_read_is_refused_and_the_page_stays_open(
    s: Session,
) -> None:
    brief = await s.proposed(s.rows.under_150)
    [light] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    url = s.person.url
    refused = [
        s.post(url, "confirm", fields={f"edit-0-{light}": text})
        for text in ("120", "120 mm", "about 100 g")
    ]
    declined = s.post(url, "decline", "lighter", fields={f"edit-0-{light}": "120 g"})
    assert [status for status, _ in refused] == [400, 400, 400]
    assert all(html.escape("Mass at most 150 g: ") in body for _, body in refused)
    assert (declined[0], html.escape(DECLINE_EDITS) in declined[1]) == (400, True)
    assert answers.read_ledger(s.roots.projects, ProjectId(brief.project_id)).answers == ()
    assert s.post(url, "confirm", fields={f"edit-0-{light}": "120 g"})[0] == 200
    confirmed = store.confirmed_requirements(s.roots, brief.brief_id)
    assert confirmed is not None and len(confirmed.requirements) == 1
