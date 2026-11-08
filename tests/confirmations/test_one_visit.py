from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cad.confirmations import answers, page
from cad.records import signed
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


async def test_a_single_item_page_shows_no_decline_box_and_accepts_none(s: Session) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    assert 'name="decline-' not in s.get(s.person.url)[1]
    assert s.post(s.person.url, "confirm", fields={"decline-0": "decline"})[0] == 400
    assert answer_files(s, brief.project_id) == []
    assert s.post(s.person.url, "confirm")[0] == 200


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


async def test_an_unwritable_answers_directory_leaves_the_page_open_for_a_retry(
    s: Session, caplog: pytest.LogCaptureFixture
) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    directory = s.roots.projects / brief.project_id / answers.ANSWERS
    directory.mkdir(mode=0o500, parents=True)
    try:
        with caplog.at_level(logging.ERROR):
            first = s.post(s.person.url, "confirm")
    finally:
        directory.chmod(0o700)
    assert (first[0], "nothing was recorded. Try again" in first[1]) == (500, True)
    assert "could not record" in caplog.text
    assert [s.get(s.person.url)[0], s.post(s.person.url, "confirm")[0]] == [200, 200]
    assert [i["outcome"] for i in (await s.ask(brief))["items"]] == ["confirmed"]


async def test_an_unexpected_error_leaves_the_page_open_for_a_retry(
    s: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    real = page.append_answer
    calls: list[PageAnswer] = []

    def once_broken(projects: Path, project: ProjectId, answer: PageAnswer) -> bool:
        calls.append(answer)
        if len(calls) == 1:
            raise RuntimeError("an unexpected failure")
        return real(projects, project, answer)

    monkeypatch.setattr(page, "append_answer", once_broken)
    with caplog.at_level(logging.ERROR):
        first = s.post(s.person.url, "confirm")
    assert (first[0], "nothing was recorded. Try again" in first[1]) == (500, True)
    assert "RuntimeError" in caplog.text
    assert [s.get(s.person.url)[0], s.post(s.person.url, "confirm")[0]] == [200, 200]
    assert len(answer_files(s, brief.project_id)) == 1


async def test_an_answer_whose_link_is_written_is_recorded_even_if_cleanup_fails(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    brief = await s.proposed(s.rows.under_150)
    await s.ask(brief)
    real_unlink = Path.unlink

    def stuck(path: Path, missing_ok: bool = False) -> None:
        if path.name.startswith(".pending-"):
            raise PermissionError("the temporary file cannot be removed")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", stuck)
    assert s.post(s.person.url, "confirm")[0] == 200
    assert [s.get(s.person.url)[0], s.post(s.person.url, "confirm")[0]] == [403, 403]
    slots = [f.name for f in answer_files(s, brief.project_id) if not f.name.startswith(".")]
    assert slots == [signed.slot_file(1)]
    assert [i["outcome"] for i in (await s.ask(brief))["items"]] == ["confirmed"]
