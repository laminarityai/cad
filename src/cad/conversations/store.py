import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Final

from cad.auto import log
from cad.auto.model import AutoRun, PersonStopped, Running, RunRefused, Stopped, UnknownRun
from cad.conversations.model import Conversation, ConversationId, Mode, UnknownConversation
from cad.records import files
from cad.records.roots import Roots

_LOCK: Final = threading.RLock()


def read(directory: Path, cid: ConversationId) -> Conversation:
    """The one lookup of a conversation. `directory` is one account's partition, so another
    account's conversation id is unknown here, the same as an id nobody made."""
    try:
        return Conversation.model_validate_json((directory / f"{cid}.json").read_bytes())
    except FileNotFoundError:
        raise UnknownConversation(f"no conversation {cid} in this account") from None


def create(
    directory: Path, cid: ConversationId, project_id: str | None = None, brief_id: str | None = None
) -> Conversation:
    with _LOCK:
        held = Conversation(project_id=project_id, brief_id=brief_id)
        return _write(directory, cid, held)


def of_project(directory: Path, project_id: str) -> ConversationId | None:
    found = [
        (path.stat().st_mtime, cid)
        for path in directory.glob("c_*.json")
        if read(directory, cid := ConversationId(path.stem)).project_id == project_id
    ]
    return max(found)[1] if found else None


def started(directory: Path, cid: ConversationId, project_id: str) -> None:
    with _LOCK:
        try:
            held = read(directory, cid)
        except UnknownConversation:
            return
        if held.project_id is None:
            _write(directory, cid, held.model_copy(update={"project_id": project_id}))


def set_mode(roots: Roots, directory: Path, cid: ConversationId, mode: Mode) -> Conversation:
    with _LOCK:
        return _switch(roots, directory, cid, mode)


def confirmed(directory: Path, cid: ConversationId) -> Conversation:
    """The conversation was just told that the person confirmed requirements. Plan ends there, and
    Design and Auto stay as they are. Callers call it once per told answer, so a later switch back
    to Plan stands until the person confirms again."""
    with _LOCK:
        held = read(directory, cid)
        if held.mode is not Mode.PLAN:
            return held
        return _write(directory, cid, held.moved(Mode.DESIGN))


def record_event(roots: Roots, directory: Path, run_id: str, make: log.Make) -> AutoRun:
    """Every record of a run goes through here. A run that is stopped after it, by any reason,
    takes its conversation out of Auto mode, to Design, when it is the conversation's current
    run (ADR-0010). It also does so for a run already stopped, so a crash between the stop and
    the write heals on the next call. A stopped earlier run leaves a conversation that moved on."""
    with _LOCK:
        run = log.append_event(roots, run_id, make)
        if isinstance(run.state, Stopped):
            cid = run.state.start.conversation
            held = read(directory, cid)
            if held.auto_run == run_id:
                _write(directory, cid, held.moved(Mode.DESIGN))
        return run


def stop_by_person(roots: Roots, directory: Path, run_id: str) -> tuple[AutoRun, Conversation]:
    run = record_event(roots, directory, run_id, lambda _: PersonStopped())
    return run, read(directory, run.state.start.conversation)


def start_run(
    roots: Roots,
    directory: Path,
    cid: ConversationId,
    brief_id: str,
    open_under_lock: Callable[[], AutoRun],
) -> AutoRun:
    with _LOCK:
        held = read(directory, cid)
        if held.mode is not Mode.AUTO:
            raise RunRefused(f"the person switched this conversation to {held.mode} mode")
        current = None if held.auto_run is None else _read_if_known(roots, held.auto_run)
        if current is not None and isinstance(current.state, Stopped):
            _write(directory, cid, held.moved(Mode.DESIGN))
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
        running = isinstance(run.state, Running)
        moved = held.moved(Mode.AUTO, run.run_id) if running else held.moved(Mode.DESIGN)
        _write(directory, cid, moved.model_copy(update={"last_run": run.run_id}))
        return run


def last_run(roots: Roots, held: Conversation) -> AutoRun | None:
    return None if held.last_run is None else _read_if_known(roots, held.last_run)


def _switch(roots: Roots, directory: Path, cid: ConversationId, mode: Mode) -> Conversation:
    held = read(directory, cid)
    if mode is Mode.AUTO and held.mode is Mode.AUTO:
        return held
    if held.auto_run is not None and _read_if_known(roots, held.auto_run) is not None:
        log.stop_by_person(roots, held.auto_run)
    return _write(directory, cid, held.moved(mode))


def _read_if_known(roots: Roots, run_id: str) -> AutoRun | None:
    try:
        return log.read_run(roots, run_id)
    except UnknownRun:
        return None


def _write(directory: Path, cid: ConversationId, held: Conversation) -> Conversation:
    directory.mkdir(parents=True, exist_ok=True)
    files.replace(directory / f"{cid}.json", json.dumps(held.model_dump(mode="json")).encode())
    return held
