from typing import Final

from pydantic import BaseModel

from cad.chat.log import Event
from cad.chat.routes import CHAT_ROUTES, Said
from cad.conversations.model import Mode
from cad.operations.openapi import Described, from_registry
from cad.operations.registry import OPERATIONS, ROUTES

CHAT_PATHS: Final = dict(CHAT_ROUTES)


class NoFields(BaseModel):
    pass


class ConversationCreated(BaseModel):
    conversation_id: str
    mode: Mode


class Send(Said):
    conversation_id: str


class MessageSent(BaseModel):
    seq: int


class Follow(BaseModel):
    """`after` and the `Last-Event-ID` header both name the last event seen. A browser's
    EventSource sends the header by itself when it reconnects."""

    conversation_id: str
    after: int = 0
    follow: bool = True


HAND_DESCRIBED: Final = (
    Described(
        name="create_conversation",
        path=CHAT_PATHS["create_conversation"],
        method="POST",
        input=NoFields,
        output=ConversationCreated,
        status=201,
        requires_json_body=True,
        failures=(401, 415),
    ),
    Described(
        name="message",
        path=CHAT_PATHS["message"],
        method="POST",
        input=Send,
        output=MessageSent,
        status=202,
        failures=(401, 404, 409, 415, 422),
    ),
    Described(
        name="stream",
        path=CHAT_PATHS["stream"],
        method="GET",
        input=Follow,
        output=Event,
        stream=True,
        failures=(401, 404, 422),
    ),
)


def every_route() -> list[Described]:
    return [*from_registry(OPERATIONS, ROUTES), *HAND_DESCRIBED]
