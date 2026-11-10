import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest

from cad.accounts.principal import AccountId
from cad.auto.log import read_run, run_dir
from cad.auto.model import Running, Stopped
from cad.chat.model import Message, Model, ToolSpec
from cad.chat.scripted import Step
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from tests.chat.support import ALICE, TEXT, UNDER_150, Chat, call, script, step

pytestmark = pytest.mark.anyio

PLATE: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
RUN: Final = "${auto_start.run_id}"


def confirmed() -> list[Step]:
    return [
        step("Storing the brief.", call("create_brief", text=TEXT)),
        step(
            "Proposing requirements.",
            call(
                "propose_requirements",
                brief_id="${create_brief.brief_id}",
                requirements=[UNDER_150],
            ),
        ),
        step(
            "Asking you to confirm.",
            call("ask_to_confirm", project_id="${create_brief.project_id}"),
        ),
        step(
            "Starting the run.",
            call("auto_start", brief_id="${create_brief.brief_id}", material_key="prusament-pla"),
        ),
    ]


def auto(chat: Chat, cid: str) -> None:
    store.set_mode(chat.tenants.of(AccountId(ALICE)), ConversationId(cid), Mode.AUTO)


def run_of(chat: Chat, cid: str) -> Any:
    """The run auto_start returned in this conversation, since a stop clears the held run."""
    tenant = chat.tenants.of(AccountId(ALICE))
    channel = chat.app.state.chat.channels.of(
        AccountId(ALICE), tenant.conversations, ConversationId(cid)
    )
    events = channel.events()
    started = next(one.call_id for one in events if getattr(one, "name", None) == "auto_start")
    returned = next(one for one in events if one.kind == "tool_result" and one.call_id == started)
    return read_run(tenant.roots, json.loads(returned.text)["run_id"])


def kinds(events: Sequence[Any]) -> list[str]:
    return [one["kind"] for one in events]


@pytest.fixture
def model() -> Model:
    return script(
        *confirmed(),
        step("I am stuck.", call("auto_ask", run_id=RUN, note="which material?")),
        step("Unreachable."),
    )


async def test_a_run_the_agent_stops_is_reported_from_the_signed_log_and_ends_the_turn(
    chat: Chat,
) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        events = await chat.events(client, cid)
    run = run_of(chat, cid)
    assert isinstance(run.state, Stopped)
    assert kinds(events)[-2:] == ["stop_report", "turn_ended"]
    report = events[-2]
    assert (report["run_id"], report["reason"]) == (run.run_id, "needs_person")
    assert report["report"] == run.state.report
    assert "Unreachable." not in [one.get("text") for one in events]


async def test_a_call_after_the_run_stopped_is_refused_by_the_server(chat: Chat) -> None:
    chat.app.state.chat.model = script(
        *confirmed(),
        step("Stuck.", call("auto_ask", run_id=RUN, note="which material?")),
        step("Trying anyway.", call("auto_revise", run_id=RUN, code=PLATE)),
        step("It was refused."),
    )
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        await chat.say(client, cid, "try again")
        await chat.finish()
        events = await chat.events(client, cid)
    refused = [one for one in events if one["kind"] == "tool_result" and one["is_error"]]
    assert len(refused) == 1
    assert any(word in refused[0]["text"] for word in ("RunStopped", "RunNotHeld"))
    assert kinds(events).count("stop_report") == 1


async def test_a_run_that_passes_every_checked_requirement_stops_with_all_pass(
    chat: Chat,
) -> None:
    revise = step("Revising.", call("auto_revise", run_id=RUN, code=PLATE))
    chat.app.state.chat.model = script(*confirmed(), revise, revise, revise)
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        events = await chat.events(client, cid)
    assert isinstance(run_of(chat, cid).state, Stopped)
    assert kinds(events)[-2:] == ["stop_report", "turn_ended"]
    assert events[-2]["reason"] == "all_pass"


@dataclass
class PressesStop:
    inner: Model
    chat: Chat
    cid: str
    after: int
    pressed: bool = False

    async def reply(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Message:
        if not self.pressed and sum(one.role == "assistant" for one in messages) == self.after:
            self.pressed = True
            tenant = self.chat.tenants.of(AccountId(ALICE))
            held = store.read(tenant.conversations, ConversationId(self.cid))
            assert held.auto_run is not None
            store.stop_by_person(tenant, held.auto_run)
        return await self.inner.reply(system, messages, tools)


async def test_the_persons_stop_during_a_turn_refuses_the_next_call_and_is_reported(
    chat: Chat,
) -> None:
    revise = step("Revising.", call("auto_revise", run_id=RUN, code=PLATE))
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        chat.app.state.chat.model = PressesStop(
            script(*confirmed(), revise, revise), chat, cid, after=4
        )
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        events = await chat.events(client, cid)
    held = store.read(chat.tenants.of(AccountId(ALICE)).conversations, ConversationId(cid))
    assert held.mode is Mode.DESIGN
    assert events[-2]["kind"] == "stop_report"
    assert events[-2]["reason"] == "stopped_by_person"
    assert [one["is_error"] for one in events if one["kind"] == "tool_result"][-1] is True


async def test_an_agent_that_ends_its_message_with_the_run_going_is_reminded_a_few_times(
    chat: Chat,
) -> None:
    chat.app.state.chat.model = script(*confirmed(), *[step(f"Done {n}.") for n in range(8)])
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(events).count("driver") == 3
    assert "turn_failed" not in kinds(events)
    assert kinds(events)[-1] == "turn_ended"
    assert isinstance(run_of(chat, cid).state, Running)


async def test_a_reminder_is_followed_by_the_agents_next_step(chat: Chat) -> None:
    chat.app.state.chat.model = script(
        *confirmed(),
        step("I think that is it."),
        step("Stopping.", call("auto_ask", run_id=RUN, note="finished?")),
    )
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        events = await chat.events(client, cid)
    assert "driver" in kinds(events)
    assert kinds(events)[-2:] == ["stop_report", "turn_ended"]


async def test_design_mode_gets_no_reminder_and_no_report(chat: Chat) -> None:
    chat.app.state.chat.model = script(step("Hello."))
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, "hi")
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(events) == ["user", "agent", "turn_ended"]


def stop(chat: Chat, cid: str) -> None:
    tenant = chat.tenants.of(AccountId(ALICE))
    held = store.read(tenant.conversations, ConversationId(cid))
    assert held.auto_run is not None
    store.stop_by_person(tenant, held.auto_run)


async def test_the_persons_stop_during_a_text_only_reply_is_reported_once(chat: Chat) -> None:
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        chat.app.state.chat.model = PressesStop(
            script(*confirmed(), step("All good, done."), step("Hello again.")), chat, cid, after=4
        )
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        first = await chat.events(client, cid)
        await chat.say(client, cid, "thanks")
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(first)[-3:] == ["agent", "stop_report", "turn_ended"]
    assert first[-2]["reason"] == "stopped_by_person"
    assert kinds(events).count("stop_report") == 1


async def test_a_stop_pressed_between_turns_is_reported_when_the_next_turn_starts(
    chat: Chat,
) -> None:
    chat.app.state.chat.model = script(
        *confirmed(), *[step(f"Waiting {n}.") for n in range(4)], step("Hello."), step("Again.")
    )
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        assert "stop_report" not in kinds(await chat.events(client, cid))
        run_id = run_of(chat, cid).run_id
        stop(chat, cid)
        seen = await chat.say(client, cid, "what happened?")
        await chat.finish()
        second = await chat.events(client, cid, after=seen)
        await chat.say(client, cid, "and now?")
        await chat.finish()
        events = await chat.events(client, cid)
    assert kinds(second)[0] == "stop_report"
    assert (second[0]["run_id"], second[0]["reason"]) == (run_id, "stopped_by_person")
    assert kinds(events).count("stop_report") == 1


async def test_a_run_of_another_conversation_is_never_reported_here(chat: Chat) -> None:
    async with chat.client() as client:
        theirs = await chat.conversation(client)
        auto(chat, theirs)
        await chat.say(client, theirs, "build me a plate")
        await chat.finish()
        run = run_of(chat, theirs)
        assert isinstance(run.state, Stopped)
        chat.app.state.chat.model = script(
            step("Driving it.", call("auto_revise", run_id=run.run_id, code=PLATE)),
            step("It was refused."),
        )
        mine = await chat.conversation(client)
        await chat.say(client, mine, "revise that run")
        await chat.finish()
        events = await chat.events(client, mine)
    assert [one["is_error"] for one in events if one["kind"] == "tool_result"] == [True]
    assert "stop_report" not in kinds(events)


async def test_a_tampered_run_log_fails_the_turn_with_a_message_that_names_it(
    chat: Chat,
) -> None:
    chat.app.state.chat.model = script(*confirmed(), *[step(f"Waiting {n}.") for n in range(4)])
    async with chat.client() as client:
        cid = await chat.conversation(client)
        auto(chat, cid)
        await chat.say(client, cid, "build me a plate")
        await chat.finish()
        tenant = chat.tenants.of(AccountId(ALICE))
        run_id = run_of(chat, cid).run_id
        for record in sorted(run_dir(tenant.roots, run_id).iterdir()):
            if record.is_file():
                record.write_bytes(record.read_bytes() + b"tampered")
        seen = await chat.say(client, cid, "go on")
        await chat.finish()
        events = await chat.events(client, cid, after=seen)
    assert kinds(events) == ["turn_failed", "turn_ended"]
    assert run_id in events[0]["message"]
    assert "cannot be read" in events[0]["message"]
