import asyncio
import json
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

import anyio.to_thread
import httpx2
import pytest

from cad.accounts.principal import AccountId
from cad.chat.log import Answered, Channel, DriverSaid, Event, transcript_path
from cad.chat.model import Message, Model, ToolSpec
from cad.chat.scripted import Scripted, Step
from cad.confirmations.answers import Ledger, read_ledger
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.conversations import store
from cad.conversations.model import ConversationId
from cad.operations import confirmation
from cad.operations.tenants import Tenants
from cad.projects.model import ProjectId
from tests.support.chat import ALICE, TEXT, Chat, call, script, step
from tests.support.conversations import briefless_run_in
from tests.support.rows import UNDER_150

pytestmark = pytest.mark.anyio

PROJECT = "${create_brief.project_id}"


def asked(**joined: str) -> list[Step]:
    """A turn that builds first: store the brief, propose, ask, end the message while it waits."""
    return [
        step("Storing the brief.", call("create_brief", **joined)),
        step(
            "Proposing.",
            call(
                "propose_requirements",
                brief_id="${create_brief.brief_id}",
                requirements=[UNDER_150],
            ),
        ),
        step("Asking you to confirm.", call("ask_to_confirm", project_id=PROJECT)),
        step("Answer it on the page."),
    ]


@dataclass
class Pages:
    """The door's opener: counts each page the agent's ask_to_confirm opens."""

    opened: threading.Event = field(default_factory=threading.Event)
    count: int = 0

    def __call__(self, account: AccountId, project: ProjectId) -> None:
        del account, project
        self.count += 1
        self.opened.set()


@dataclass(frozen=True)
class Gated:
    """A scripted model that holds step `at` until the test opens the gate."""

    inner: Scripted
    at: int
    gate: asyncio.Event

    async def reply(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        searches_spent: int,
    ) -> Message:
        if sum(one.role == "assistant" for one in messages) == self.at:
            await self.gate.wait()
        return await self.inner.reply(system, messages, tools, searches_spent)


@pytest.fixture
def pages() -> Pages:
    return Pages()


@pytest.fixture
def chat_tenants(tmp_path: Path, pages: Pages) -> Tenants:
    return Tenants(tmp_path / "accounts", 600, Door(open_page=pages, wait_seconds=1.0), ingest)


@pytest.fixture
def model() -> Model:
    return script(*asked(), step("Building it now."))


def hold(chat: Chat, cid: str) -> str:
    tenant = chat.tenants.of(AccountId(ALICE))
    run_id = briefless_run_in(chat.tenants, AccountId(ALICE), ConversationId(cid))
    store.stop_by_person(tenant.roots, tenant.conversations, run_id)
    return run_id


def stopped_run(chat: Chat, cid: str) -> str | None:
    conversations = chat.tenants.of(AccountId(ALICE)).conversations
    return store.read(conversations, ConversationId(cid)).stopped_run


def project_of(events: Sequence[Any]) -> str:
    created = next(one for one in events if one["kind"] == "tool_result")
    return json.loads(created["text"])["project_id"]


def kinds(events: Sequence[Any]) -> list[str]:
    return [one["kind"] for one in events]


async def waiting(chat: Chat, client: httpx2.AsyncClient, text: str = TEXT) -> str:
    """A conversation whose agent asked, got pending, and ended its turn."""
    cid = await chat.conversation(client)
    await chat.say(client, cid, text)
    await chat.finish()
    return cid


async def answer(chat: Chat, client: httpx2.AsyncClient, cid: str, verdict: str = "confirm") -> int:
    project = project_of(await chat.events(client, cid))
    body = await chat.page_form(client, project, verdict, "thinner please")
    return await chat.post_page(client, project, body)


async def test_a_page_answer_starts_one_turn_with_no_message(
    chat: Chat,
) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        before = len(await chat.events(client, cid))
        assert await answer(chat, client, cid) == 200
        await chat.finish()
        after = (await chat.events(client, cid))[before:]
    assert kinds(after) == ["driver", "agent", "turn_ended"]
    assert after[0]["answered"]["through"] == 1
    assert "confirmed 1 and declined 0" in after[0]["text"]
    assert '"thinner please"' in after[0]["text"]
    assert "with no rebuild" in after[0]["text"]
    assert "http" not in after[0]["text"]
    assert after[1]["text"] == "Building it now."


async def test_a_page_answer_lifts_the_stop_that_holds_the_conversation(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        run_id = hold(chat, cid)
        assert stopped_run(chat, cid) == run_id
        assert await answer(chat, client, cid) == 200
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(events)[-3:] == ["driver", "agent", "turn_ended"]
    assert stopped_run(chat, cid) is None


class Crash(Exception):
    pass


async def test_a_crash_once_the_persons_message_is_recorded_leaves_no_hold(
    chat: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = Channel.append

    def append_then_crash(channel: Channel, event: Event) -> NoReturn:
        real(channel, event)
        raise Crash

    async with chat.client() as client:
        cid = await chat.conversation(client)
        hold(chat, cid)
        monkeypatch.setattr(Channel, "append", append_then_crash)
        with pytest.raises(Crash):
            await chat.say(client, cid, "try again")
    assert stopped_run(chat, cid) is None


async def test_a_replayed_answer_starts_no_second_turn(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        project = project_of(await chat.events(client, cid))
        body = await chat.page_form(client, project, "confirm")
        assert await chat.post_page(client, project, body) == 200
        await chat.finish()
        assert await chat.post_page(client, project, body) == 409
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(events).count("driver") == 1
    assert kinds(events).count("turn_ended") == 2


async def test_a_declined_answer_wakes_the_agent_and_keeps_what_it_built(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        assert await answer(chat, client, cid, "decline") == 200
        await chat.finish()
        events = await chat.events(client, cid)
    driver = next(one for one in events if one["kind"] == "driver")
    assert "confirmed 0 and declined 1" in driver["text"]
    assert "Nothing you built is gone" in driver["text"]
    assert kinds(events)[-1] == "turn_ended"


async def test_an_answer_during_a_turn_starts_one_follow_up_after_it(chat: Chat) -> None:
    gate = asyncio.Event()
    async with chat.client() as client:
        cid = await waiting(chat, client)
        steps = (*asked(), step("Noted the colour."), step("Building it now."))
        chat.app.state.chat.model = Gated(script(*steps), at=4, gate=gate)
        await chat.say(client, cid, "and make it blue")
        assert await answer(chat, client, cid) == 200
        assert "driver" not in kinds(await chat.events(client, cid))
        gate.set()
        await chat.finish()
        events = await chat.events(client, cid)
    tail = [(one["kind"], one.get("text", "")[:17]) for one in events[-6:]]
    assert tail == [
        ("user", "and make it blue"),
        ("agent", "Noted the colour."),
        ("turn_ended", ""),
        ("driver", "The person answer"),
        ("agent", "Building it now."),
        ("turn_ended", ""),
    ]


async def test_an_answer_the_turns_own_ask_sees_starts_no_follow_up(
    chat: Chat, pages: Pages
) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        steps = (*asked(), step("Asking again.", call("ask_to_confirm", project_id=PROJECT)))
        chat.app.state.chat.model = script(*steps, step("Confirmed, building."))
        pages.opened.clear()
        await chat.say(client, cid, "check again")
        await anyio.to_thread.run_sync(pages.opened.wait)
        assert await answer(chat, client, cid) == 200
        await chat.finish()
        events = await chat.events(client, cid)
    results = [json.loads(one["text"]) for one in events if one["kind"] == "tool_result"]
    assert (results[-1]["status"], results[-1]["answers_recorded"]) == ("answered", 1)
    assert "driver" not in kinds(events)
    assert kinds(events).count("turn_ended") == 2


async def test_an_answer_between_the_count_and_the_items_still_ends_the_wait(
    chat: Chat, pages: Pages, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_read = [True]

    def before_the_answer(projects: Path, project: ProjectId) -> Ledger:
        held = read_ledger(projects, project)
        if first_read[0]:
            first_read[0] = False
            return Ledger(held.answers[:-1])
        return held

    async with chat.client() as client:
        cid = await waiting(chat, client)
        steps = (*asked(), step("Asking again.", call("ask_to_confirm", project_id=PROJECT)))
        chat.app.state.chat.model = script(*steps, step("Confirmed, building."))
        pages.opened.clear()
        await chat.say(client, cid, "check again")
        await anyio.to_thread.run_sync(pages.opened.wait)
        monkeypatch.setattr(confirmation, "read_ledger", before_the_answer)
        assert await answer(chat, client, cid) == 200
        await chat.finish()
        events = await chat.events(client, cid)
    result = json.loads([one for one in events if one["kind"] == "tool_result"][-1]["text"])
    assert (result["status"], result["answers_recorded"]) == ("answered", 1)


async def test_a_delivery_a_restart_cut_off_runs_once_when_the_conversation_opens(
    chat: Chat, restarted: Chat
) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        project = project_of(await chat.events(client, cid))
    conversations = chat.tenants.of(AccountId(ALICE)).conversations
    Channel(transcript_path(conversations, ConversationId(cid))).append(
        DriverSaid(text="answered", answered=Answered(project_id=project, through=1))
    )
    async with restarted.client() as client:
        await restarted.events(client, cid)
        await restarted.finish()
        await restarted.events(client, cid)
        await restarted.finish()
        events = await restarted.events(client, cid)
    assert kinds(events)[-3:] == ["driver", "agent", "turn_ended"]
    assert kinds(events).count("turn_ended") == 2


async def test_a_restart_rerunning_a_delivery_keeps_a_stop_pressed_after_it(
    chat: Chat, restarted: Chat
) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        project = project_of(await chat.events(client, cid))
    conversations = chat.tenants.of(AccountId(ALICE)).conversations
    Channel(transcript_path(conversations, ConversationId(cid))).append(
        DriverSaid(text="answered", answered=Answered(project_id=project, through=1))
    )
    run_id = hold(chat, cid)
    async with restarted.client() as client:
        await restarted.events(client, cid)
        await restarted.finish()
        events = await restarted.events(client, cid)
    assert kinds(events)[-4:] == ["driver", "stop_report", "agent", "turn_ended"]
    assert stopped_run(restarted, cid) == run_id


async def test_after_a_restart_an_answer_is_told_once_when_the_conversation_opens(
    chat: Chat, restarted: Chat
) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
    async with restarted.client() as client:
        assert await answer(restarted, client, cid) == 200
        await restarted.finish()
        await restarted.events(client, cid)
        await restarted.finish()
        events = await restarted.events(client, cid)
    assert kinds(events).count("driver") == 1
    assert kinds(events)[-3:] == ["driver", "agent", "turn_ended"]


async def test_after_a_restart_a_conversation_already_told_starts_nothing(
    chat: Chat, restarted: Chat
) -> None:
    async with chat.client() as client:
        cid = await waiting(chat, client)
        assert await answer(chat, client, cid) == 200
        await chat.finish()
        told = await chat.events(client, cid)
    async with restarted.client() as client:
        await restarted.events(client, cid)
        await restarted.finish()
        events = await restarted.events(client, cid)
    assert events == told
