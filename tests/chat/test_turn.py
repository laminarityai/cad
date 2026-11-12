import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.chat.model import Message, Model, ModelUnavailable, ToolSpec
from cad.chat.turn import CLIENT_ID, agent_token
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.registry import OPERATIONS
from cad.operations.tools import agent_operations
from tests.support.chat import ALICE, JSON, Chat, call, script, step

pytestmark = pytest.mark.anyio


@dataclass
class Recording:
    inner: Model
    systems: list[str] = field(default_factory=list[str])
    offered: list[list[str]] = field(default_factory=list[list[str]])

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        self.systems.append(system)
        self.offered.append([one.name for one in tools])
        return await self.inner.reply(system, messages, tools)


@dataclass
class Failing:
    error: Exception

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        del system, messages, tools
        raise self.error


def test_the_token_is_built_from_the_verified_session_and_names_one_conversation() -> None:
    person = PersonSession(account=AccountId(ALICE), session_id="sess_1")
    one = agent_token(person, ConversationId("c1"))
    other = agent_token(person, ConversationId("c1"))
    assert (one.account, one.conversation, one.client_id) == (ALICE, "c1", CLIENT_ID)
    assert one.token_id != other.token_id


@pytest.fixture
def recording() -> Recording:
    return Recording(
        script(
            step("Looking.", call("create_brief")),
            step("Starting.", call("auto_start", brief_id="b" * 16)),
            step("It was refused."),
        )
    )


@pytest.fixture
def model(recording: Recording) -> Model:
    return recording


async def test_a_refused_tool_is_a_result_the_agent_reads_not_a_failed_turn(
    chat: Chat, recording: Recording
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "make a hook")
        await chat.finish()
        events = await chat.events(client, cid)
    results = [one for one in events if one["kind"] == "tool_result"]
    assert [one["is_error"] for one in results] == [False, True]
    assert "this caller's mode is design" in results[1]["text"]
    assert [one["kind"] for one in events][-2:] == ["agent", "turn_ended"]
    assert "turn_failed" not in {one["kind"] for one in events}
    assert len(recording.offered) == 3


async def test_the_agent_is_offered_the_agent_tools_and_nothing_a_person_alone_may_use(
    chat: Chat, recording: Recording
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "make a hook")
        await chat.finish()
    agent = {one.name for one in agent_operations(OPERATIONS)}
    assert set(recording.offered[0]) == agent
    assert {"auto_start", "auto_revise", "auto_ask", "build_variant"} <= agent
    assert {"auto_stop", "set_mode"}.isdisjoint(agent)
    assert "Design mode" in recording.systems[0]
    assert "Plan mode" not in recording.systems[0]


@pytest.mark.docker
async def test_a_mode_the_person_sets_reaches_the_next_message_and_the_prompt(
    chat: Chat, recording: Recording
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        tenant = chat.tenants.of(AccountId(ALICE))
        store.set_mode(tenant.roots, tenant.conversations, ConversationId(cid), Mode.DESIGN)
        await chat.say(client, cid, "make a hook")
        await chat.finish()
        events = await chat.events(client, cid)
    assert "Design mode" in recording.systems[0]
    refusals = [one["text"] for one in events if one["kind"] == "tool_result" and one["is_error"]]
    assert all("Plan mode" not in text for text in refusals)


@pytest.mark.parametrize(
    ("error", "shown"),
    [
        (ModelUnavailable("the model answered with HTTP 529"), "the model answered with HTTP 529"),
        (RuntimeError("secret detail sk-ant-xyz"), "the agent failed"),
    ],
)
async def test_a_model_that_fails_ends_the_turn_with_a_message_and_frees_the_conversation(
    chat: Chat, error: Exception, shown: str
) -> None:
    chat.app.state.chat.model = Failing(error)
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "hi")
        await chat.finish()
        events = await chat.events(client, cid)
        sent = await client.post(
            f"/v1/conversations/{cid}/messages", headers=JSON, content=json.dumps({"text": "again"})
        )
    kinds = [one["kind"] for one in events]
    assert kinds == ["user", "turn_failed", "turn_ended"]
    assert shown in events[1]["message"]
    assert "sk-ant" not in events[1]["message"]
    assert sent.status_code == 202
