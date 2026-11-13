from types import SimpleNamespace
from typing import Any

import pytest

from cad.chat.anthropic_model import AnthropicModel
from cad.chat.model import Message, Text, ToolSpec

pytestmark = pytest.mark.anyio

SPECS = (
    ToolSpec(name="create_brief", description="Store the brief.", input_schema={"type": "object"}),
    ToolSpec(name="build_variant", description="Build one.", input_schema={"type": "object"}),
)


class Messages:
    def __init__(self) -> None:
        self.sent: dict[str, Any] = {}

    async def create(self, **request: Any) -> object:
        self.sent = request
        usage = SimpleNamespace(
            input_tokens=12,
            cache_read_input_tokens=3000,
            cache_creation_input_tokens=40,
            output_tokens=5,
        )
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Done.")],
            usage=usage,
        )


async def test_the_request_caches_the_tools_and_the_conversation_so_far() -> None:
    model = AnthropicModel(model="claude-sonnet-5-5", environ={})
    messages = Messages()
    model._client = SimpleNamespace(messages=messages)  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage]
    said = await model.reply("system", [Message(role="user", blocks=(Text(text="a block"),))], SPECS)
    assert said.blocks == (Text(text="Done."),)
    assert messages.sent["cache_control"] == {"type": "ephemeral"}
    first, last = messages.sent["tools"]
    assert "cache_control" not in first
    assert last["cache_control"] == {"type": "ephemeral"}
