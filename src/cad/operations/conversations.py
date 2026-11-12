from typing import Final

from pydantic import BaseModel

from cad.auto.model import AutoRun
from cad.conversations import store
from cad.conversations.model import (
    ConversationId,
    ConversationRefused,
    NotAConversation,
    conversation_id,
)
from cad.operations.model import Audience, Input, Tenant, operation

CONVERSATION = (
    "One conversation of the signed-in person: the project and brief it was started on, its "
    "running Auto run, the run whose stop holds it until the person writes or answers, and the "
    "latest Auto run it started, running or stopped with its reason. The web app "
    "reads it on load, when the tab comes back into view, after each turn and every few seconds "
    "while it is open, so a Stop pressed in another tab shows here."
)


class ConversationInput(Input):
    conversation_id: str


class ConversationState(BaseModel):
    conversation_id: str
    auto_run: str | None
    stopped_run: str | None


class ConversationView(ConversationState):
    project_id: str | None
    brief_id: str | None
    run: AutoRun | None


def _parsed(raw: str) -> ConversationId:
    try:
        return conversation_id(raw)
    except NotAConversation as error:
        raise ConversationRefused(str(error)) from error


def conversation(tenant: Tenant, arguments: ConversationInput) -> ConversationView:
    cid = _parsed(arguments.conversation_id)
    held = store.read(tenant.conversations, cid)
    return ConversationView(
        conversation_id=cid,
        auto_run=held.auto_run,
        stopped_run=held.stopped_run,
        project_id=held.project_id,
        brief_id=held.brief_id,
        run=store.last_run(tenant.roots, held),
    )


OPERATIONS: Final = (
    operation(
        name="conversation",
        audience=Audience.PERSON,
        description=CONVERSATION,
        input=ConversationInput,
        output=ConversationView,
        run=conversation,
    ),
)
