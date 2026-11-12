import json

import pytest
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.auto import log
from cad.auto.model import Running
from cad.conversations import store
from cad.conversations.model import ConversationId
from cad.operations.tenants import Tenants
from tests.support.conversations import (
    ACCEPT,
    ALICE,
    BOB,
    CID,
    INITIALIZE,
    agent_call,
    http,
    records,
    start_briefless_run,
    stop,
)

pytestmark = pytest.mark.anyio

NO_CONTAINER = "this test starts no container"


async def test_a_new_conversation_builds_at_once(
    app: Starlette, local: LocalIssuer, tenants: Tenants, started: list[str]
) -> None:
    store.create(tenants.of(ALICE).conversations, CID)
    token = local.mint_agent(ALICE, conversation=CID)
    built = await agent_call(app, token, "build_variant", code="result = None")
    assert NO_CONTAINER in built.content[0].text
    assert len(started) == 1


@pytest.mark.parametrize("mode", ["design", "auto", "plan"])
async def test_a_record_stored_with_a_mode_still_reads(tenants: Tenants, mode: str) -> None:
    conversations = tenants.of(ALICE).conversations
    stored = {"mode": mode, "auto_run": "r1", "project_id": "p-" + "0" * 16}
    conversations.mkdir(parents=True)
    (conversations / f"{CID}.json").write_text(json.dumps(stored))
    held = store.read(conversations, CID)
    assert (held.auto_run, held.stopped_run, held.project_id) == ("r1", None, "p-" + "0" * 16)


async def test_the_person_stops_a_running_run_and_a_replay_records_nothing(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    person = local.mint_person(ALICE)
    stopped = await stop(app, person, run_id)
    assert stopped.status_code == 200
    assert stopped.json()["run"]["state"]["reason"] == {"kind": "stopped_by_person"}
    assert "The person stopped the run." in stopped.json()["run"]["state"]["report"]
    assert records(tenants, ALICE, run_id) == 2
    again = await stop(app, person, run_id)
    assert again.json() == stopped.json()
    assert records(tenants, ALICE, run_id) == 2


async def test_the_persons_stop_holds_the_conversation_against_every_agent_call(
    app: Starlette, local: LocalIssuer, tenants: Tenants, started: list[str]
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    stopped = await stop(app, local.mint_person(ALICE), run_id)
    assert stopped.json()["conversation"] == {
        "conversation_id": CID,
        "auto_run": None,
        "stopped_run": run_id,
    }
    agent = local.mint_agent(ALICE, conversation=CID)
    calls = {
        "auto_revise": {"run_id": run_id, "code": "result = None"},
        "auto_ask": {"run_id": run_id, "note": "again"},
        "build_variant": {"code": "result = None"},
        "score_variant": {"variant_id": "0" * 16},
    }
    for tool, arguments in calls.items():
        refused = await agent_call(app, agent, tool, **arguments)
        assert refused.is_error, tool
        assert f"auto run {run_id} has stopped" in refused.content[0].text, tool
    held = store.read(tenants.of(ALICE).conversations, CID)
    assert (held.auto_run, held.stopped_run) == (None, run_id)
    project_runs = log.run_dir(tenants.of(ALICE).roots, run_id).parent.iterdir()
    assert [path.name for path in project_runs if not path.name.startswith(".")] == [run_id]
    assert (started, records(tenants, ALICE, run_id)) == ([], 2)


async def test_one_conversations_hold_does_not_reach_another(
    app: Starlette, local: LocalIssuer, tenants: Tenants, started: list[str]
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    await stop(app, local.mint_person(ALICE), run_id)
    other = local.mint_agent(ALICE, conversation="c-other")
    built = await agent_call(app, other, "build_variant", code="result = None")
    assert NO_CONTAINER in built.content[0].text
    assert len(started) == 1


async def test_an_agent_token_cannot_stop_a_run(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    refused = await stop(app, local.mint_agent(ALICE, conversation=CID), run_id)
    assert refused.status_code == 401
    assert isinstance(log.read_run(tenants.of(ALICE).roots, run_id).state, Running)


async def test_another_account_cannot_stop_a_run_it_does_not_hold(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    refused = await stop(app, local.mint_person(BOB), run_id)
    assert refused.status_code == 404
    assert refused.json()["error"].startswith("UnknownRun")
    assert isinstance(log.read_run(tenants.of(ALICE).roots, run_id).state, Running)


@pytest.mark.parametrize("cid", ["bad.id", "a" * 65, "sp%20ace"])
async def test_a_bad_conversation_id_is_refused(
    app: Starlette, local: LocalIssuer, tenants: Tenants, cid: str
) -> None:
    async with http(app, local.mint_person(ALICE)) as client:
        refused = await client.get(f"/v1/conversations/{cid}")
    assert refused.status_code == 400
    assert refused.json()["error"].startswith("ConversationRefused")
    assert not tenants.of(ALICE).conversations.exists()


async def test_a_token_with_a_malformed_conversation_claim_gets_401(
    app: Starlette, local: LocalIssuer
) -> None:
    for claim in ("../escape", "", "a" * 65):
        async with http(app, local.mint_agent(ALICE, conversation=claim)) as client:
            refused = await client.post("/mcp", json=INITIALIZE, headers=ACCEPT)
        assert refused.status_code == 401, claim


async def test_another_accounts_conversation_is_404_on_every_route_and_nothing_is_made(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    alice, bob = local.mint_person(ALICE), local.mint_person(BOB)
    async with http(app) as client:
        client.cookies.set("__session", alice)
        made = await client.post("/v1/conversations", json={})
    cid = made.json()["conversation_id"]
    run_id = start_briefless_run(tenants, ALICE, ConversationId(cid))
    async with http(app) as client:
        client.cookies.set("__session", bob)
        read = await client.get(f"/v1/conversations/{cid}")
        sent = await client.post(f"/v1/conversations/{cid}/messages", json={"text": "hi"})
        streamed = await client.get(f"/v1/conversations/{cid}/stream", params={"follow": "false"})
        stopped = await client.post(f"/v1/auto/{run_id}/stop")
    answered = [one.status_code for one in (read, sent, streamed, stopped)]
    assert answered == [404, 404, 404, 404], [one.text for one in (read, sent, streamed, stopped)]
    assert not tenants.of(BOB).conversations.exists()
    assert store.read(tenants.of(ALICE).conversations, ConversationId(cid)).auto_run == run_id
    assert isinstance(log.read_run(tenants.of(ALICE).roots, run_id).state, Running)


async def test_an_unknown_conversation_is_404_and_nothing_is_made(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    async with http(app, local.mint_person(ALICE)) as client:
        refused = await client.get(f"/v1/conversations/{CID}")
    assert refused.status_code == 404
    assert refused.json()["error"].startswith("UnknownConversation")
    assert not tenants.of(ALICE).conversations.exists()
