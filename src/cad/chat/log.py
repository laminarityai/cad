"""A conversation's transcript: an append-only list of events, one JSON line each.

The transcript is what the stream shows and what the next turn sends the model, so a reload or a
restart loses nothing.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Final, Literal, cast

from pydantic import Field, TypeAdapter, ValidationError

from cad.accounts.principal import AccountId
from cad.chat.model import Attached, Block, Message, ServerBlock, Text, ToolResult, ToolUse
from cad.conversations.model import ConversationId
from cad.frozen import Frozen
from cad.records import files
from cad.selections.model import SelectionNote

TRANSCRIPTS: Final = "chat"
STOP_NOTICE: Final = "(this call was interrupted before it returned)"


class UserSaid(Frozen):
    """`selection` is the part of a design the person pointed at in the 3D view when they sent
    this message."""

    kind: Literal["user"] = "user"
    text: str
    selection: SelectionNote | None = None


class Answered(Frozen):
    """The conversation is told every answer in the project's ledger up to `through`."""

    project_id: str
    through: int


class DriverSaid(Frozen):
    """The server speaking to the model: the Auto driver's reminder that the run has not stopped,
    or, with `answered`, the person's answer to the confirmation page."""

    kind: Literal["driver"] = "driver"
    text: str
    answered: Answered | None = None


class AgentSaid(Frozen):
    kind: Literal["agent"] = "agent"
    text: str


class ToolCalled(Frozen):
    kind: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    input: dict[str, Any]


class ToolReturned(Frozen):
    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    text: str
    is_error: bool
    attached: tuple[Attached, ...] = Field(default=(), exclude_if=lambda one: not one)


class Page(Frozen):
    title: str
    url: str


class WebSearched(Frozen):
    """A web search the model ran through the API. `raw` is the API's block, sent back unchanged.
    A search result is a pointer: no check reads a number from it."""

    kind: Literal["web_search"] = "web_search"
    call_id: str
    query: str
    raw: dict[str, Any]


class WebFound(Frozen):
    """What a web search found: the pages, or the API's error code."""

    kind: Literal["web_search_result"] = "web_search_result"
    call_id: str
    pages: tuple[Page, ...] = ()
    error: str | None = None
    raw: dict[str, Any]


def web_event(block: ServerBlock) -> WebSearched | WebFound | None:
    raw = block.raw
    if raw.get("type") == "server_tool_use":
        query = raw.get("input", {}).get("query", "")
        return WebSearched(call_id=raw["id"], query=str(query), raw=raw)
    if raw.get("type") == "web_search_tool_result":
        content = raw.get("content")
        if isinstance(content, list):
            pages = tuple(
                Page(title=str(one.get("title", "")), url=str(one.get("url", "")))
                for one in cast(list[dict[str, Any]], content)
            )
            return WebFound(call_id=raw["tool_use_id"], pages=pages, raw=raw)
        code = cast(dict[str, Any], content or {}).get("error_code", "unavailable")
        return WebFound(call_id=raw["tool_use_id"], error=str(code), raw=raw)
    return None


class StopReport(Frozen):
    """An Auto run stopped. `report` is the server's, from the signed run log."""

    kind: Literal["stop_report"] = "stop_report"
    run_id: str
    reason: str
    report: str


class TurnFailed(Frozen):
    kind: Literal["turn_failed"] = "turn_failed"
    message: str


class TurnEnded(Frozen):
    kind: Literal["turn_ended"] = "turn_ended"


PARTIAL: Final = "agent_partial"
KEEPALIVE_SECONDS: Final = 15.0

type Event = Annotated[
    UserSaid
    | DriverSaid
    | AgentSaid
    | ToolCalled
    | ToolReturned
    | WebSearched
    | WebFound
    | StopReport
    | TurnFailed
    | TurnEnded,
    Field(discriminator="kind"),
]


class Stamped(Frozen):
    seq: int
    event: Event


STAMPED: Final = TypeAdapter[Stamped](Stamped)


def transcript_path(conversations: Path, cid: ConversationId) -> Path:
    return conversations / TRANSCRIPTS / f"{cid}.jsonl"


@dataclass
class Channel:
    """One conversation's transcript, with a signal for each append and a flag for a running turn.
    Everything that appends runs on the server's event loop, so an append needs no lock.
    `partial` is the reply text heard so far and not yet stored. It lives only here, and each
    append clears it, because the append stores the reply it was part of or ends the turn."""

    path: Path
    running: bool = False
    partial: str = ""
    _stamped: list[Stamped] = field(default_factory=list[Stamped])
    _changed: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self._stamped = _readable_prefix(self.path)

    def append(self, event: Event) -> Stamped:
        stamped = Stamped(seq=len(self._stamped) + 1, event=event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as file:
            file.write(stamped.model_dump_json().encode() + b"\n")
        self._stamped.append(stamped)
        self.partial = ""
        self._release()
        return stamped

    def hear(self, text: str) -> None:
        self.partial += text
        self._release()

    def _release(self) -> None:
        released, self._changed = self._changed, asyncio.Event()
        released.set()

    def after(self, seq: int) -> Sequence[Stamped]:
        return self._stamped[seq:]

    async def wait_change(self, seq: int, partial: str) -> None:
        """Return once an event after `seq` is held or the partial text is no longer `partial`."""
        while True:
            changed = self._changed
            if self.after(seq) or self.partial != partial:
                return
            await changed.wait()

    def events(self) -> Sequence[Event]:
        return tuple(one.event for one in self._stamped)


def _readable_prefix(path: Path) -> list[Stamped]:
    try:
        lines = path.read_bytes().splitlines()
    except FileNotFoundError:
        return []
    loaded: list[Stamped] = []
    for line in lines:
        try:
            loaded.append(STAMPED.validate_json(line))
        except (ValidationError, ValueError):
            break
    if len(loaded) < len(lines):
        files.replace(path, b"".join(one.model_dump_json().encode() + b"\n" for one in loaded))
    return loaded


def transcript(conversations: Path, cid: ConversationId) -> tuple[Stamped, ...]:
    try:
        lines = transcript_path(conversations, cid).read_bytes().splitlines()
    except FileNotFoundError:
        return ()
    stamped: list[Stamped] = []
    for line in lines:
        try:
            stamped.append(STAMPED.validate_json(line))
        except (ValidationError, ValueError):
            break
    return tuple(stamped)


@dataclass
class Channels:
    _open: dict[tuple[AccountId, ConversationId], Channel] = field(
        default_factory=dict[tuple[AccountId, ConversationId], Channel]
    )

    def of(self, account: AccountId, conversations: Path, cid: ConversationId) -> Channel:
        key = (account, cid)
        channel = self._open.get(key)
        if channel is None:
            channel = self._open[key] = Channel(transcript_path(conversations, cid))
        return channel

    def open_in(self, account: AccountId) -> list[tuple[ConversationId, Channel]]:
        return [(cid, channel) for (owner, cid), channel in self._open.items() if owner == account]


def messages_of(events: Sequence[Event]) -> list[Message]:
    """The conversation as the model sees it. A call with no result, from a turn that died, gets
    an error result, because the API refuses a call that nothing answers. A web search with no
    result is left out for the same reason."""
    messages: list[Message] = []
    open_calls: list[str] = []
    found = {event.call_id for event in events if isinstance(event, WebFound)}

    def add(role: Literal["user", "assistant"], block: Block) -> None:
        if messages and messages[-1].role == role:
            messages[-1] = Message(role=role, blocks=(*messages[-1].blocks, block))
        else:
            messages.append(Message(role=role, blocks=(block,)))

    def close_calls() -> None:
        for call_id in open_calls:
            add("user", ToolResult(call_id=call_id, text=STOP_NOTICE, is_error=True))
        open_calls.clear()

    for event in events:
        match event:
            case UserSaid() | DriverSaid():
                close_calls()
                add("user", Text(text=_told(event)))
            case AgentSaid():
                add("assistant", Text(text=event.text))
            case ToolCalled():
                add("assistant", ToolUse(id=event.call_id, name=event.name, input=event.input))
                open_calls.append(event.call_id)
            case ToolReturned():
                if event.call_id in open_calls:
                    open_calls.remove(event.call_id)
                    add("user", ToolResult(**event.model_dump(exclude={"kind"})))
            case WebSearched():
                if event.call_id in found:
                    add("assistant", ServerBlock(raw=event.raw))
            case WebFound():
                add("assistant", ServerBlock(raw=event.raw))
            case StopReport() | TurnFailed() | TurnEnded():
                pass
    close_calls()
    return messages


def _told(event: UserSaid | DriverSaid) -> str:
    """What the model reads for a message: the person's words, then, when they pointed at part of
    a design, one server line that names it. Only the server writes that line."""
    if not isinstance(event, UserSaid) or event.selection is None:
        return event.text
    picked = event.selection
    return (
        f"{event.text}\n\n[server: the person selected {picked.summary} of slot {picked.slot}, "
        f"revision {picked.revision}, brief {picked.brief_id}, in the 3D view when they sent "
        f"this message. This, these and it in the message mean that selection. Call "
        f"read_selection with {picked.selection_id} to see what it covers, then build the "
        f"slot's next revision.]"
    )


def partial_line(text: str) -> str:
    """The reply text heard so far, as a server-sent event with no id: it is not stored, so a
    client never resumes from it."""
    data = json.dumps({"text": text}, separators=(",", ":"))
    return f"event: {PARTIAL}\ndata: {data}\n\n"


def line(stamped: Stamped) -> str:
    """One server-sent event: the seq is its id, so a client can resume with Last-Event-ID."""
    data = json.dumps(stamped.event.model_dump(mode="json"), separators=(",", ":"))
    return f"id: {stamped.seq}\nevent: {stamped.event.kind}\ndata: {data}\n\n"


async def frames(channel: Channel, seen: int, follow: bool) -> AsyncIterator[str]:
    """Everything after `seen`, then each event as it is appended, and the reply text heard so
    far whenever it grows. A stored event replaces the text before it, so a client drops its
    partial text at each one. `follow=false` ends after what is held, for a reload or a `curl`."""
    shown = ""
    while True:
        held = channel.after(seen)
        for stamped in held:
            yield line(stamped)
            seen = stamped.seq
        if held:
            shown = ""
        if channel.partial != shown:
            shown = channel.partial
            if shown:
                yield partial_line(shown)
        if not follow:
            return
        try:
            await asyncio.wait_for(channel.wait_change(seen, shown), KEEPALIVE_SECONDS)
        except TimeoutError:
            yield ": keepalive\n\n"
