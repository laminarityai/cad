import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from cad.accounts.principal import AccountId
from cad.chat.model import Message, Model, ToolSpec
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.briefs import BriefCreated, CreateBriefInput, create_brief
from tests.chat.support import ALICE, BOB, JSON, TEXT, Chat, script, step

pytestmark = pytest.mark.anyio


@dataclass
class Recording:
    inner: Model
    systems: list[str] = field(default_factory=list[str])

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        self.systems.append(system)
        return await self.inner.reply(system, messages, tools)


@pytest.fixture
def recording() -> Recording:
    return Recording(script(step("Looking.")))


@pytest.fixture
def model(recording: Recording) -> Model:
    return recording


def brief(chat: Chat, account: str = ALICE) -> BriefCreated:
    return create_brief(chat.tenants.of(AccountId(account)), CreateBriefInput(text=TEXT))


async def test_a_conversation_started_on_a_brief_names_it_to_the_agent(
    chat: Chat, recording: Recording
) -> None:
    made = brief(chat)
    body = json.dumps({"project_id": made.project_id, "brief_id": made.brief_id})
    async with chat.client() as client:
        started = await client.post("/v1/conversations", headers=JSON, content=body)
        cid = started.json()["conversation_id"]
        await chat.say(client, cid, "make the side walls of slot 1 thicker")
        await chat.finish()
        read = await client.get(f"/v1/conversations/{cid}")
    assert started.status_code == 201, started.text
    assert read.json() == {
        "conversation_id": cid,
        "mode": "plan",
        "auto_run": None,
        "project_id": made.project_id,
        "brief_id": made.brief_id,
        "run": None,
    }
    system = recording.systems[0]
    assert f"project {made.project_id}, brief {made.brief_id}" in system
    assert all(tool in system for tool in ("variant_set", "variant_code", "score_variant"))


async def test_a_conversation_without_a_brief_names_none(chat: Chat, recording: Recording) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "hi")
        await chat.finish()
    assert "started this conversation on project" not in recording.systems[0]


async def test_a_brief_outside_the_account_or_the_project_starts_no_conversation(
    chat: Chat,
) -> None:
    alices = brief(chat)
    bobs = brief(chat, BOB)
    asks = [
        {"project_id": bobs.project_id, "brief_id": bobs.brief_id},
        {"project_id": alices.project_id, "brief_id": alices.brief_id},
        {"project_id": bobs.project_id, "brief_id": alices.brief_id},
        {"brief_id": alices.brief_id},
        {"project_id": alices.project_id, "brief_id": alices.brief_id, "slot": 1},
    ]
    async with chat.client(BOB) as client:
        answers = [
            (await client.post("/v1/conversations", headers=JSON, content=json.dumps(one)))
            for one in asks
        ]
    assert [one.status_code for one in answers] == [201, 404, 404, 422, 422]
    assert not list(chat.tenants.of(AccountId(ALICE)).conversations.glob("*.json"))


async def test_the_read_answers_only_the_account_that_holds_the_conversation(
    chat: Chat,
) -> None:
    async with chat.client() as alice, chat.client(BOB) as bob, chat.client(None) as nobody:
        cid = await chat.conversation(alice)
        store.set_mode(chat.tenants.of(AccountId(ALICE)), ConversationId(cid), Mode.DESIGN)
        own = await alice.get(f"/v1/conversations/{cid}")
        other = await bob.get(f"/v1/conversations/{cid}")
        unknown = await alice.get("/v1/conversations/c_0000000000000000")
        anonymous = await nobody.get(f"/v1/conversations/{cid}")
    assert own.json()["mode"] == "design"
    assert (other.status_code, unknown.status_code, anonymous.status_code) == (404, 404, 401)
    assert not list(chat.tenants.of(AccountId(BOB)).conversations.glob("*.json"))
