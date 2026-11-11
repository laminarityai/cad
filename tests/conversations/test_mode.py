import pytest
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.auto import log
from cad.auto.model import Running, Stopped, StoppedByPerson
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.tenants import Tenants
from tests.support.conversations import (
    ACCEPT,
    ALICE,
    BOB,
    CID,
    INITIALIZE,
    agent_call,
    http,
    put_mode,
    records,
    start_briefless_run,
    stop,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("mode", ["design", "auto"])
async def test_the_person_switches_a_conversation_to_each_mode(
    app: Starlette, local: LocalIssuer, tenants: Tenants, mode: str
) -> None:
    store.create(tenants.of(ALICE).conversations, CID)
    answered = await put_mode(app, local.mint_person(ALICE), CID, mode)
    assert answered.status_code == 200
    assert answered.json() == {"conversation_id": CID, "mode": mode, "auto_run": None}
    held = store.read(tenants.of(ALICE).conversations, CID)
    assert held.mode == Mode(mode)


async def test_test_mode_is_refused_and_the_mode_stays(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.create(tenants.of(ALICE).conversations, CID)
    refused = await put_mode(app, local.mint_person(ALICE), CID, "test")
    assert refused.status_code == 422, refused.text
    assert store.read(tenants.of(ALICE).conversations, CID).mode is Mode.DESIGN


async def test_plan_is_not_a_mode_any_more(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.create(tenants.of(ALICE).conversations, CID)
    refused = await put_mode(app, local.mint_person(ALICE), CID, "plan")
    assert refused.status_code == 422, refused.text
    assert store.read(tenants.of(ALICE).conversations, CID).mode is Mode.DESIGN


async def test_a_new_conversation_is_in_design_so_a_brief_builds_at_once(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.create(tenants.of(ALICE).conversations, CID)
    assert store.read(tenants.of(ALICE).conversations, CID).mode is Mode.DESIGN
    token = local.mint_agent(ALICE, conversation=CID)
    built = await agent_call(app, token, "build_variant", code="result = None")
    assert "Plan mode" not in built.content[0].text


async def test_a_record_stored_in_plan_reads_as_design(tenants: Tenants) -> None:
    conversations = tenants.of(ALICE).conversations
    store.create(conversations, CID)
    path = conversations / f"{CID}.json"
    path.write_text(path.read_text().replace('"design"', '"plan"'))
    assert store.read(conversations, CID).mode is Mode.DESIGN


async def test_the_mode_the_person_sets_reaches_the_agents_next_call(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.create(tenants.of(ALICE).conversations, CID)
    person, agent = local.mint_person(ALICE), local.mint_agent(ALICE, conversation=CID)
    await put_mode(app, person, CID, "auto")
    in_auto = await agent_call(app, agent, "build_variant", code="result = None")
    assert in_auto.is_error
    assert "this conversation is in Auto mode, so call auto_start first" in in_auto.content[0].text
    await put_mode(app, person, CID, "design")
    in_design = await agent_call(app, agent, "build_variant", code="result = None")
    assert "this conversation is in Auto mode" not in in_design.content[0].text


async def test_one_conversations_mode_does_not_reach_another(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.create(tenants.of(ALICE).conversations, ConversationId("c-auto"))
    await put_mode(app, local.mint_person(ALICE), "c-auto", "auto")
    other = local.mint_agent(ALICE, conversation="c-other")
    built = await agent_call(app, other, "build_variant", code="result = None")
    assert "this conversation is in Auto mode" not in built.content[0].text


async def test_leaving_auto_stops_the_run_and_the_agent_cannot_revise_it(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    assert isinstance(log.read_run(tenants.of(ALICE).roots, run_id).state, Running)
    answered = await put_mode(app, local.mint_person(ALICE), CID, "design")
    assert answered.json() == {"conversation_id": CID, "mode": "design", "auto_run": None}
    stopped = log.read_run(tenants.of(ALICE).roots, run_id).state
    assert isinstance(stopped, Stopped)
    assert isinstance(stopped.reason, StoppedByPerson)
    assert records(tenants, ALICE, run_id) == 2
    refused = await agent_call(
        app,
        local.mint_agent(ALICE, conversation=CID),
        "auto_revise",
        run_id=run_id,
        code="result = None",
    )
    assert refused.is_error
    assert f"RunNotHeld: auto run {run_id} is not" in refused.content[0].text
    assert not tenants.of(ALICE).variants.exists()


async def test_setting_auto_again_keeps_the_run(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    answered = await put_mode(app, local.mint_person(ALICE), CID, "auto")
    assert answered.json()["auto_run"] == run_id
    assert isinstance(log.read_run(tenants.of(ALICE).roots, run_id).state, Running)


async def test_an_agent_token_cannot_set_the_mode(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.create(tenants.of(ALICE).conversations, CID)
    refused = await put_mode(app, local.mint_agent(ALICE, conversation=CID), CID, "design")
    assert refused.status_code == 401
    assert store.read(tenants.of(ALICE).conversations, CID).mode is Mode.DESIGN


@pytest.mark.parametrize("cid", ["bad.id", "a" * 65, "sp%20ace"])
async def test_a_bad_conversation_id_is_refused(
    app: Starlette, local: LocalIssuer, tenants: Tenants, cid: str
) -> None:
    refused = await put_mode(app, local.mint_person(ALICE), cid, "design")
    assert refused.status_code == 400
    assert refused.json()["error"].startswith("ModeRefused")
    assert not tenants.of(ALICE).conversations.exists()


async def test_a_body_that_is_not_a_mode_is_refused(app: Starlette, local: LocalIssuer) -> None:
    token = local.mint_person(ALICE)
    assert (await put_mode(app, token, CID, "turbo")).status_code == 422
    async with http(app, token) as client:
        not_an_object = await client.put(f"/v1/conversations/{CID}/mode", content=b"[1]")
        not_json = await client.put(f"/v1/conversations/{CID}/mode", content=b"{")
    assert (not_an_object.status_code, not_json.status_code) == (422, 422)


async def test_the_mode_comes_from_the_body_not_the_query_string(
    app: Starlette, local: LocalIssuer
) -> None:
    token = local.mint_person(ALICE)
    async with http(app, token) as client:
        refused = await client.put(f"/v1/conversations/{CID}/mode?mode=auto")
    assert refused.status_code == 422


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


async def test_the_persons_stop_moves_the_conversation_to_design_so_the_agent_cannot_restart(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    stopped = await stop(app, local.mint_person(ALICE), run_id)
    assert stopped.json()["conversation"] == {
        "conversation_id": CID,
        "mode": "design",
        "auto_run": None,
    }
    assert store.read(tenants.of(ALICE).conversations, CID).mode is Mode.DESIGN
    agent = local.mint_agent(ALICE, conversation=CID)
    restarted = await agent_call(app, agent, "auto_start", brief_id="b" * 16)
    assert restarted.is_error
    assert "this caller's mode is design" in restarted.content[0].text
    project_runs = log.run_dir(tenants.of(ALICE).roots, run_id).parent.iterdir()
    assert [path.name for path in project_runs if not path.name.startswith(".")] == [run_id]


async def test_the_persons_stop_of_an_earlier_run_leaves_the_conversations_mode(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    tenant = tenants.of(ALICE)
    store.set_mode(tenant.roots, tenant.conversations, CID, Mode.DESIGN)
    store.set_mode(tenant.roots, tenant.conversations, CID, Mode.AUTO)
    stopped = await stop(app, local.mint_person(ALICE), run_id)
    assert stopped.json()["conversation"]["mode"] == "auto"
    assert store.read(tenant.conversations, CID).mode is Mode.AUTO


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
        moded = await client.put(f"/v1/conversations/{cid}/mode", json={"mode": "design"})
        sent = await client.post(f"/v1/conversations/{cid}/messages", json={"text": "hi"})
        streamed = await client.get(f"/v1/conversations/{cid}/stream", params={"follow": "false"})
        stopped = await client.post(f"/v1/auto/{run_id}/stop")
    answered = [one.status_code for one in (moded, sent, streamed, stopped)]
    assert answered == [404, 404, 404, 404], [one.text for one in (moded, sent, streamed, stopped)]
    assert not tenants.of(BOB).conversations.exists()
    assert store.read(tenants.of(ALICE).conversations, ConversationId(cid)).mode is Mode.AUTO
    assert isinstance(log.read_run(tenants.of(ALICE).roots, run_id).state, Running)


async def test_an_unknown_conversation_is_404_for_mode_and_nothing_is_made(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    refused = await put_mode(app, local.mint_person(ALICE), CID, "design")
    assert refused.status_code == 404
    assert refused.json()["error"].startswith("UnknownConversation")
    assert not tenants.of(ALICE).conversations.exists()
