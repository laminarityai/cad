import re
from enum import StrEnum
from typing import Final, NewType

from pydantic import BaseModel, ConfigDict

from cad.variants.entry import VariantRefused

ConversationId = NewType("ConversationId", str)

# The id names a file, so it is checked here, at the boundary, and nowhere else.
CONVERSATION_ID: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")


class NotAConversation(ValueError):
    pass


def conversation_id(raw: object) -> ConversationId:
    if not isinstance(raw, str) or not CONVERSATION_ID.fullmatch(raw):
        raise NotAConversation(f"{raw!r} is not a conversation id")
    return ConversationId(raw)


class Mode(StrEnum):
    PLAN = "plan"
    DESIGN = "design"
    AUTO = "auto"
    TEST = "test"


class Conversation(BaseModel):
    """What the server holds about a conversation. One never set is in Plan, which comes first for
    every brief."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Mode = Mode.PLAN
    auto_run: str | None = None


class ModeRefused(VariantRefused):
    pass
