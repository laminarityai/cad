"""The seam between a chat turn and the language model.

A turn hands the model the conversation so far and the tools the server lists, and gets one
assistant message back. The server's tool list is the only tool list, so the model is the one
part of a turn that can be swapped: the Anthropic adapter in production, a scripted double in
tests and evals. `CAD_CHAT_MODEL` selects it.
"""

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL: Final = "claude-sonnet-5-5"
MODEL_VARIABLE: Final = "CAD_CHAT_MODEL"
SCRIPTED_PREFIX: Final = "scripted:"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Text(_Frozen):
    kind: Literal["text"] = "text"
    text: str


class ToolUse(_Frozen):
    kind: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResult(_Frozen):
    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    text: str
    is_error: bool = False


type Block = Annotated[Text | ToolUse | ToolResult, Field(discriminator="kind")]


class Message(_Frozen):
    role: Literal["user", "assistant"]
    blocks: tuple[Block, ...]

    @property
    def calls(self) -> tuple[ToolUse, ...]:
        return tuple(one for one in self.blocks if isinstance(one, ToolUse))


class ToolSpec(_Frozen):
    name: str
    description: str
    input_schema: dict[str, Any]


class ModelUnavailable(Exception):
    """The model cannot answer this turn: no key, a refusal, or the API is down. The text is for
    the person, so it never holds a key or a host."""


class Model(Protocol):
    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message: ...


def from_environment(environ: Mapping[str, str]) -> Model:
    """`scripted:<path>` replays a script. Any other value is an Anthropic model id, and an empty
    or missing one is the product default. The Anthropic client is built on the first reply, so a
    server with no key still starts and answers every other call."""
    chosen = environ.get(MODEL_VARIABLE, "").strip()
    if chosen.startswith(SCRIPTED_PREFIX):
        from cad.chat.scripted import Scripted

        return Scripted.load(chosen.removeprefix(SCRIPTED_PREFIX))
    from cad.chat.anthropic_model import AnthropicModel

    return AnthropicModel(chosen or DEFAULT_MODEL, environ)
