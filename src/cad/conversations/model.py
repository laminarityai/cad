import re
from enum import StrEnum
from typing import Final, NewType

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


class Mode(StrEnum):
    PLAN = "plan"
    DESIGN = "design"
    AUTO = "auto"


class Conversation(Frozen):
    mode: Mode = Mode.PLAN
    auto_run: str | None = None
    project_id: str | None = None
    brief_id: str | None = None
    last_run: str | None = None

    def moved(self, mode: Mode, auto_run: str | None = None) -> "Conversation":
        return self.model_copy(update={"mode": mode, "auto_run": auto_run})


class ModeRefused(Refused):
    pass


class UnknownConversation(NotFound):
    pass
