import pytest

from cad.chat.model import Model
from tests.support.auto_chat import RUN, confirmed, kinds
from tests.support.chat import TEXT, Chat, call, script, step
from tests.support.rows import UNDER_150

pytestmark = pytest.mark.anyio


@pytest.fixture
def model() -> Model:
    return script(
        *confirmed(),
        step("A lid.", call("create_brief", project_id="${create_brief.project_id}")),
        step(
            "Its mass.",
            call(
                "propose_requirements",
                brief_id="${create_brief.brief_id}",
                requirements=[UNDER_150],
            ),
        ),
        step("Revising.", call("auto_revise", run_id=RUN, code="# a plate\n")),
        step("Unreachable."),
    )


async def test_the_persons_stop_report_names_a_row_proposed_on_another_brief_of_the_project(
    chat: Chat,
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(events)[-2:] == ["stop_report", "turn_ended"]
    assert events[-2]["report"] == (
        "New requirements were proposed, and only the person can confirm them: "
        "Mass at most 150 g.\nNothing was built under the run."
    )
