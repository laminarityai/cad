import re
from enum import StrEnum
from typing import Final, NewType

from pydantic import BaseModel, ConfigDict

from cad.variants.entry import VariantRefused

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
    TEST = "test"


class Conversation(BaseModel):
    """`project_id` and `brief_id` name what the person had open when the conversation started,
    so the agent can find the brief and its slots without being told. `auto_run` is the run that
    is going on now, and every stop clears it; `last_run` is the latest run the conversation
    started, kept after it stops so the page can show why it stopped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Mode = Mode.PLAN
    auto_run: str | None = None
    project_id: str | None = None
    brief_id: str | None = None
    last_run: str | None = None

    def moved(self, mode: Mode, auto_run: str | None = None) -> "Conversation":
        return self.model_copy(update={"mode": mode, "auto_run": auto_run})


class ModeRefused(VariantRefused):
    pass


class UnknownConversation(ModeRefused):
    pass
