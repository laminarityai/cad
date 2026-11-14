"""The seam between a chat turn and the language model.

A turn hands the model the conversation so far and the tools the server lists, and gets one
assistant message back. The server's tool list is the only tool list, so the model is the one
part of a turn that can be swapped: the Anthropic adapter in production, a scripted double in
tests and evals. `CAD_CHAT_MODEL` selects it.
"""

from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from typing import Annotated, Any, Final, Literal, Protocol

from pydantic import Field

from cad.frozen import Frozen

DEFAULT_MODEL: Final = "claude-haiku-5-5"
MODEL_VARIABLE: Final = "CAD_CHAT_MODEL"
SCRIPTED_PREFIX: Final = "scripted:"


class Text(Frozen):
    kind: Literal["text"] = "text"
    text: str


class ToolUse(Frozen):
    kind: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class Attached(Frozen):
    """A file of a project that a tool result hands the model to read, such as a PDF."""

    project_id: str
    file_id: str


class Media(Frozen):
    """An attached file's bytes, base64, loaded for one reply and never written to the log."""

    media_type: str
    data: str


class ToolResult(Frozen):
    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    text: str
    is_error: bool = False
    attached: tuple[Attached, ...] = ()
    media: tuple[Media, ...] = ()


class ServerBlock(Frozen):
    """A block the API ran itself, a web search or its result. It goes back to the API exactly as
    it came, on every later step, because the API refuses one that was changed."""

    kind: Literal["server"] = "server"
    raw: dict[str, Any]


type Block = Annotated[Text | ToolUse | ToolResult | ServerBlock, Field(discriminator="kind")]


class Message(Frozen):
    role: Literal["user", "assistant"]
    blocks: tuple[Block, ...]

    @property
    def calls(self) -> tuple[ToolUse, ...]:
        return tuple(one for one in self.blocks if isinstance(one, ToolUse))

    @property
    def searches(self) -> int:
        return sum(
            isinstance(one, ServerBlock) and one.raw.get("type") == "server_tool_use"
            for one in self.blocks
        )


class ToolSpec(Frozen):
    name: str
    description: str
    input_schema: dict[str, Any]


type Heard = Callable[[str], None]

HEARD: Final = ContextVar[Heard | None]("heard", default=None)
"""Where a model that streams sends each piece of reply text as it arrives. A turn sets it for
its own task, so the open page shows the reply before it is whole. The text it hears is not
stored: the reply is, once it is whole."""


class ModelUnavailable(Exception):
    """The model cannot answer this turn: no key, a refusal, or the API is down. The text is for
    the person, so it never holds a key or a host."""


class Model(Protocol):
    async def reply(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        searches_spent: int,
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
