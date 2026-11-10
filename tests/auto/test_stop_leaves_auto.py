from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.auto import log
from cad.auto.model import Asked, Event, PersonStopped, Running, Stopped
from cad.conversations import store
from cad.conversations.model import Conversation, Mode

from .test_run import TEXT, UNDER_150, running

if TYPE_CHECKING:
    from auto.conftest import Session

pytestmark = pytest.mark.anyio


def asked(_: Running) -> Event:
    return Asked(note="stuck")


async def test_the_persons_stop_leaves_auto_like_every_other_stop(s: Session) -> None:
    brief_id, run_id = await running(s)
    stopped, held = store.stop_by_person(s.tenant, run_id)
    assert isinstance(stopped.state, Stopped)
    assert held == Conversation(mode=Mode.DESIGN)
    await s.left_auto(brief_id, run_id)


async def test_a_replayed_stop_records_nothing_and_leaves_the_mode(s: Session) -> None:
    _, run_id = await running(s)
    store.record_event(s.tenant, run_id, asked)
    before = len(log.read_events(s.roots, run_id))
    store.set_mode(s.tenant, s.conversation, Mode.AUTO)
    for _ in range(2):
        store.record_event(s.tenant, run_id, asked)
        store.record_event(s.tenant, run_id, lambda _: PersonStopped())
    assert len(log.read_events(s.roots, run_id)) == before
    assert store.read(s.tenant.conversations, s.conversation) == Conversation(mode=Mode.AUTO)


async def test_the_stop_of_an_earlier_run_does_not_change_a_conversation_that_moved_on(
    s: Session,
) -> None:
    brief_id, earlier = await running(s)
    other = await s.confirmed(TEXT, UNDER_150)
    store.set_mode(s.tenant, s.conversation, Mode.PLAN)
    store.set_mode(s.tenant, s.conversation, Mode.AUTO)
    current = (await s.start(brief_id=other, material_key="prusament-pla")).run_id
    assert current != earlier
    assert isinstance(s.run(earlier).state, Stopped)
    store.record_event(s.tenant, earlier, asked)
    store.stop_by_person(s.tenant, earlier)
    assert store.read(s.tenant.conversations, s.conversation) == Conversation(
        mode=Mode.AUTO, auto_run=current
    )
    assert isinstance(s.run(current).state, Running)
    assert brief_id != other


async def test_a_stop_recorded_before_the_conversation_moved_is_finished_by_the_next_call(
    s: Session,
) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    assert store.read(s.tenant.conversations, s.conversation).mode is Mode.AUTO
    store.record_event(s.tenant, run_id, asked)
    await s.left_auto(brief_id, run_id)
