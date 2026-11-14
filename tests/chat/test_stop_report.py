"""The person's Stop shows its report in the chat when the stop is recorded, once per run."""

import asyncio
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import httpx2
import pytest

from cad.auto.step import STILL_RUNNING
from cad.chat.model import Model
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import SetRefused
from tests.support.auto_chat import RUN, confirmed, kinds, run_of
from tests.support.chat import JSON, TEXT, Chat, call, script, step

pytestmark = pytest.mark.anyio

PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
WAIT_SECONDS: Final = 10


@dataclass
class SlowBuild:
    """A build that runs until the test lets it return, then is refused by its set."""

    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)

    def __call__(self, *_: object, **__: object) -> Any:
        self.entered.set()
        assert self.release.wait(WAIT_SECONDS), "the test never let the build return"
        raise SetRefused("the set took no more options")

    async def running(self) -> None:
        assert await asyncio.to_thread(self.entered.wait, WAIT_SECONDS), "the build never started"


@pytest.fixture
def build(monkeypatch: pytest.MonkeyPatch) -> Iterator[SlowBuild]:
    slow = SlowBuild()
    monkeypatch.setattr(variant_sets, "build_into_set", slow)
    yield slow
    slow.release.set()


@pytest.fixture
def model() -> Model:
    revise = step("Revising.", call("auto_revise", run_id=RUN, code=PLATE))
    return script(*confirmed(), revise, step("Unreachable."))


async def press_stop(chat: Chat, client: httpx2.AsyncClient, cid: str) -> None:
    run_id = run_of(chat, cid).run_id
    pressed = await client.post(f"/v1/auto/{run_id}/stop", headers=JSON, content=b"{}")
    assert pressed.status_code == 200, pressed.text


def reports(events: list[Any]) -> list[Any]:
    return [one for one in events if one["kind"] == "stop_report"]


async def test_the_report_shows_at_stop_while_a_build_runs_and_its_return_adds_none(
    chat: Chat, build: SlowBuild
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await build.running()
        await press_stop(chat, client, cid)
        at_stop = await chat.events(client, cid)
        build.release.set()
        await chat.finish()
        events = await chat.events(client, cid)
    assert "turn_ended" not in kinds(at_stop)
    [shown] = reports(at_stop)
    assert shown["reason"] == "stopped_by_person"
    assert STILL_RUNNING in shown["report"]
    assert reports(events) == [shown]
    assert kinds(events)[-1] == "turn_ended"
    assert "Unreachable." not in [one.get("text") for one in events]


async def test_a_stop_with_no_turn_running_reports_once_however_often_it_is_pressed(
    chat: Chat,
) -> None:
    chat.app.state.chat.model = script(
        *confirmed(), *[step(f"Waiting {n}.") for n in range(4)], step("It stopped.")
    )
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await chat.finish()
        await press_stop(chat, client, cid)
        at_stop = await chat.events(client, cid)
        await press_stop(chat, client, cid)
        await chat.say(client, cid, "what happened?")
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(at_stop)[-1] == "stop_report"
    assert STILL_RUNNING not in at_stop[-1]["report"]
    assert len(reports(events)) == 1


async def test_a_restart_between_the_stop_and_the_builds_return_leaves_one_report(
    chat: Chat, restarted: Chat, build: SlowBuild
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await build.running()
        await press_stop(chat, client, cid)
        turns = tuple(chat.app.state.chat._turns)
        for turn in turns:
            turn.cancel()
        await asyncio.gather(*turns, return_exceptions=True)
    build.release.set()
    restarted.app.state.chat.model = script(step("It stopped."))
    async with restarted.client() as client:
        await restarted.say(client, cid, "what happened?")
        await restarted.finish()
        events = await restarted.events(client, cid)
    assert len(reports(events)) == 1
    assert kinds(events)[-2:] == ["agent", "turn_ended"]


async def test_a_report_that_cannot_be_posted_does_not_fail_the_stop_and_the_next_turn_posts_it(
    chat: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat.app.state.chat.model = script(*confirmed(), step("Waiting."), step("It stopped."))

    def unreadable(*_: object) -> Any:
        raise OSError("the transcript could not be written")

    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await chat.finish()
        with monkeypatch.context() as patched:
            patched.setattr("cad.chat.routes.stop_report", unreadable)
            await press_stop(chat, client, cid)
        at_stop = await chat.events(client, cid)
        await chat.say(client, cid, "what happened?")
        await chat.finish()
        events = await chat.events(client, cid)
    assert reports(at_stop) == []
    assert len(reports(events)) == 1
