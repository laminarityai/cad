import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.chat.guidance import CHAT_AUTO
from cad.chat.model import Message, Model, ModelUnavailable, ServerBlock, Text, ToolSpec, ToolUse
from cad.chat.turn import CLIENT_ID, agent_token
from cad.conversations.model import ConversationId
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
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        searches_spent: int,
    ) -> Message:
        self.systems.append(system)
        self.offered.append([one.name for one in tools])
        return await self.inner.reply(system, messages, tools, searches_spent)


@dataclass
class Failing:
    error: Exception

    async def reply(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        searches_spent: int,
    ) -> Message:
        del system, messages, tools, searches_spent
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
    assert "UnknownBrief: no brief bbbbbbbbbbbbbbbb is stored" in results[1]["text"]
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
    assert "auto_stop" not in agent
    assert CHAT_AUTO in recording.systems[0]
    assert all(f"{one} mode" not in recording.systems[0] for one in ("Plan", "Design", "Auto"))


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


@dataclass
class Searching:
    searches_spent: list[int] = field(default_factory=list[int])

    async def reply(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        searches_spent: int,
    ) -> Message:
        del system, messages, tools
        self.searches_spent.append(searches_spent)
        if len(self.searches_spent) == 3:
            return Message(role="assistant", blocks=(Text(text="Done."),))
        step = len(self.searches_spent)
        search = {"type": "server_tool_use", "id": f"srvtoolu_{step}", "name": "web_search"}
        call = ToolUse(id=f"toolu_{step}", name="list_materials", input={})
        return Message(role="assistant", blocks=(ServerBlock(raw=search), call))


@pytest.mark.parametrize("model", [Searching()])
async def test_each_step_is_told_how_many_searches_the_turn_has_run(
    chat: Chat, model: Searching
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "make a hook")
        await chat.finish()
    assert model.searches_spent == [0, 1, 2]
