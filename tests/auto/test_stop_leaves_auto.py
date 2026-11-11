from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.auto import log
from cad.auto.model import Asked, Event, PersonStopped, Running, Stopped
from cad.conversations import store
from cad.conversations.model import Conversation, Mode
from tests.support.auto_session import TEXT, UNDER_150, running

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio


def asked(_: Running) -> Event:
    return Asked(note="stuck")


async def test_the_persons_stop_leaves_auto_like_every_other_stop(s: Session) -> None:
    brief_id, run_id = await running(s)
    stopped, held = store.stop_by_person(s.tenant.roots, s.tenant.conversations, run_id)
    assert isinstance(stopped.state, Stopped)
    assert (held.mode, held.auto_run, held.last_run) == (Mode.DESIGN, None, run_id)
    await s.left_auto(brief_id, run_id)


async def test_a_replayed_stop_records_nothing_and_leaves_the_mode(s: Session) -> None:
    _, run_id = await running(s)
    store.record_event(s.tenant.roots, s.tenant.conversations, run_id, asked)
    before = len(log.read_events(s.roots, run_id))
    store.set_mode(s.tenant.roots, s.tenant.conversations, s.conversation, Mode.AUTO)
    for _ in range(2):
        store.record_event(s.tenant.roots, s.tenant.conversations, run_id, asked)
        store.record_event(
            s.tenant.roots, s.tenant.conversations, run_id, lambda _: PersonStopped()
        )
    assert len(log.read_events(s.roots, run_id)) == before
    held = store.read(s.tenant.conversations, s.conversation)
    assert (held.mode, held.auto_run) == (Mode.AUTO, None)


async def test_the_stop_of_an_earlier_run_does_not_change_a_conversation_that_moved_on(
    s: Session,
) -> None:
    brief_id, earlier = await running(s)
    other = await s.confirmed(TEXT, UNDER_150)
    store.set_mode(s.tenant.roots, s.tenant.conversations, s.conversation, Mode.DESIGN)
    store.set_mode(s.tenant.roots, s.tenant.conversations, s.conversation, Mode.AUTO)
    current = (
        await s.start(
            brief_id=other,
            material_key="prusament-pla",
            material_reason="PLA is light and prints easily",
        )
    ).run_id
    assert current != earlier
    assert isinstance(s.run(earlier).state, Stopped)
    store.record_event(s.tenant.roots, s.tenant.conversations, earlier, asked)
    store.stop_by_person(s.tenant.roots, s.tenant.conversations, earlier)
    held = store.read(s.tenant.conversations, s.conversation)
    assert (held.mode, held.auto_run, held.last_run) == (Mode.AUTO, current, current)
    assert isinstance(s.run(current).state, Running)
    assert brief_id != other


async def test_a_stop_recorded_before_the_conversation_moved_is_finished_by_the_next_call(
    s: Session,
) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    assert store.read(s.tenant.conversations, s.conversation).mode is Mode.AUTO
    store.record_event(s.tenant.roots, s.tenant.conversations, run_id, asked)
    await s.left_auto(brief_id, run_id)


async def test_a_start_after_a_stop_recorded_before_the_conversation_moved_is_refused(
    s: Session,
) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    text = await s.refusal(
        "auto_start",
        brief_id=brief_id,
        material_key="prusament-pla",
        material_reason="PLA is light and prints easily",
    )
    assert f"auto run {run_id} has stopped" in text, text
    await s.left_auto(brief_id, run_id)


async def test_a_conversation_left_in_auto_on_a_stopped_run_refuses_a_start(s: Session) -> None:
    brief_id, run_id = await running(s)
    log.append_event(s.roots, run_id, asked)
    stuck = Conversation(mode=Mode.AUTO, auto_run=run_id)
    (s.tenant.conversations / f"{s.conversation}.json").write_text(stuck.model_dump_json())
    store.set_mode(s.tenant.roots, s.tenant.conversations, s.conversation, Mode.AUTO)
    text = await s.refusal(
        "auto_start",
        brief_id=brief_id,
        material_key="prusament-pla",
        material_reason="PLA is light and prints easily",
    )
    assert f"auto run {run_id} has stopped" in text, text
    await s.left_auto(brief_id, run_id)
