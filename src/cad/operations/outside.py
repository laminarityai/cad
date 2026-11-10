from typing import Final

from pydantic import BaseModel

from cad.chat.log import Event
from cad.chat.routes import CHAT_ROUTES, ConversationCreated, Follow, MessageSent, Said
from cad.operations.events import EVENTS_PATH
from cad.operations.openapi import Described, from_registry
from cad.operations.registry import OPERATIONS, ROUTES
from cad.operations.scorecards import ScorecardInput
from cad.scorecard.material import ScorecardSnapshot

CHAT_PATHS: Final = dict(CHAT_ROUTES)


class NoFields(BaseModel):
    pass


class Send(Said):
    conversation_id: str


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
        events="server-sent events: id is the sequence number, event is the kind, data is one "
        "transcript event",
        failures=(401, 404, 422),
    ),
    Described(
        name="scorecard_events",
        path=EVENTS_PATH,
        method="GET",
        input=ScorecardInput,
        output=ScorecardSnapshot,
        events="server-sent events: id is the card's etag, and event `scorecard` carries the whole "
        "card as data each time it changes. Event `refused` carries the refusal's name as plain "
        "text and ends the stream.",
    ),
)


def every_route() -> list[Described]:
    return [*from_registry(OPERATIONS, ROUTES), *HAND_DESCRIBED]
