import json
import os
import secrets
import threading
from dataclasses import replace
from pathlib import Path
from typing import Final

from cad.auto import log
from cad.auto.model import AutoRun, Running, RunRefused, UnknownRun
from cad.conversations.model import Conversation, ConversationId, Mode
from cad.operations.model import Tenant

_LOCK: Final = threading.Lock()


def read(directory: Path, cid: ConversationId) -> Conversation:
    try:
        return Conversation.model_validate_json((directory / f"{cid}.json").read_bytes())
    except FileNotFoundError:
        return Conversation()


def bind(tenant: Tenant, cid: ConversationId | None) -> Tenant:
    if cid is None:
        return tenant
    held = read(tenant.conversations, cid)
    return replace(
        tenant,
        conversation=cid,
        mode=held.mode,
        auto_run=held.auto_run if held.mode is Mode.AUTO else None,
    )


def set_mode(tenant: Tenant, cid: ConversationId, mode: Mode) -> Conversation:
    with _LOCK:
        held = read(tenant.conversations, cid)
        if mode is Mode.AUTO and held.mode is Mode.AUTO:
            return held
        if held.auto_run is not None and _read_if_known(tenant, held.auto_run) is not None:
            log.stop_by_person(tenant.roots, held.auto_run)
        return _write(tenant.conversations, cid, Conversation(mode=mode))


def attach_run(tenant: Tenant, cid: ConversationId, run_id: str) -> AutoRun:
    with _LOCK:
        held = read(tenant.conversations, cid)
        if held.mode is not Mode.AUTO:
            return log.stop_by_person(tenant.roots, run_id)
        if held.auto_run is not None and held.auto_run != run_id:
            other = _read_if_known(tenant, held.auto_run)
            if other is not None and isinstance(other.state, Running):
                raise RunRefused(
                    f"this conversation already has Auto run {other.run_id} on brief "
                    f"{other.state.start.brief_id}; call auto_ask to stop it first"
                )
        _write(tenant.conversations, cid, Conversation(mode=Mode.AUTO, auto_run=run_id))
        return log.read_run(tenant.roots, run_id)


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
