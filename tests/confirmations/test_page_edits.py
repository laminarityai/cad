from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cad.briefs import store
from cad.briefs.words import describe
from cad.confirmations import answers, page
from cad.confirmations.answers import Edit, PageAnswer
from cad.confirmations.page import DECLINE_EDITS
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable

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


async def test_an_edit_counts_on_a_confirmed_item_beside_a_declined_one(s: Session) -> None:
    first = await s.proposed(s.rows.under_150)
    second = await s.proposed(s.rows.envelope, project_id=first.project_id)
    [light], [box] = row_ids(s, first.brief_id), row_ids(s, second.brief_id)
    await s.ask(first)
    url = s.person.url
    on_declined = {f"edit-1-{box}": "200 x 100 x 50 mm", "decline-1": "decline"}
    status, body = s.post(url, "confirm", fields=on_declined)
    assert (status, html.escape(DECLINE_EDITS) in body) == (400, True)
    mixed = {f"edit-0-{light}": "100 g", "decline-1": "decline"}
    assert s.post(url, "confirm", "box is wrong", fields=mixed)[0] == 200
    confirmed = store.confirmed_requirements(s.roots, first.brief_id)
    assert confirmed is not None
    assert [describe(r) for r in confirmed.requirements] == ["Mass at most 100 g"]
    assert store.confirmed_requirements(s.roots, second.brief_id) is None


async def test_a_single_item_page_takes_an_edit_with_no_decline_box(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    [light] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    shown = s.get(s.person.url)[1]
    assert (f'name="edit-0-{light}"' in shown, 'name="decline-' in shown) == (True, False)
    edit = {f"edit-0-{light}": "120 g"}
    assert s.post(s.person.url, "confirm", fields={**edit, "decline-0": "decline"})[0] == 400
    assert s.post(s.person.url, "confirm", fields=edit)[0] == 200
    confirmed = store.confirmed_requirements(s.roots, brief.brief_id)
    assert confirmed is not None
    assert [describe(r) for r in confirmed.requirements] == ["Mass at most 120 g"]


async def test_a_resent_edit_counts_after_a_failed_post(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = await s.proposed(s.rows.under_150)
    [light] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    real = page.append_answer
    calls: list[PageAnswer] = []

    def once_broken(projects: Path, project: ProjectId, answer: PageAnswer) -> bool:
        calls.append(answer)
        if len(calls) == 1:
            raise RuntimeError("an unexpected failure")
        return real(projects, project, answer)

    monkeypatch.setattr(page, "append_answer", once_broken)
    edit = {f"edit-0-{light}": "120 g"}
    assert s.post(s.person.url, "confirm", fields=edit)[0] == 500
    assert f'name="edit-0-{light}" placeholder="150 g"' in s.get(s.person.url)[1]
    assert s.post(s.person.url, "confirm", fields=edit)[0] == 200
    confirmed = store.confirmed_requirements(s.roots, brief.brief_id)
    assert confirmed is not None
    assert [describe(r) for r in confirmed.requirements] == ["Mass at most 120 g"]


async def test_a_store_failure_while_reading_an_edit_leaves_the_page_open(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = await s.proposed(s.rows.under_150)
    [light] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    real = store.read_state
    calls: list[str] = []

    def once_unusable(roots: Roots, raw_id: str) -> store.BriefState:
        calls.append(raw_id)
        if len(calls) == 1:
            raise StoreUnusable("the brief store cannot be read")
        return real(roots, raw_id)

    monkeypatch.setattr(store, "read_state", once_unusable)
    edit = {f"edit-0-{light}": "120 g"}
    first = s.post(s.person.url, "confirm", fields=edit)
    assert (first[0], "nothing was recorded. Try again" in first[1]) == (500, True)
    assert s.post(s.person.url, "confirm", fields=edit)[0] == 200


async def test_list_requirements_says_the_user_changed_the_number(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150, s.rows.shelf)
    [light, _] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    assert s.post(s.person.url, "confirm", fields={f"edit-0-{light}": "120 g"})[0] == 200
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    edited, untouched = listed["proposals"][0]["requirements"]
    assert edited["edited_by_user"] == {"proposed": "150 g", "confirmed": "120 g"}
    assert untouched["edited_by_user"] is None


async def test_text_pint_would_choke_on_is_refused_and_the_page_stays_open(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    [light] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    texts = ("120 g's", '120 g"', "120 g (", "120 g/0", "120 g**0", "120 g-))")
    refused = [s.post(s.person.url, "confirm", fields={f"edit-0-{light}": t}) for t in texts]
    assert [status for status, _ in refused] == [400] * len(texts)
    assert all(html.escape("Mass at most 150 g: Write a number") in body for _, body in refused)
    assert answers.read_ledger(s.roots.projects, ProjectId(brief.project_id)).answers == ()
    assert s.post(s.person.url, "confirm", fields={f"edit-0-{light}": "120 g"})[0] == 200


async def test_the_recorded_page_says_what_the_person_changed(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150, s.rows.envelope)
    light, box = row_ids(s, brief.brief_id)
    await s.ask(brief)
    edits = {f"edit-0-{light}": "120 G", f"edit-0-{box}": "120 x 80 x 40 mm"}
    status, body = s.post(s.person.url, "confirm", fields=edits)
    assert status == 200
    assert "Mass at most 120 g (you changed it from 150 g)." in body
    assert "Fits inside a box" not in body


async def test_a_refusal_on_a_page_of_two_briefs_names_the_item(s: Session) -> None:
    first = await s.proposed(s.rows.under_150)
    second = await s.proposed(s.rows.under_150, project_id=first.project_id)
    [light] = row_ids(s, second.brief_id)
    await s.ask(first)
    shown = s.get(s.person.url)[1]
    assert "<h2>Item 1. Requirements" in shown and "<h2>Item 2. Requirements" in shown
    status, body = s.post(s.person.url, "confirm", fields={f"edit-1-{light}": "120 mm"})
    assert status == 400
    assert html.escape("Item 2. Mass at most 150 g: mm is a length, not a mass.") in body


async def test_a_change_past_the_sixth_digit_is_refused_and_one_within_it_shows(
    s: Session,
) -> None:
    brief = await s.proposed(s.rows.under_150)
    [light] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    tiny = s.post(s.person.url, "confirm", fields={f"edit-0-{light}": "150.0000001 g"})
    assert (tiny[0], "Use at most 6 digits" in tiny[1]) == (400, True)
    assert s.post(s.person.url, "confirm", fields={f"edit-0-{light}": "150.001 g"})[0] == 200
    listed = await s.call("list_requirements", brief_id=brief.brief_id)
    [edited] = listed["proposals"][0]["requirements"]
    assert edited["edited_by_user"] == {"proposed": "150 g", "confirmed": "150.001 g"}


async def test_a_field_of_only_spaces_is_no_edit(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    [light] = row_ids(s, brief.brief_id)
    await s.ask(brief)
    status, _ = s.post(s.person.url, "confirm", fields={f"edit-0-{light}": "   "})
    assert status == 200
    [(_, answered)] = answers.read_ledger(s.roots.projects, ProjectId(brief.project_id)).answers
    assert answered.answers[0].edits == ()
