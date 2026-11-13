from typing import Any

import pytest

from cad.accounts.principal import AccountId
from cad.chat.log import Channel, ToolCalled, UserSaid, transcript_path
from cad.conversations.model import ConversationId
from tests.support.chat import ALICE, Chat

pytestmark = pytest.mark.anyio


def died_mid_turn(chat: Chat, cid: str) -> None:
    """What a server that died during a build leaves: the message and a call, and no end."""
    conversations = chat.tenants.of(AccountId(ALICE)).conversations
    held = Channel(transcript_path(conversations, ConversationId(cid)))
    held.append(UserSaid(text="a hook"))
    held.append(ToolCalled(call_id="a", name="build_variant", input={}))


def tail(events: list[Any]) -> list[str]:
    return [one["kind"] for one in events][-2:]


async def test_a_turn_a_restart_cut_off_ends_and_says_so_when_the_conversation_opens(
    chat: Chat, restarted: Chat
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
    died_mid_turn(chat, cid)
    async with restarted.client() as client:
        events = await restarted.events(client, cid)
        await restarted.finish()
        again = await restarted.events(client, cid)
    assert tail(events) == ["turn_failed", "turn_ended"]
    assert "Send a message" in events[-2]["message"]
    assert again == events
