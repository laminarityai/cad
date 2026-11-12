"""The confirmation page says a described load case is the agent's description."""

import pytest

from tests.support.load_cases import hole_hook, shelf
from tests.support.session import Session
from tests.support.stress import WORDS, row

pytestmark = pytest.mark.anyio
NOTE = "on a load case the agent described from fixed terms"


async def page_for(s: Session, case: dict[str, object]) -> str:
    created = await s.call("create_brief", text=WORDS)
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[row(case)])
    await s.call("ask_to_confirm", project_id=created["project_id"])
    status, body = s.get(s.person.url)
    assert status == 200
    return body


async def test_the_page_marks_a_described_load_case_as_the_agents_description(s: Session) -> None:
    body = await page_for(s, shelf())
    assert NOTE in body
    assert "our team has not reviewed this load case" in body
    assert "middle of its largest flat face" in body


async def test_the_page_does_not_mark_a_reviewed_phrase(s: Session) -> None:
    body = await page_for(s, hole_hook())
    assert NOTE not in body
    assert "Decided by the fea check" in body
