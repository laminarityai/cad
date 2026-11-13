"""The Anthropic Messages API behind the `Model` seam.

The client is built on the first reply and reads the key from the environment it was given. The
key is never logged, never part of an error, and never sent to a tool.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal, cast

import anthropic
from anthropic.types import (
    CacheControlEphemeralParam,
    MessageParam,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)
from anthropic.types.tool_result_block_param import (
    Content,
)

from cad.chat.model import (
    Block,
    Message,
    ModelUnavailable,
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

_LOG = logging.getLogger(__name__)


@dataclass
class AnthropicModel:
    model: str
    environ: Mapping[str, str]
    _client: "AsyncAnthropic | None" = field(default=None, init=False, repr=False)

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        client = self._open()
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[_param(one) for one in messages],
                tools=_tools(tools),
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
            "model usage: input %d, cache read %d, cache write %d, output %d",
            usage.input_tokens,
            usage.cache_read_input_tokens or 0,
            usage.cache_creation_input_tokens or 0,
            usage.output_tokens,
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ModelUnavailable(f"the model stopped with {response.stop_reason}")
        blocks: list[Block] = []
        for block in response.content:
            if block.type == "text" and block.text:
                blocks.append(Text(text=block.text))
            elif block.type == "tool_use":
                blocks.append(ToolUse(id=block.id, name=block.name, input=_object(block.input)))
        return Message(role="assistant", blocks=tuple(blocks))

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


def _tools(specs: Sequence[ToolSpec]) -> list[ToolParam]:
    """The tools, with a cache breakpoint after the last. The request's own breakpoint moves to
    the end of the conversation each step. This one holds the tools when the system text changes
    under them, such as when a turn stores a brief."""
    tools: list[ToolParam] = [
        {"name": one.name, "description": one.description, "input_schema": one.input_schema}
        for one in specs
    ]
    if tools:
        tools[-1]["cache_control"] = CACHED
    return tools


def _param(message: Message) -> MessageParam:
    content: list[TextBlockParam | ToolUseBlockParam | ToolResultBlockParam] = []
    for block in message.blocks:
        match block:
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
