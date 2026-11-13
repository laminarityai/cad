"""The person's chat routes: start a conversation, send a message, follow the transcript.

Each route takes a Clerk session token, like every person route, so an agent's OAuth access token
gets 401. A conversation is looked up only in the signed-in account's partition, so another
account's conversation id is 404 and nothing of it is read or written. A turn starts on the
person's say-so only: a message, or an answer on the confirmation page that the conversation waits
on. One answer starts at most one turn, because the transcript records that the conversation was
told it (see `answer_driver`). A POST must be JSON, so a cross-site form cannot send one with the
person's cookie.
"""

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from cad.accounts.principal import PersonSession
from cad.briefs import store as briefs
from cad.briefs.store import BriefRefused
from cad.chat import answer_driver, log
from cad.chat.log import (
    Channel,
    Channels,
    DriverSaid,
    Event,
    TurnEnded,
    TurnFailed,
    UserSaid,
)
from cad.chat.model import Model
from cad.chat.turn import agent_token, run_turn
from cad.confirmations.answers import read_ledger
from cad.conversations import store
from cad.conversations.model import (
    ConversationId,
    NotAConversation,
    UnknownConversation,
    conversation_id,
)
from cad.operations.model import Tenant
from cad.operations.routes import PersonOf, refuse, session_person
from cad.operations.tenants import Tenants
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId, ProjectRefused, UnknownProject, parse_project_id
from cad.sandbox.outcome import SandboxUnavailable
from cad.selections import mint
from cad.selections.model import Picked, SelectionNote, SelectionRefused
from cad.variants.entry import VariantRefused

MAX_MESSAGE_CHARS: Final = 20_000
KEEPALIVE_SECONDS: Final = 15.0
CHAT_ROUTES: Final = frozenset(
    {
        ("create_conversation", "/v1/conversations"),
        ("project_conversation", "/v1/projects/{project_id}/conversation"),
        ("message", "/v1/conversations/{conversation_id}/messages"),
        ("stream", "/v1/conversations/{conversation_id}/stream"),
    }
)
STREAM_HEADERS: Final = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
CUT_OFF: Final = "The server stopped before this turn finished. Send a message to carry on."
_LOG = logging.getLogger(__name__)


class Said(BaseModel):
    """`selection` is what the person picked in the 3D view for this message to change."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    selection: Picked | None = None


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    brief_id: str | None = None


class ConversationCreated(BaseModel):
    conversation_id: str


class ProjectConversation(BaseModel):
    conversation_id: str


class MessageSent(BaseModel):
    seq: int


class Follow(BaseModel):
    """`after` and the `Last-Event-ID` header both name the last event seen. A browser's
    EventSource sends the header by itself when it reconnects, and the header wins."""

    conversation_id: str
    after: int = 0
    follow: bool = True


@dataclass
class Chat:
    model: Model
    tenants: Tenants
    channels: Channels = field(default_factory=Channels)
    _turns: set["asyncio.Task[None]"] = field(default_factory=set["asyncio.Task[None]"])

    def channel(self, person: PersonSession, cid: ConversationId) -> Channel | None:
        conversations = self.tenants.of(person.account).conversations
        try:
            store.read(conversations, cid)
        except UnknownConversation:
            return None
        return self.channels.of(person.account, conversations, cid)

    def start(
        self,
        person: PersonSession,
        cid: ConversationId,
        channel: Channel,
        text: str,
        selection: SelectionNote | None = None,
    ) -> int | None:
        if channel.running:
            return None
        return self._begin(person, cid, channel, UserSaid(text=text, selection=selection))

    def answered(self, person: PersonSession, project: ProjectId) -> None:
        """The person answered the project's page. Each open conversation of theirs that waits on
        it starts a turn now, or when its running turn ends. One not opened since a restart is
        told when it is opened."""
        for cid, channel in self.channels.open_in(person.account):
            self._deliver(person, cid, channel, project)

    def catch_up(self, person: PersonSession, cid: ConversationId, channel: Channel) -> None:
        """The person opened the conversation: deliver an answer this process has not told it,
        and run a delivery that a restart cut off before its turn started."""
        if channel.running:
            return
        events = channel.events()
        if events and _is_delivery(events[-1]):
            self._run(person, cid, channel)
            return
        if _turn_left_open(events):
            channel.append(TurnFailed(message=CUT_OFF))
            channel.append(TurnEnded())
        self._deliver(person, cid, channel, None)

    def _deliver(
        self, person: PersonSession, cid: ConversationId, channel: Channel, only: ProjectId | None
    ) -> None:
        # Synchronous from the running check to the append, so nothing else on the loop can
        # deliver the same answers in between.
        if channel.running:
            return
        waiting = answer_driver.waiting_on(channel.events())
        if waiting is None or (only is not None and waiting.project != only):
            return
        tenant = self.tenants.of(person.account)
        try:
            ledger = read_ledger(tenant.roots.projects, waiting.project)
            found = answer_driver.delivery(waiting, ledger)
        except Exception:
            # The page answer is recorded already, so a store that cannot be read must not fail
            # it. The conversation is told when it is next opened.
            _LOG.exception("could not tell conversation %s about a page answer", cid)
            return
        if found is not None:
            self._begin(person, cid, channel, found)

    def _begin(
        self, person: PersonSession, cid: ConversationId, channel: Channel, event: Event
    ) -> int:
        tenant = self.tenants.of(person.account)
        store.lift_hold(tenant.roots, tenant.conversations, cid)
        seq = channel.append(event).seq
        self._run(person, cid, channel)
        return seq

    def _run(self, person: PersonSession, cid: ConversationId, channel: Channel) -> None:
        channel.running = True
        turn = asyncio.create_task(
            run_turn(self.model, self.tenants, agent_token(person, cid), channel)
        )
        self._turns.add(turn)
        turn.add_done_callback(self._turns.discard)
        turn.add_done_callback(
            lambda done: done.cancelled() or self._deliver(person, cid, channel, None)
        )

    async def idle(self) -> None:
        while True:
            # A turn's done callback may start a follow-up turn, so let the callbacks run first.
            await asyncio.sleep(0)
            if not self._turns:
                return
            await asyncio.gather(*self._turns)


def chat_routes(person_of: PersonOf, chat: Chat) -> list[Route]:
    def known(request: Request, person: PersonSession) -> tuple[ConversationId, Channel] | Response:
        try:
            cid = conversation_id(request.path_params["conversation_id"])
        except NotAConversation as error:
            return refuse(422, str(error))
        channel = chat.channel(person, cid)
        if channel is None:
            return refuse(404, f"no conversation {cid} in this account")
        return cid, channel

    async def create(request: Request) -> Response:
        who = session_person(person_of, request)
        if isinstance(who, Response):
            return who
        if not _is_json(request):
            return refuse(415, "send application/json")
        try:
            start = Start.model_validate_json(await request.body())
        except ValidationError as error:
            return refuse(422, str(error))
        tenant = chat.tenants.of(who.account)
        if start.brief_id is not None and start.project_id is None:
            return refuse(422, "send project_id with brief_id")
        if start.brief_id is not None and not _holds(tenant, start.project_id, start.brief_id):
            return refuse(404, f"no brief {start.brief_id} in project {start.project_id}")
        if start.project_id is not None and not _is_project(tenant, start.project_id):
            return refuse(404, f"no project {start.project_id} in this account")
        cid = conversation_id(f"c_{secrets.token_hex(8)}")
        store.create(tenant.conversations, cid, start.project_id, start.brief_id)
        return _json(ConversationCreated(conversation_id=cid), 201)

    async def send(request: Request) -> Response:
        who = session_person(person_of, request)
        if isinstance(who, Response):
            return who
        if not _is_json(request):
            return refuse(415, "send application/json")
        found = known(request, who)
        if isinstance(found, Response):
            return found
        cid, channel = found
        try:
            said = Said.model_validate_json(await request.body())
        except ValidationError as error:
            return refuse(422, str(error))
        picked = None
        if said.selection is not None:
            minted = await _mint(chat.tenants.of(who.account), cid, said.selection)
            if isinstance(minted, Response):
                return minted
            picked = minted
        seq = chat.start(who, cid, channel, said.text, picked)
        if seq is None:
            return refuse(409, "the agent is still answering the last message")
        return _json(MessageSent(seq=seq), 202)

    async def stream(request: Request) -> Response:
        who = session_person(person_of, request)
        if isinstance(who, Response):
            return who
        found = known(request, who)
        if isinstance(found, Response):
            return found
        cid, channel = found
        chat.catch_up(who, cid, channel)
        try:
            asked = Follow.model_validate({**request.query_params, **request.path_params})
            header = request.headers.get("last-event-id")
            seen = int(header) if header else asked.after
        except (ValidationError, ValueError):
            return refuse(422, "after and Last-Event-ID are event numbers, follow is a boolean")
        return StreamingResponse(
            _events(channel, max(seen, 0), asked.follow),
            media_type="text/event-stream",
            headers=STREAM_HEADERS,
        )

    async def project_conversation(request: Request) -> Response:
        """The project's one conversation, made on the first read, so every brief of the project
        opens the same chat without an id in the URL."""
        who = session_person(person_of, request)
        if isinstance(who, Response):
            return who
        tenant = chat.tenants.of(who.account)
        raw = request.path_params["project_id"]
        if not _is_project(tenant, raw):
            return refuse(404, f"no project {raw} in this account")
        project = parse_project_id(raw)
        # No await from the read to the create, so two reads on this loop make one conversation.
        cid = store.of_project(tenant.conversations, project)
        if cid is None:
            cid = conversation_id(f"c_{secrets.token_hex(8)}")
            store.create(tenant.conversations, cid, project)
        return _json(ProjectConversation(conversation_id=cid), 200)

    return [
        Route(
            "/v1/projects/{project_id}/conversation",
            project_conversation,
            methods=["GET"],
            name="project_conversation",
        ),
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


async def _mint(tenant: Tenant, cid: ConversationId, picked: Picked) -> SelectionNote | Response:
    """The signed selection's note, or the response that refuses the pick. It is made before the
    message is appended, so a refused pick leaves the transcript as it was."""
    try:
        project = store.read(tenant.conversations, cid).project_id
    except UnknownConversation:
        return refuse(404, f"no conversation {cid} in this account")
    if project is None:
        return refuse(422, "pick something in a project: this conversation has none")
    try:
        record = await asyncio.to_thread(
            mint.mint,
            tenant.roots,
            parse_project_id(project),
            picked,
            variants=tenant.variants,
            geometry=tenant.geometry,
        )
    except (SelectionRefused, VariantRefused, ProjectRefused) as error:
        return refuse(422, str(error))
    except SandboxUnavailable as error:
        return refuse(503, str(error))
    return mint.note(record)


def _is_delivery(event: Event) -> bool:
    return isinstance(event, DriverSaid) and event.answered is not None


def _turn_left_open(events: Sequence[Event]) -> bool:
    for one in reversed(events):
        if isinstance(one, TurnEnded):
            return False
        if isinstance(one, UserSaid | DriverSaid):
            return True
    return False


def _holds(tenant: Tenant, project_id: str | None, brief_id: str) -> bool:
    try:
        return briefs.read_brief(tenant.roots, brief_id).project == project_id
    except BriefRefused:
        return False


def _is_project(tenant: Tenant, raw: str) -> bool:
    try:
        return bool(project_briefs(tenant.roots, parse_project_id(raw)))
    except UnknownProject:
        return False


def _is_json(request: Request) -> bool:
    return request.headers.get("content-type", "").split(";")[0].strip().lower() == (
        "application/json"
    )


def _json(body: BaseModel, status: int) -> Response:
    return Response(body.model_dump_json(), status, media_type="application/json")
