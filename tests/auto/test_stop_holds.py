from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from cad.auto import log
from cad.auto.model import Asked, Event, PersonStopped, Running, Stopped
from cad.conversations import store
from cad.conversations.model import Conversation
from tests.support.auto_session import PLA_CHOICE, TEXT, UNDER_150, running

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio


def asked(_: Running) -> Event:
    return Asked(note="stuck")


def hold(s: Session) -> tuple[str | None, str | None, str | None]:
    held = store.read(s.tenant.conversations, s.conversation)
    return held.auto_run, held.stopped_run, held.last_run


async def test_the_persons_stop_holds_the_conversation_like_every_other_stop(s: Session) -> None:
    brief_id, run_id = await running(s)
    stopped, held = store.stop_by_person(s.tenant.roots, s.tenant.conversations, run_id)
    assert isinstance(stopped.state, Stopped)
    assert (held.auto_run, held.stopped_run, held.last_run) == (None, run_id, run_id)
    await s.held(brief_id, run_id)


async def test_a_replayed_stop_records_nothing_and_keeps_the_hold(s: Session) -> None:
    _, run_id = await running(s)
    store.record_event(s.tenant.roots, s.tenant.conversations, run_id, asked)
    before = len(log.read_events(s.roots, run_id))
    for _ in range(2):
        store.record_event(s.tenant.roots, s.tenant.conversations, run_id, asked)
        store.record_event(
            s.tenant.roots, s.tenant.conversations, run_id, lambda _: PersonStopped()
        )
    assert len(log.read_events(s.roots, run_id)) == before
    assert hold(s) == (None, run_id, run_id)


async def test_the_stop_of_an_earlier_run_does_not_change_a_conversation_that_moved_on(
    s: Session,
) -> None:
    brief_id, earlier = await running(s)
    await s.call("auto_ask", run_id=earlier, note="stuck")
    other = await s.confirmed(TEXT, UNDER_150)
    s.person_acts()
    current = (await s.start(brief_id=other, **PLA_CHOICE)).run_id
    assert current != earlier
    store.record_event(s.tenant.roots, s.tenant.conversations, earlier, asked)
    store.stop_by_person(s.tenant.roots, s.tenant.conversations, earlier)
    assert hold(s) == (current, None, current)
    assert isinstance(s.run(current).state, Running)
    assert brief_id != other


async def test_a_stop_recorded_before_the_conversation_was_written_is_finished_by_the_next_call(
    s: Session,
) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    assert hold(s) == (run_id, None, run_id)
    store.record_event(s.tenant.roots, s.tenant.conversations, run_id, asked)
    await s.held(brief_id, run_id)


async def test_a_start_after_a_stop_recorded_before_the_conversation_was_written_is_refused(
    s: Session,
) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    text = await s.refusal("auto_start", brief_id=brief_id, **PLA_CHOICE)
    assert f"auto run {run_id} has stopped" in text, text
    await s.held(brief_id, run_id)


async def test_a_build_after_a_stop_recorded_before_the_conversation_was_written_is_refused(
    s: Session, started: list[str]
) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    text = await s.refusal("build_variant", code="result = None", brief_id=brief_id)
    assert f"RunStopped: auto run {run_id} has stopped" in text, text
    assert started == []
    await s.held(brief_id, run_id)


async def test_the_person_acting_after_such_a_stop_lifts_it_and_a_run_starts(s: Session) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    s.person_acts()
    assert hold(s) == (None, None, run_id)
    again = await s.start(brief_id=brief_id, **PLA_CHOICE)
    assert again.run_id != run_id
    assert hold(s) == (again.run_id, None, again.run_id)


async def test_the_person_acting_with_no_stop_keeps_the_running_run(s: Session) -> None:
    _, run_id = await running(s)
    s.person_acts()
    assert hold(s) == (run_id, None, run_id)
    assert isinstance(s.run(run_id).state, Running)


async def test_an_old_record_left_on_a_stopped_run_refuses_a_start(s: Session) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    stuck = {"mode": "auto", **Conversation(auto_run=run_id).model_dump(mode="json")}
    (s.tenant.conversations / f"{s.conversation}.json").write_text(json.dumps(stuck))
    text = await s.refusal("auto_start", brief_id=brief_id, **PLA_CHOICE)
    assert f"auto run {run_id} has stopped" in text, text
    await s.held(brief_id, run_id)
