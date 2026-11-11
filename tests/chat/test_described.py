import pytest

from cad.chat.model import Model
from tests.support.bodies import check
from tests.support.chat import JSON, Chat, script, step

pytestmark = pytest.mark.anyio

CONVERSATIONS = "/v1/conversations"
MESSAGES = "/v1/conversations/{conversation_id}/messages"
STREAM = "/v1/conversations/{conversation_id}/stream"


@pytest.fixture
def model() -> Model:
    return script(step("Hello."))


async def test_what_the_chat_routes_send_is_what_the_web_page_is_told(chat: Chat) -> None:
    async with chat.client() as client:
        made = await client.post(CONVERSATIONS, headers=JSON, content=b"{}")
        cid = made.json()["conversation_id"]
        sent = await client.post(
            MESSAGES.format(conversation_id=cid), headers=JSON, content='{"text": "hello"}'
        )
        await chat.finish()
        events = await chat.events(client, cid)
        resumed = await chat.events(client, cid, after=events[0]["seq"])
    check("POST", CONVERSATIONS, made.status_code, made.json())
    check("POST", MESSAGES, sent.status_code, sent.json())
    for one in events:
        check("GET", STREAM, 200, {key: value for key, value in one.items() if key != "seq"})
    assert [one["kind"] for one in events] == ["user", "agent", "turn_ended"]
    assert resumed == events[1:]
