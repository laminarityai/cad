from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from anthropic.types import ServerToolUseBlock, TextBlock, ToolUseBlock, WebSearchToolResultBlock

from cad.chat.anthropic_model import SEARCHES, AnthropicModel
from cad.chat.log import Page, WebFound, WebSearched, messages_of, web_event
from cad.chat.model import Message, ServerBlock, Text, ToolSpec, ToolUse

pytestmark = pytest.mark.anyio

SPECS = (
    ToolSpec(name="create_brief", description="Store the brief.", input_schema={"type": "object"}),
    ToolSpec(name="build_variant", description="Build one.", input_schema={"type": "object"}),
)


USAGE = SimpleNamespace(
    input_tokens=12,
    cache_read_input_tokens=3000,
    cache_creation_input_tokens=40,
    output_tokens=5,
    server_tool_use=None,
)
SEARCH = ServerToolUseBlock(
    type="server_tool_use", id="srvtoolu_1", name="web_search", input={"query": "pump impeller"}
)
FOUND = WebSearchToolResultBlock.model_validate(
    {
        "type": "web_search_tool_result",
        "tool_use_id": "srvtoolu_1",
        "content": [
            {
                "type": "web_search_result",
                "url": "https://example.com/impellers",
                "title": "Impellers",
                "encrypted_content": "Eq0secret",
                "page_age": None,
            }
        ],
    }
)


class Messages:
    def __init__(self, *replies: tuple[str, Sequence[object]]) -> None:
        self.replies = list(replies) or [("end_turn", [TextBlock(type="text", text="Done.")])]
        self.requests: list[dict[str, Any]] = []

    @property
    def sent(self) -> dict[str, Any]:
        return self.requests[-1]

    async def create(self, **request: Any) -> object:
        self.requests.append(request)
        stop_reason, content = self.replies.pop(0)
        return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=USAGE)


def a_model(messages: Messages, environ: dict[str, str] | None = None) -> AnthropicModel:
    model = AnthropicModel(model="claude-haiku-5-5", environ=environ or {})
    model._client = SimpleNamespace(messages=messages)  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage]
    return model


ASKED = [Message(role="user", blocks=(Text(text="an impeller"),))]


async def test_the_request_caches_the_tools_and_the_conversation_so_far() -> None:
    messages = Messages()
    said = await a_model(messages).reply("system", ASKED, SPECS, 0)
    assert said.blocks == (Text(text="Done."),)
    assert messages.sent["cache_control"] == {"type": "ephemeral"}
    *before, last = messages.sent["tools"]
    assert all("cache_control" not in one for one in before)
    assert last["cache_control"] == {"type": "ephemeral"}


async def test_the_model_may_search_the_web_a_capped_number_of_times_or_not_at_all() -> None:
    on, off = Messages(), Messages()
    await a_model(on).reply("system", ASKED, SPECS, 0)
    await a_model(off, {"CAD_WEB_SEARCHES": "0"}).reply("system", ASKED, SPECS, 0)
    search = {"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCHES}
    assert on.sent["tools"][0] == search
    assert "web_search" in on.sent["system"]
    assert [one["name"] for one in off.sent["tools"]] == ["create_brief", "build_variant"]
    assert off.sent["system"] == "system"


async def test_a_search_comes_back_as_the_apis_own_blocks_and_goes_back_unchanged() -> None:
    cited = [TextBlock(type="text", text="Impellers are "), TextBlock(type="text", text="cast.")]
    build = ToolUseBlock(type="tool_use", id="toolu_1", name="create_brief", input={})
    messages = Messages(("tool_use", [SEARCH, FOUND, *cited, build]), ("end_turn", []))
    model = a_model(messages)
    said = await model.reply("system", ASKED, SPECS, 0)
    raw_search, raw_found = (
        SEARCH.model_dump(exclude_none=True),
        FOUND.model_dump(exclude_none=True),
    )
    assert said.blocks == (
        ServerBlock(raw=raw_search),
        ServerBlock(raw=raw_found),
        Text(text="Impellers are cast."),
        ToolUse(id="toolu_1", name="create_brief", input={}),
    )
    assert raw_found["content"][0]["encrypted_content"] == "Eq0secret"
    await model.reply("system", [*ASKED, said], SPECS, 0)
    assert messages.sent["messages"][1]["content"][:2] == [raw_search, raw_found]


async def test_a_paused_search_is_sent_back_and_its_continuation_joins_the_same_reply() -> None:
    messages = Messages(
        ("pause_turn", [SEARCH]), ("end_turn", [FOUND, TextBlock(type="text", text="Done.")])
    )
    said = await a_model(messages).reply("system", ASKED, SPECS, 0)
    first, second = messages.requests
    assert first["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "an impeller"}]}
    ]
    assert second["messages"][1] == {
        "role": "assistant",
        "content": [SEARCH.model_dump(exclude_none=True)],
    }
    assert [type(one) for one in said.blocks] == [ServerBlock, ServerBlock, Text]


async def test_a_turn_that_spent_its_searches_is_offered_no_search_and_a_pause_ends_there() -> None:
    spent = Messages()
    await a_model(spent).reply("system", ASKED, SPECS, SEARCHES)
    assert [one["name"] for one in spent.sent["tools"]] == ["create_brief", "build_variant"]
    paused = Messages(("pause_turn", [SEARCH]))
    said = await a_model(paused).reply("system", ASKED, SPECS, SEARCHES - 1)
    assert paused.sent["tools"][0]["max_uses"] == 1
    assert len(paused.requests) == 1
    assert said.blocks == (ServerBlock(raw=SEARCH.model_dump(exclude_none=True)),)


def test_the_transcript_keeps_a_search_and_drops_one_that_never_returned() -> None:
    raw_search, raw_found = (
        SEARCH.model_dump(exclude_none=True),
        FOUND.model_dump(exclude_none=True),
    )
    searches_spent = web_event(ServerBlock(raw=raw_search))
    found = web_event(ServerBlock(raw=raw_found))
    assert searches_spent is not None and found is not None
    assert searches_spent == WebSearched(
        call_id="srvtoolu_1", query="pump impeller", raw=raw_search
    )
    assert found == WebFound(
        call_id="srvtoolu_1",
        pages=(Page(title="Impellers", url="https://example.com/impellers"),),
        raw=raw_found,
    )
    dead = WebSearched(call_id="srvtoolu_2", query="lost", raw={**raw_search, "id": "srvtoolu_2"})
    [message] = messages_of([searches_spent, found, dead])
    assert message.blocks == (ServerBlock(raw=raw_search), ServerBlock(raw=raw_found))
    failed = web_event(
        ServerBlock(
            raw={
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_3",
                "content": {
                    "type": "web_search_tool_result_error",
                    "error_code": "max_uses_exceeded",
                },
            }
        )
    )
    assert isinstance(failed, WebFound) and failed.error == "max_uses_exceeded"
