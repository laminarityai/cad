from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx2
import pytest

from cad.chat.model import HEARD, Message, Text, ToolSpec
from tests.support.chat import Chat

pytestmark = pytest.mark.anyio


@dataclass
class Typing:
    """A model that streams its reply in two pieces and reads the page's stream between them."""

    client: httpx2.AsyncClient | None = None
    cid: str = ""
    seen: list[str] = field(default_factory=list[str])

    async def reply(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        searches_spent: int,
    ) -> Message:
        del system, messages, tools, searches_spent
        heard = HEARD.get()
        assert heard is not None and self.client is not None
        for piece in ("Built ", "3 options."):
            heard(piece)
            streamed = await self.client.get(
                f"/v1/conversations/{self.cid}/stream", params={"follow": "false"}
            )
            self.seen.append(streamed.text.split("\n\n")[-2])
        return Message(role="assistant", blocks=(Text(text="Built 3 options."),))


@pytest.mark.parametrize("model", [Typing()])
async def test_the_page_reads_the_reply_as_it_arrives_and_then_only_the_stored_reply(
    chat: Chat, model: Typing
) -> None:
    async with chat.client() as client:
        model.client = client
        model.cid = await chat.conversation(client)
        await chat.say(client, model.cid, "a hook")
        await chat.finish()
        after = await client.get(
            f"/v1/conversations/{model.cid}/stream", params={"follow": "false"}
        )
    assert model.seen == [
        'event: agent_partial\ndata: {"text":"Built "}',
        'event: agent_partial\ndata: {"text":"Built 3 options."}',
    ]
    assert "agent_partial" not in after.text
    assert 'event: agent\ndata: {"kind":"agent","text":"Built 3 options."}' in after.text
