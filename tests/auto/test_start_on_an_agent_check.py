"""Auto may start on a requirement that only an approved agent-written check decides (ADR-0011)."""

import pytest

from cad.agent_checks import probes
from cad.agent_checks.gates import Shaped
from cad.agent_checks.model import CheckDraft
from cad.auto.model import Running
from cad.context_parts.model import Outcome
from tests.support.agent_checks import answer, write
from tests.support.auto_session import PLA_CHOICE, Session

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def no_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def passes(draft: CheckDraft, shaped: Shaped) -> None:
        return None

    monkeypatch.setattr(probes, "repeat_and_turn", passes)


async def test_a_confirmed_agent_limit_with_an_approved_check_starts_a_run(s: Session) -> None:
    brief_id, stored = write(s.roots)
    answer(s.roots, brief_id, stored, "confirmed")
    run = await s.start(brief_id=brief_id, **PLA_CHOICE)
    assert isinstance(run.state, Running)
    assert run.state.start.brief_id == brief_id


@pytest.mark.parametrize("check", ["declined", "waiting"])
async def test_an_agent_limit_whose_check_the_person_did_not_approve_decides_nothing(
    s: Session, check: Outcome
) -> None:
    brief_id, stored = write(s.roots)
    answer(s.roots, brief_id, stored, check)
    text = await s.refusal("auto_start", brief_id=brief_id, **PLA_CHOICE)
    assert "an agent-written check the person approved decides" in text, text
