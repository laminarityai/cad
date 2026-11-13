import json
from typing import Any

import pytest

from cad.accounts.principal import AccountId
from cad.auto.log import read_run, run_dir
from tests.support.auto_chat import RUN, confirmed, kinds, run_of
from tests.support.chat import ALICE, TEXT, UNDER_150, Chat, call, script, step

pytestmark = pytest.mark.anyio


async def test_a_run_damaged_after_its_report_leaves_the_chat_working_and_a_new_brief_runs(
    chat: Chat,
) -> None:
    start = {"material_key": "prusament-pla", "material_reason": "PLA is light and prints easily"}
    chat.app.state.chat.model = script(
        *confirmed(),
        step("Stuck.", call("auto_ask", run_id=RUN, note="which material?")),
        step("Starting again.", call("auto_start", brief_id="${create_brief.brief_id}", **start)),
        step("Told the person."),
        step("Third message answered."),
        step("A new brief.", call("create_brief")),
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
        step("Auto on it.", call("auto_start", brief_id="${create_brief.brief_id}", **start)),
        step("Stopping.", call("auto_ask", run_id=RUN, note="enough for now")),
    )
    async with chat.client() as client:
        cid = await chat.conversation(client)
        await chat.say(client, cid, TEXT)
        await chat.finish()
        tenant = chat.tenants.of(AccountId(ALICE))
        damaged = run_of(chat, cid).run_id
        for record in sorted(run_dir(tenant.roots, damaged).iterdir()):
            if record.is_file():
                record.write_bytes(record.read_bytes() + b"tampered")
        later: list[list[Any]] = []
        for said in ("use PLA and try again", "and another message", "a plate under 150 g again"):
            seen = await chat.say(client, cid, said)
            await chat.finish()
            later.append(await chat.events(client, cid, after=seen))
    for events in later:
        assert "turn_failed" not in kinds(events)
        assert "agent" in kinds(events)
    refused = next(one for one in later[0] if one["kind"] == "tool_result")
    assert refused["is_error"]
    assert damaged in refused["text"]
    assert "cannot take more messages" not in refused["text"]
    assert "new project" not in refused["text"]
    assert "create a new brief to run Auto" in refused["text"]
    results = [one for one in later[2] if one["kind"] == "tool_result"]
    created, started = json.loads(results[0]["text"]), results[3]
    assert not started["is_error"], started["text"]
    opened = read_run(tenant.roots, json.loads(started["text"])["run_id"])
    assert (opened.run_id != damaged, opened.state.start.brief_id) == (True, created["brief_id"])
