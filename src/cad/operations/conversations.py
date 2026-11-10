from typing import Final

from pydantic import BaseModel

from cad.conversations import store
from cad.conversations.model import Mode, ModeRefused, NotAConversation, conversation_id
from cad.operations.model import Audience, Input, Tenant, operation

SET_MODE = (
    "Switch a conversation to Plan, Design, Auto or Test mode. Only the person does this, in the "
    "web app, and the server enforces the mode on the agent's next tool call. Leaving Auto stops "
    "the conversation's Auto run. Returns the conversation's mode and its Auto run, if any."
)


class SetModeInput(Input):
    conversation_id: str
    mode: Mode


class ConversationState(BaseModel):
    conversation_id: str
    mode: Mode
    auto_run: str | None


def set_mode(tenant: Tenant, arguments: SetModeInput) -> ConversationState:
    try:
        cid = conversation_id(arguments.conversation_id)
    except NotAConversation as error:
        raise ModeRefused(str(error)) from error
    held = store.set_mode(tenant, cid, arguments.mode)
    return ConversationState(conversation_id=cid, mode=held.mode, auto_run=held.auto_run)


OPERATIONS: Final = (
    operation(
        name="set_mode",
        audience=Audience.PERSON,
        description=SET_MODE,
        input=SetModeInput,
        output=ConversationState,
        run=set_mode,
    ),
)
