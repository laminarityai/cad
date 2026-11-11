from typing import Final

from pydantic import BaseModel

from cad.auto.model import AutoRun
from cad.conversations import store
from cad.conversations.model import (
    ConversationId,
    Mode,
    ModeRefused,
    NotAConversation,
    conversation_id,
)
from cad.operations.model import Audience, Input, Tenant, operation

SET_MODE = (
    "Switch a conversation to Plan, Design or Auto mode. Only the person does this, in the "
    "web app, and the server enforces the mode on the agent's next tool call. Leaving Auto stops "
    "the conversation's Auto run. Returns the conversation's mode and its Auto run, if any."
)


CONVERSATION = (
    "One conversation of the signed-in person: its mode, the project and brief it was started "
    "on, and the latest Auto run it started, running or stopped with its reason. The web app "
    "reads it on load, when the tab comes back into view, after each turn and every few seconds "
    "while it is open, so a Stop pressed in another tab shows here."
)


class ConversationInput(Input):
    conversation_id: str


class SetModeInput(Input):
    conversation_id: str
    mode: Mode


class ConversationState(BaseModel):
    conversation_id: str
    mode: Mode
    auto_run: str | None


class ConversationView(ConversationState):
    project_id: str | None
    brief_id: str | None
    run: AutoRun | None


def _parsed(raw: str) -> ConversationId:
    try:
        return conversation_id(raw)
    except NotAConversation as error:
        raise ModeRefused(str(error)) from error


def conversation(tenant: Tenant, arguments: ConversationInput) -> ConversationView:
    cid = _parsed(arguments.conversation_id)
    held = store.read(tenant.conversations, cid)
    return ConversationView(
        conversation_id=cid,
        mode=held.mode,
        auto_run=held.auto_run,
        project_id=held.project_id,
        brief_id=held.brief_id,
        run=store.last_run(tenant.roots, held),
    )


def set_mode(tenant: Tenant, arguments: SetModeInput) -> ConversationState:
    cid = _parsed(arguments.conversation_id)
    held = store.set_mode(tenant.roots, tenant.conversations, cid, arguments.mode)
    return ConversationState(conversation_id=cid, mode=held.mode, auto_run=held.auto_run)


OPERATIONS: Final = (
    operation(
        name="conversation",
        audience=Audience.PERSON,
        description=CONVERSATION,
        input=ConversationInput,
        output=ConversationView,
        run=conversation,
    ),
    operation(
        name="set_mode",
        audience=Audience.PERSON,
        description=SET_MODE,
        input=SetModeInput,
        output=ConversationState,
        run=set_mode,
    ),
)
