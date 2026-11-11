"""A conversation's transcript: an append-only list of events, one JSON line each.

The transcript is what the stream shows and what the next turn sends the model, so a reload or a
restart loses nothing. It lives in the account's conversations directory, beside the
conversation's mode, so one account's transcript is never in another's partition.
"""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from cad.accounts.principal import AccountId
from cad.chat.model import Block, Message, Text, ToolResult, ToolUse
from cad.conversations.model import ConversationId
from cad.selections.model import SelectionNote

TRANSCRIPTS: Final = "chat"
STOP_NOTICE: Final = "(this call was interrupted before it returned)"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UserSaid(_Frozen):
    """`selection` is the part of a design the person pointed at in the 3D view when they sent
    this message."""

    kind: Literal["user"] = "user"
    text: str
    selection: SelectionNote | None = None


class Answered(_Frozen):
    """The conversation is told every answer in the project's ledger up to `through`."""

    project_id: str
    through: int


class DriverSaid(_Frozen):
    """The server speaking to the model: the Auto driver's reminder that the run has not stopped,
    or, with `answered`, the person's answer to the confirmation page."""

    kind: Literal["driver"] = "driver"
    text: str
    answered: Answered | None = None


class AgentSaid(_Frozen):
    kind: Literal["agent"] = "agent"
    text: str


class ToolCalled(_Frozen):
    kind: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    input: dict[str, Any]


class ToolReturned(_Frozen):
    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    text: str
    is_error: bool


class StopReport(_Frozen):
    """An Auto run stopped. `report` is the server's, from the signed run log."""

    kind: Literal["stop_report"] = "stop_report"
    run_id: str
    reason: str
    report: str


class TurnFailed(_Frozen):
    kind: Literal["turn_failed"] = "turn_failed"
    message: str


class TurnEnded(_Frozen):
    kind: Literal["turn_ended"] = "turn_ended"


type Event = Annotated[
    UserSaid
    | DriverSaid
    | AgentSaid
    | ToolCalled
    | ToolReturned
    | StopReport
    | TurnFailed
    | TurnEnded,
    Field(discriminator="kind"),
]


class Stamped(_Frozen):
    seq: int
    event: Event


STAMPED: Final = TypeAdapter[Stamped](Stamped)


def transcript_path(conversations: Path, cid: ConversationId) -> Path:
    return conversations / TRANSCRIPTS / f"{cid}.jsonl"


@dataclass
class Channel:
    """One conversation's transcript, with a signal for each append and a flag for a running turn.
    Everything that appends runs on the server's event loop, so an append needs no lock."""

    path: Path
    running: bool = False
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
        released, self._changed = self._changed, asyncio.Event()
        released.set()
        return stamped

    def after(self, seq: int) -> Sequence[Stamped]:
        return self._stamped[seq:]

    async def wait_after(self, seq: int) -> Sequence[Stamped]:
        while True:
            changed = self._changed
            held = self.after(seq)
            if held:
                return held
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
        path.write_bytes(b"".join(one.model_dump_json().encode() + b"\n" for one in loaded))
    return loaded


def person_said(conversations: Path, cid: ConversationId) -> tuple[tuple[int, str], ...]:
    try:
        lines = transcript_path(conversations, cid).read_bytes().splitlines()
    except FileNotFoundError:
        return ()
    said: list[tuple[int, str]] = []
    for line in lines:
        try:
            stamped = STAMPED.validate_json(line)
        except (ValidationError, ValueError):
            break
        if isinstance(stamped.event, UserSaid):
            said.append((stamped.seq, stamped.event.text))
    return tuple(said)


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
    an error result, because the API refuses a call that nothing answers."""
    messages: list[Message] = []
    open_calls: list[str] = []

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
                add("user", Text(text=event.text))
            case AgentSaid():
                add("assistant", Text(text=event.text))
            case ToolCalled():
                add("assistant", ToolUse(id=event.call_id, name=event.name, input=event.input))
                open_calls.append(event.call_id)
            case ToolReturned():
                if event.call_id in open_calls:
                    open_calls.remove(event.call_id)
                    add("user", ToolResult(**event.model_dump(exclude={"kind"})))
            case StopReport() | TurnFailed() | TurnEnded():
                pass
    close_calls()
    return messages


def line(stamped: Stamped) -> str:
    """One server-sent event: the seq is its id, so a client can resume with Last-Event-ID."""
    data = json.dumps(stamped.event.model_dump(mode="json"), separators=(",", ":"))
    return f"id: {stamped.seq}\nevent: {stamped.event.kind}\ndata: {data}\n\n"
