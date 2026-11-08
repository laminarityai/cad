from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cad.confirmations import answers, page
from cad.confirmations.answers import PageAnswer
from cad.projects.model import ProjectBusy, ProjectId

if TYPE_CHECKING:
    from conftest import Session

pytestmark = pytest.mark.anyio


def answer_files(s: Session, project_id: str) -> list[Path]:
    return sorted((s.roots.projects / project_id / answers.ANSWERS).glob("*"))


async def test_one_visit_declines_one_brief_and_confirms_the_other(s: Session) -> None:
    right = await s.proposed(s.rows.under_150)
    wrong = await s.proposed(s.rows.shelf, project_id=right.project_id)
    await s.ask(right)
    shown = s.get(s.person.url)[1]
    assert shown.count('name="decline-') == 2
    status, said = s.post(
        s.person.url, "confirm", "the shelf weighs 3 kg", {"decline-1": "decline"}
    )
    asked = await s.ask(right)
    assert (status, "confirmed 1 and declined 1" in said) == (200, True)
    assert [(i["brief_id"], i["outcome"], i["note"]) for i in asked["items"]] == [
        (right.brief_id, "confirmed", ""),
        (wrong.brief_id, "declined", "the shelf weighs 3 kg"),
    ]
    await s.call("propose_requirements", brief_id=wrong.brief_id, requirements=[s.rows.solid])
    reasked = await s.ask(right)
    again = s.get(s.person.url)[1]
    assert again.count('<section class="item">') == 1
    assert [(i["brief_id"], i["outcome"]) for i in reasked["items"]] == [
        (right.brief_id, "confirmed"),
        (wrong.brief_id, "waiting"),
    ]


async def test_a_decline_of_an_item_not_on_the_page_is_refused(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    refused = [
        s.post(s.person.url, "confirm", fields={"decline-1": "decline"})[0],
        s.post(s.person.url, "confirm", fields={"decline-0": "yes"})[0],
    ]
    assert refused == [400, 400]
    assert answer_files(s, brief.project_id) == []


async def test_a_store_refusal_leaves_the_page_open_for_a_retry(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    real = page.append_answer
    calls: list[PageAnswer] = []

    def once_busy(projects: Path, project: ProjectId, answer: PageAnswer) -> bool:
        calls.append(answer)
        if len(calls) == 1:
            raise ProjectBusy(f"project {project} is being answered concurrently; try again")
        return real(projects, project, answer)

    monkeypatch.setattr(page, "append_answer", once_busy)
    first = s.post(s.person.url, "confirm")[0]
    retried = [s.get(s.person.url)[0], s.post(s.person.url, "confirm")[0]]
    assert (first, retried) == (500, [200, 200])
    assert len(answer_files(s, brief.project_id)) == 1
    assert [i["outcome"] for i in (await s.ask(brief))["items"]] == ["confirmed"]


async def test_concurrent_posts_on_one_token_write_one_answer(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    url = s.person.url

    def confirm(_: int) -> int:
        return s.post(url, "confirm")[0]

    with ThreadPoolExecutor(max_workers=25) as pool:
        statuses = list(pool.map(confirm, range(25)))
    assert statuses.count(200) == 1
    assert set(statuses) <= {200, 403, 409}
    assert len(answer_files(s, brief.project_id)) == 1
