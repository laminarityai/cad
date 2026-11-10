import json
import os
import secrets
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Final

from cad.auto import log
from cad.auto.model import AutoRun, PersonStopped, Running, RunRefused, Stopped, UnknownRun
from cad.conversations.model import Conversation, ConversationId, Mode, UnknownConversation
from cad.operations.model import Tenant

_LOCK: Final = threading.RLock()


def read(directory: Path, cid: ConversationId) -> Conversation:
    """The one lookup of a conversation. `directory` is one account's partition, so another
    account's conversation id is unknown here, the same as an id nobody made."""
    try:
        return Conversation.model_validate_json((directory / f"{cid}.json").read_bytes())
    except FileNotFoundError:
        raise UnknownConversation(f"no conversation {cid} in this account") from None


def create(tenant: Tenant, cid: ConversationId) -> Conversation:
    with _LOCK:
        return _write(tenant.conversations, cid, Conversation())


def bind(tenant: Tenant, cid: ConversationId | None) -> Tenant:
    """An agent token's conversation with no record binds as Plan, which builds nothing."""
    if cid is None:
        return tenant
    try:
        held = read(tenant.conversations, cid)
    except UnknownConversation:
        held = Conversation()
    return replace(
        tenant,
        conversation=cid,
        mode=held.mode,
        auto_run=held.auto_run if held.mode is Mode.AUTO else None,
    )


def set_mode(tenant: Tenant, cid: ConversationId, mode: Mode) -> Conversation:
    with _LOCK:
        return _switch(tenant, cid, mode)


def record_event(tenant: Tenant, run_id: str, make: log.Make) -> AutoRun:
    """Every record of a run goes through here. A run that is stopped after it, by any reason,
    takes its conversation out of Auto mode, to Design, when it is the conversation's current
    run (ADR-0010). It also does so for a run already stopped, so a crash between the stop and
    the write heals on the next call. A stopped earlier run leaves a conversation that moved on."""
    with _LOCK:
        run = log.append_event(tenant.roots, run_id, make)
        if isinstance(run.state, Stopped):
            cid = run.state.start.conversation
            if read(tenant.conversations, cid).auto_run == run_id:
                _write(tenant.conversations, cid, Conversation(mode=Mode.DESIGN))
        return run


def stop_by_person(tenant: Tenant, run_id: str) -> tuple[AutoRun, Conversation]:
    run = record_event(tenant, run_id, lambda _: PersonStopped())
    return run, read(tenant.conversations, run.state.start.conversation)


def start_run(
    tenant: Tenant, cid: ConversationId, brief_id: str, open_under_lock: Callable[[], AutoRun]
) -> AutoRun:
    with _LOCK:
        held = read(tenant.conversations, cid)
        if held.mode is not Mode.AUTO:
            raise RunRefused(f"the person switched this conversation to {held.mode} mode")
        current = None if held.auto_run is None else _read_if_known(tenant, held.auto_run)
        if current is not None and isinstance(current.state, Stopped):
            _write(tenant.conversations, cid, Conversation(mode=Mode.DESIGN))
            raise RunRefused(
                f"auto run {current.run_id} has stopped, so this conversation moved to Design "
                "mode; only the person can start a new Auto run"
            )
        if (
            current is not None
            and isinstance(current.state, Running)
            and current.state.start.brief_id != brief_id
        ):
            raise RunRefused(
                f"this conversation already has Auto run {current.run_id} on brief "
                f"{current.state.start.brief_id}; call auto_ask to stop it first"
            )
        run = open_under_lock()
        held = (
            Conversation(mode=Mode.AUTO, auto_run=run.run_id)
            if isinstance(run.state, Running)
            else Conversation(mode=Mode.DESIGN)
        )
        _write(tenant.conversations, cid, held)
        return run


def _switch(tenant: Tenant, cid: ConversationId, mode: Mode) -> Conversation:
    held = read(tenant.conversations, cid)
    if mode is Mode.AUTO and held.mode is Mode.AUTO:
        return held
    if held.auto_run is not None and _read_if_known(tenant, held.auto_run) is not None:
        log.stop_by_person(tenant.roots, held.auto_run)
    return _write(tenant.conversations, cid, Conversation(mode=mode))


def _read_if_known(tenant: Tenant, run_id: str) -> AutoRun | None:
    try:
        return log.read_run(tenant.roots, run_id)
    except UnknownRun:
        return None


def _write(directory: Path, cid: ConversationId, held: Conversation) -> Conversation:
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".{cid}-{secrets.token_hex(8)}.tmp"
    try:
        temporary.write_text(json.dumps(held.model_dump(mode="json")))
        os.replace(temporary, directory / f"{cid}.json")
    finally:
        temporary.unlink(missing_ok=True)
    return held
