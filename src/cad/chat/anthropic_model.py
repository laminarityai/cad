"""The Anthropic Messages API behind the `Model` seam.

The client is built on the first reply and reads the key from the environment it was given. The
key is never logged, never part of an error, and never sent to a tool.

The model may search the web with the API's own web search tool, at most `CAD_WEB_SEARCHES` times
in a turn (5 when unset, none when 0). A search and its result come back as blocks the API ran
itself, and each goes back unchanged on every later step.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, cast

import anthropic
from anthropic.types import (
    CacheControlEphemeralParam,
    ContentBlock,
    ContentBlockParam,
    MessageParam,
    ToolParam,
    ToolUnionParam,
    WebSearchTool20250305Param,
)
from anthropic.types.tool_result_block_param import (
    Content,
)

from cad.chat.guidance import CHAT_WEB_SEARCH
from cad.chat.model import (
    Block,
    Message,
    ModelUnavailable,
    ServerBlock,
    Text,
    ToolResult,
    ToolSpec,
    ToolUse,
)

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

KEY_VARIABLE: Final = "ANTHROPIC_API_KEY"
MAX_TOKENS: Final = 8192
TIMEOUT_SECONDS: Final = 120.0
IMAGE_TYPES: Final[dict[str, Literal["image/png", "image/jpeg"]]] = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
}
CACHED: Final[CacheControlEphemeralParam] = {"type": "ephemeral"}
SEARCHES_VARIABLE: Final = "CAD_WEB_SEARCHES"
SEARCHES: Final = 5
MAX_PAUSES: Final = 3
SERVER_BLOCKS: Final = frozenset({"server_tool_use", "web_search_tool_result"})

_LOG = logging.getLogger(__name__)


@dataclass
class AnthropicModel:
    model: str
    environ: Mapping[str, str]
    _client: "AsyncAnthropic | None" = field(default=None, init=False, repr=False)

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        searches = _searches(self.environ)
        if searches:
            system = f"{system}\n\n{CHAT_WEB_SEARCH.format(searches=searches)}"
        sent = [_param(one) for one in messages]
        content: list[ContentBlock] = []
        for _ in range(MAX_PAUSES + 1):
            paused: list[MessageParam] = [{"role": "assistant", "content": _sent_back(content)}]
            response = await self._create(
                system, [*sent, *(paused if content else [])], _tools(tools, searches)
            )
            content.extend(response.content)
            if response.stop_reason != "pause_turn":
                break
        else:
            raise ModelUnavailable("the model's web search paused too often, so this turn stopped")
        return Message(role="assistant", blocks=_blocks(content))

    async def _create(
        self, system: str, messages: list[MessageParam], tools: list[ToolUnionParam]
    ) -> anthropic.types.Message:
        client = self._open()
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                tools=tools,
                cache_control=CACHED,
            )
        except anthropic.APIStatusError as error:
            raise ModelUnavailable(
                f"the model answered with HTTP {error.status_code}, so this turn stopped"
            ) from error
        except anthropic.APIConnectionError as error:
            raise ModelUnavailable(
                "the model could not be reached, so this turn stopped"
            ) from error
        usage = response.usage
        _LOG.info(
            "model usage: input %d, cache read %d, cache write %d, output %d, web searches %d",
            usage.input_tokens,
            usage.cache_read_input_tokens or 0,
            usage.cache_creation_input_tokens or 0,
            usage.output_tokens,
            usage.server_tool_use.web_search_requests if usage.server_tool_use else 0,
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ModelUnavailable(f"the model stopped with {response.stop_reason}")
        return response

    def _open(self) -> "AsyncAnthropic":
        if self._client is None:
            key = self.environ.get(KEY_VARIABLE, "").strip()
            if not key:
                raise ModelUnavailable(f"the server has no {KEY_VARIABLE}, so the agent cannot run")
            self._client = anthropic.AsyncAnthropic(api_key=key, timeout=TIMEOUT_SECONDS)
        return self._client


def _object(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in cast("dict[object, Any]", raw).items()}


def _searches(environ: Mapping[str, str]) -> int:
    raw = environ.get(SEARCHES_VARIABLE, "").strip()
    return int(raw) if raw.isdigit() else SEARCHES


def _tools(specs: Sequence[ToolSpec], searches: int) -> list[ToolUnionParam]:
    """The web search tool, then ours, with a cache breakpoint after the last. The request's own
    breakpoint moves to the end of the conversation each step. This one holds the tools when the
    system text changes under them, such as when a turn stores a brief."""
    ours: list[ToolParam] = [
        {"name": one.name, "description": one.description, "input_schema": one.input_schema}
        for one in specs
    ]
    if ours:
        ours[-1]["cache_control"] = CACHED
    search: list[WebSearchTool20250305Param] = (
        [{"type": "web_search_20250305", "name": "web_search", "max_uses": searches}]
        if searches
        else []
    )
    return [*search, *ours]


def _blocks(content: Sequence[ContentBlock]) -> tuple[Block, ...]:
    """Our blocks from the API's. Text the API split at its citations is one text again, and a
    thinking block is left out."""
    blocks: list[Block] = []
    for block in content:
        if block.type == "text" and block.text:
            last = blocks[-1] if blocks else None
            if isinstance(last, Text):
                blocks[-1] = Text(text=last.text + block.text)
            else:
                blocks.append(Text(text=block.text))
        elif block.type == "tool_use":
            blocks.append(ToolUse(id=block.id, name=block.name, input=_object(block.input)))
        elif block.type in SERVER_BLOCKS:
            blocks.append(ServerBlock(raw=block.model_dump(mode="json", exclude_none=True)))
    return tuple(blocks)


def _sent_back(content: Sequence[ContentBlock]) -> list[ContentBlockParam]:
    return [
        cast(ContentBlockParam, block.model_dump(mode="json", exclude_none=True))
        for block in content
    ]


def _param(message: Message) -> MessageParam:
    content: list[ContentBlockParam] = []
    for block in message.blocks:
        match block:
            case ServerBlock():
                content.append(cast(ContentBlockParam, block.raw))
            case Text():
                content.append({"type": "text", "text": block.text})
            case ToolUse():
                content.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
            case ToolResult():
                content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.call_id,
                        "content": _result_content(block),
                        "is_error": block.is_error,
                    }
                )
    return {"role": message.role, "content": content}


def _result_content(block: ToolResult) -> str | list[Content]:
    """A result with files attaches each after the text: a PDF as a document, an image as an
    image."""
    if not block.media:
        return block.text
    content: list[Content] = [{"type": "text", "text": block.text}]
    for one in block.media:
        if one.media_type == "application/pdf":
            content.append(
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": one.data},
                }
            )
        elif one.media_type in IMAGE_TYPES:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": IMAGE_TYPES[one.media_type],
                        "data": one.data,
                    },
                }
            )
    return content
