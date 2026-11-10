"""The person's chat routes: start a conversation, send a message, follow the transcript.

Each route takes a Clerk session token, like every person route, so an agent's OAuth access token
gets 401. A conversation is looked up only in the signed-in account's partition, so another
account's conversation id is 404 and nothing of it is read or written. A message starts one agent
turn on the person's say-so, and a turn never starts for any other reason. A POST must be JSON, so
a cross-site form cannot send one with the person's cookie.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from cad.accounts.principal import PersonSession
from cad.accounts.tenants import Tenants
from cad.chat import log
from cad.chat.log import Channel, Channels, UserSaid
from cad.chat.model import Model
from cad.chat.turn import agent_token, run_turn
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode, NotAConversation, conversation_id
from cad.operations.routes import CHALLENGE, PersonOf, session_token

MAX_MESSAGE_CHARS: Final = 20_000
KEEPALIVE_SECONDS: Final = 15.0
CHAT_ROUTES: Final = frozenset({"create_conversation", "message", "stream"})
STREAM_HEADERS: Final = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


class Said(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


@dataclass
class Chat:
    model: Model
    tenants: Tenants
    channels: Channels = field(default_factory=Channels)
    _turns: set["asyncio.Task[None]"] = field(default_factory=set["asyncio.Task[None]"])

    def channel(self, person: PersonSession, cid: ConversationId) -> Channel | None:
        conversations = self.tenants.of(person.account).conversations
        if not log.exists(conversations, cid):
            return None
        return self.channels.of(person.account, conversations, cid)

    def start(
        self, person: PersonSession, cid: ConversationId, channel: Channel, text: str
    ) -> int | None:
        if channel.running:
            return None
        channel.running = True
        seq = channel.append(UserSaid(text=text)).seq
        turn = asyncio.create_task(
            run_turn(self.model, self.tenants, agent_token(person, cid), channel)
        )
        self._turns.add(turn)
        turn.add_done_callback(self._turns.discard)
        return seq

    async def idle(self) -> None:
        while self._turns:
            await asyncio.gather(*self._turns)


def chat_routes(person_of: PersonOf, chat: Chat) -> list[Route]:
    def person(request: Request) -> PersonSession | Response:
        found = person_of(session_token(request))
        if found is None:
            return _error(401, "sign in: this route takes a Clerk session token", CHALLENGE)
        return found

    def known(request: Request, person: PersonSession) -> tuple[ConversationId, Channel] | Response:
        try:
            cid = conversation_id(request.path_params["conversation_id"])
        except NotAConversation as error:
            return _error(422, str(error))
        channel = chat.channel(person, cid)
        if channel is None:
            return _error(404, f"no conversation {cid} in this account")
        return cid, channel

    async def create(request: Request) -> Response:
        who = person(request)
        if isinstance(who, Response):
            return who
        if not _is_json(request):
            return _error(415, "send application/json")
        cid = conversation_id(f"c_{secrets.token_hex(8)}")
        held = store.set_mode(chat.tenants.of(who.account), cid, Mode.PLAN)
        return JSONResponse({"conversation_id": cid, "mode": held.mode}, 201)

    async def send(request: Request) -> Response:
        who = person(request)
        if isinstance(who, Response):
            return who
        if not _is_json(request):
            return _error(415, "send application/json")
        found = known(request, who)
        if isinstance(found, Response):
            return found
        cid, channel = found
        try:
            said = Said.model_validate_json(await request.body())
        except ValidationError as error:
            return _error(422, str(error))
        seq = chat.start(who, cid, channel, said.text)
        if seq is None:
            return _error(409, "the agent is still answering the last message")
        return JSONResponse({"seq": seq}, 202)

    async def stream(request: Request) -> Response:
        who = person(request)
        if isinstance(who, Response):
            return who
        found = known(request, who)
        if isinstance(found, Response):
            return found
        _, channel = found
        try:
            seen = int(request.headers.get("last-event-id") or request.query_params.get("after", 0))
        except ValueError:
            return _error(422, "after and Last-Event-ID are event numbers")
        follow = request.query_params.get("follow", "true") != "false"
        return StreamingResponse(
            _events(channel, max(seen, 0), follow),
            media_type="text/event-stream",
            headers=STREAM_HEADERS,
        )

    return [
        Route("/v1/conversations", create, methods=["POST"], name="create_conversation"),
        Route(
            "/v1/conversations/{conversation_id}/messages", send, methods=["POST"], name="message"
        ),
        Route("/v1/conversations/{conversation_id}/stream", stream, methods=["GET"], name="stream"),
    ]


async def _events(channel: Channel, seen: int, follow: bool) -> AsyncIterator[str]:
    """Everything after `seen`, then each event as it is appended. `follow=false` ends after what
    is held, for a reload or a `curl`."""
    while True:
        held = channel.after(seen)
        for stamped in held:
            yield log.line(stamped)
            seen = stamped.seq
        if held:
            continue
        if not follow:
            return
        try:
            await asyncio.wait_for(channel.wait_after(seen), KEEPALIVE_SECONDS)
        except TimeoutError:
            yield ": keepalive\n\n"


def _is_json(request: Request) -> bool:
    return request.headers.get("content-type", "").split(";")[0].strip().lower() == (
        "application/json"
    )


def _error(status: int, message: str, headers: dict[str, str] | None = None) -> Response:
    return JSONResponse({"error": message}, status, headers=headers)
