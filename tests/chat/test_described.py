import pytest
from pydantic import TypeAdapter

from cad.chat.log import Event
from cad.chat.model import Model
from cad.operations.outside import HAND_DESCRIBED, ConversationCreated, MessageSent
from tests.chat.support import JSON, Chat, script, step

pytestmark = pytest.mark.anyio

STATUS = {one.name: one.status for one in HAND_DESCRIBED}


@pytest.fixture
def model() -> Model:
    return script(step("Hello."))


async def test_what_the_chat_routes_send_is_what_the_web_page_is_told(chat: Chat) -> None:
    async with chat.client() as client:
        made = await client.post("/v1/conversations", headers=JSON, content=b"{}")
        created = ConversationCreated.model_validate(made.json())
        sent = await client.post(
            f"/v1/conversations/{created.conversation_id}/messages",
            headers=JSON,
            content='{"text": "hello"}',
        )
        await chat.finish()
        events = await chat.events(client, created.conversation_id)
    MessageSent.model_validate(sent.json())
    assert made.status_code == STATUS["create_conversation"]
    assert sent.status_code == STATUS["message"]
    sent_as_data = [{key: value for key, value in one.items() if key != "seq"} for one in events]
    parsed = [TypeAdapter(Event).validate_python(one) for one in sent_as_data]
    assert [one.kind for one in parsed] == ["user", "agent", "turn_ended"]
