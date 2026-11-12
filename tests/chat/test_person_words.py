import json
from typing import Any

import pytest

from cad.accounts.principal import AccountId
from cad.briefs import store
from cad.briefs.origins import quoted as quote_of
from cad.chat.model import Model
from tests.support.chat import ALICE, TEXT, Chat, call, script, step
from tests.support.rows import UNDER_150

pytestmark = pytest.mark.anyio

LATER = "and it has to stay under 120 g"
UNDER_120 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 120, "unit": "g"}},
    "quote": "under 120 g",
}
BRIEF_ID = "${create_brief.brief_id}"


@pytest.fixture
def model() -> Model:
    return script(
        step("Storing it.", call("create_brief", text="a plate, light")),
        step("Storing it.", call("create_brief")),
        step(
            "Proposing.", call("propose_requirements", brief_id=BRIEF_ID, requirements=[UNDER_150])
        ),
        step("Proposed."),
        step(
            "Proposing.",
            call("propose_requirements", brief_id=BRIEF_ID, requirements=[UNDER_150, UNDER_120]),
        ),
        step(
            "Again.",
            call("propose_requirements", brief_id=BRIEF_ID, requirements=[UNDER_150, UNDER_120]),
        ),
        step(
            "With said.",
            call("propose_requirements", brief_id=BRIEF_ID, requirements=[UNDER_150], said=LATER),
        ),
        step("Done."),
    )


def results(events: list[Any]) -> list[tuple[bool, str]]:
    return [(one["is_error"], one["text"]) for one in events if one["kind"] == "tool_result"]


async def test_the_brief_is_the_persons_message_and_a_later_number_lands_on_it(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await chat.finish()
        await chat.say(client, cid, LATER)
        await chat.finish()
        events = await chat.events(client, cid)
    (refused, typed), (_, created), (_, first), (_, second), (_, again), (said, why) = results(
        events
    )
    assert refused, typed
    assert "in chat pass no text" in typed
    brief = json.loads(created)
    assert brief["text"] == TEXT
    assert [json.loads(one)["proposal"] for one in (first, second, again)] == [1, 2, 2]
    assert {json.loads(one)["brief_id"] for one in (first, second, again)} == {brief["brief_id"]}
    assert said, why
    assert "in chat pass no said" in why
    roots = chat.tenants.of(AccountId(ALICE)).roots
    state = store.read_state(roots, brief["brief_id"])
    assert state.brief.text == f"{TEXT}\n\n{LATER}"
    quoted = [
        [quote_of(state.brief.text, r.origin)[1] for r in p.requirements] for p in state.proposals
    ]
    assert quoted == [["under 150 g"], ["under 150 g", "under 120 g"]]
