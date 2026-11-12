import re
from typing import Final, NewType, cast

from pydantic import model_validator

from cad.errors import NotFound, Refused
from cad.frozen import Frozen

ConversationId = NewType("ConversationId", str)

CONVERSATION_ID: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")


class NotAConversation(ValueError):
    pass


def conversation_id(raw: object) -> ConversationId:
    if not isinstance(raw, str) or not CONVERSATION_ID.fullmatch(raw):
        raise NotAConversation(f"{raw!r} is not a conversation id")
    return ConversationId(raw)


class Conversation(Frozen):
    auto_run: str | None = None
    stopped_run: str | None = None
    project_id: str | None = None
    brief_id: str | None = None
    last_run: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _drop_the_mode(cls, raw: object) -> object:
        if not isinstance(raw, dict):
            return raw
        return {
            key: value for key, value in cast("dict[str, object]", raw).items() if key != "mode"
        }


class ConversationRefused(Refused):
    pass


class UnknownConversation(NotFound):
    pass
