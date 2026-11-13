import os
from collections.abc import Callable
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter, ValidationError

from cad.auto.model import (
    AutoRun,
    Event,
    Running,
    Started,
    Stopped,
    TamperedRun,
    UnknownRun,
    run_project,
)
from cad.auto.step import fold
from cad.projects.model import ProjectBusy
from cad.records import signed
from cad.records.roots import Roots, project_store

AUTO: Final = "auto"
EVENT: Final = TypeAdapter[Event](Event)

type Make = Callable[[Running], Event | None]


def run_dir(roots: Roots, run_id: str) -> Path:
    return roots.projects / run_project(run_id) / AUTO / run_id


def read_events(roots: Roots, run_id: str) -> tuple[Event, ...]:
    directory = run_dir(roots, run_id)
    if not os.path.lexists(directory):
        raise UnknownRun(f"no auto run {run_id} is stored")
    raw = signed.read_numbered(project_store(roots.projects), directory, _slot_of(run_id))
    events = None if raw is None else _parse(raw)
    if events is None:
        raise TamperedRun(_unreadable(run_id))
    return events


def read_run(roots: Roots, run_id: str) -> AutoRun:
    return AutoRun(run_id=run_id, state=fold(read_events(roots, run_id)))


def exists(roots: Roots, run_id: str) -> bool:
    return os.path.lexists(run_dir(roots, run_id))


def create_run(roots: Roots, run_id: str, started: Started) -> None:
    """Exclusive: when a concurrent start already created run_id, this writes nothing."""
    directory = run_dir(roots, run_id)
    directory.parent.mkdir(parents=True, exist_ok=True)
    first = (_slot_of(run_id)(1), signed.slot_file(1), _encode(started))
    entry = directory.relative_to(roots.projects).as_posix()
    signed.create_entry(project_store(roots.projects), entry, first, ())


def append_event(roots: Roots, run_id: str, make: Make) -> AutoRun:
    if not exists(roots, run_id):
        raise UnknownRun(f"no auto run {run_id} is stored")

    def record_for(existing: tuple[bytes, ...]) -> bytes | None:
        events = _parse(existing)
        if events is None:
            raise signed.Tampered
        state = fold(events)
        if isinstance(state, Stopped):
            return None
        event = make(state)
        return None if event is None else _encode(event)

    _append(roots, run_id, record_for)
    return read_run(roots, run_id)


def _append(
    roots: Roots, run_id: str, record_for: Callable[[tuple[bytes, ...]], bytes | None]
) -> None:
    store = project_store(roots.projects)
    try:
        signed.append(store, run_dir(roots, run_id), _slot_of(run_id), record_for)
    except signed.Tampered as error:
        raise TamperedRun(_unreadable(run_id)) from error
    except signed.Contended as error:
        raise ProjectBusy(f"auto run {run_id} is being changed concurrently; try again") from error


def _unreadable(run_id: str) -> str:
    return (
        f"auto run {run_id}'s records failed the server's integrity check, so Auto cannot go on "
        "and this chat cannot take more messages; start a new project to carry on"
    )


def _encode(event: Event) -> bytes:
    return EVENT.dump_json(event)


def _parse(raw: tuple[bytes, ...]) -> tuple[Event, ...] | None:
    try:
        return tuple(EVENT.validate_json(one) for one in raw)
    except ValidationError:
        return None


def _slot_of(run_id: str) -> Callable[[int], str]:
    return lambda number: f"{run_project(run_id)}/auto/{run_id}/{number}"
