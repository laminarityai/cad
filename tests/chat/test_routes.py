import json

import pytest

from cad.chat.model import Model
from tests.chat.support import ALICE, BOB, JSON, Chat, call, script, step

pytestmark = pytest.mark.anyio


@pytest.fixture
def model() -> Model:
    return script(
        step("Storing it.", call("create_brief", text="a hook")),
        step("Stored."),
    )


async def test_a_message_runs_one_turn_and_the_stream_replays_it(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        assert await chat.say(client, cid, "make a hook") == 1
        await chat.finish()
        events = await chat.events(client, cid)
    assert [one["kind"] for one in events] == [
        "user",
        "agent",
        "tool_call",
        "tool_result",
        "agent",
        "turn_ended",
    ]
    assert [one["seq"] for one in events] == [1, 2, 3, 4, 5, 6]
    assert json.loads(events[3]["text"])["brief_id"]


async def test_a_stream_resumes_after_the_last_event_it_saw(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "make a hook")
        await chat.finish()
        later = await chat.events(client, cid, after=4)
        resumed = await client.get(
            f"/v1/conversations/{cid}/stream",
            params={"follow": "false"},
            headers={"Last-Event-ID": "5"},
        )
    assert [one["seq"] for one in later] == [5, 6]
    assert resumed.text.startswith("id: 6\n")


async def test_a_second_message_while_a_turn_runs_is_409(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "first")
        second = await client.post(
            f"/v1/conversations/{cid}/messages", headers=JSON, content='{"text": "second"}'
        )
        await chat.finish()
        again = await chat.say(client, cid, "third")
    assert second.status_code == 409
    assert again > 6


async def test_a_message_that_is_not_json_is_415_and_starts_nothing(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        form = await client.post(
            f"/v1/conversations/{cid}/messages",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content="text=hi",
        )
        plain = await client.post(f"/v1/conversations/{cid}/messages", content='{"text": "hi"}')
        events = await chat.events(client, cid)
    assert (form.status_code, plain.status_code, events) == (415, 415, [])


async def test_an_empty_or_unknown_field_is_422(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        bodies = ['{"text": ""}', '{"text": "hi", "mode": "auto"}', "not json"]
        sent = [
            await client.post(f"/v1/conversations/{cid}/messages", headers=JSON, content=body)
            for body in bodies
        ]
    assert [one.status_code for one in sent] == [422, 422, 422]


async def test_another_accounts_conversation_is_404_for_every_route(chat: Chat) -> None:
    async with chat.client(ALICE) as alice, chat.client(BOB) as bob:
        cid = await chat.conversation(alice)
        await chat.say(alice, cid, "make a hook")
        await chat.finish()
        sent = await bob.post(
            f"/v1/conversations/{cid}/messages", headers=JSON, content='{"text": "hi"}'
        )
        streamed = await bob.get(f"/v1/conversations/{cid}/stream", params={"follow": "false"})
        mine = await alice.get(f"/v1/conversations/{cid}/stream", params={"follow": "false"})
    assert (sent.status_code, streamed.status_code, mine.status_code) == (404, 404, 200)
    assert "make a hook" not in sent.text + streamed.text


async def test_an_unknown_conversation_is_404_and_a_malformed_id_is_422(chat: Chat) -> None:
    async with chat.client() as client:
        unknown = await client.get("/v1/conversations/c_0000000000000000/stream")
        malformed = await client.get("/v1/conversations/a b/stream")
    assert (unknown.status_code, malformed.status_code) == (404, 422)


async def test_an_agent_token_and_no_token_get_401_on_every_chat_route(chat: Chat) -> None:
    agent = chat.local.mint_agent(ALICE)
    async with chat.client(None) as anonymous, chat.client(None) as bearer:
        bearer.headers["Authorization"] = f"Bearer {agent}"
        for client in (anonymous, bearer):
            made = await client.post("/v1/conversations", headers=JSON, content=b"{}")
            sent = await client.post(
                "/v1/conversations/c1/messages", headers=JSON, content='{"text": "hi"}'
            )
            streamed = await client.get("/v1/conversations/c1/stream")
            assert (made.status_code, sent.status_code, streamed.status_code) == (401, 401, 401)
