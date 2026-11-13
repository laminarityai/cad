from typing import Final

from cad.chat.log import Event
from cad.chat.routes import (
    CHAT_ROUTES,
    ConversationCreated,
    Follow,
    MessageSent,
    ProjectConversation,
    Said,
    Start,
)
from cad.confirmations.card import ConfirmationCard, ProjectArguments
from cad.confirmations.web import CARD_PATH
from cad.operations.openapi import Described, from_registry
from cad.operations.registry import OPERATIONS, ROUTES
from cad.uploads.web import PATHS, Added, AddFileInput, Declined, DeclineInput

CHAT_PATHS: Final = dict(CHAT_ROUTES)


class Send(Said):
    conversation_id: str


HAND_DESCRIBED: Final = (
    Described(
        name="create_conversation",
        path=CHAT_PATHS["create_conversation"],
        method="POST",
        input=Start,
        output=ConversationCreated,
        status=201,
        requires_json_body=True,
        failures=(401, 404, 415, 422),
    ),
    Described(
        name="project_conversation",
        path=CHAT_PATHS["project_conversation"],
        method="GET",
        input=ProjectArguments,
        output=ProjectConversation,
        failures=(401, 404),
    ),
    Described(
        name="confirmation",
        path=CARD_PATH,
        method="GET",
        input=ProjectArguments,
        output=ConfirmationCard,
        failures=(401, 404),
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
        events="server-sent events: id is the sequence number, event is the kind, data is one "
        "transcript event",
        failures=(401, 404, 422),
    ),
    Described(
        name="add_file",
        path=PATHS["add_file"],
        method="POST",
        input=AddFileInput,
        output=Added,
        octets=True,
        failures=(400, 401, 404, 413, 415, 422, 503),
    ),
    Described(
        name="decline_part",
        path=PATHS["decline_part"],
        method="POST",
        input=DeclineInput,
        output=Declined,
        requires_json_body=True,
        failures=(400, 401, 404, 415, 422),
    ),
)


def every_route() -> list[Described]:
    return [*from_registry(OPERATIONS, ROUTES), *HAND_DESCRIBED]
