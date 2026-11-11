import pytest
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.confirmations.web import LocalSignIn
from cad.operations.tenants import Tenants
from cad.server.hosted import build_app
from tests.support.conversations import ALICE, CID, http, start_briefless_run, stop

pytestmark = pytest.mark.anyio


async def test_a_stop_from_another_tab_shows_in_the_read_after_a_restart(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    tab_a, tab_b = local.mint_person(ALICE), local.mint_person(ALICE)
    async with http(app, tab_a) as client:
        running = (await client.get(f"/v1/conversations/{CID}")).json()
    await stop(app, tab_b, run_id)
    restarted = build_app(local.issuer(), tenants, LocalSignIn(local))
    async with restarted.router.lifespan_context(restarted), http(restarted, tab_a) as client:
        stopped = (await client.get(f"/v1/conversations/{CID}")).json()
    assert (running["mode"], running["run"]["state"]["kind"]) == ("auto", "running")
    assert (stopped["mode"], stopped["auto_run"]) == ("design", None)
    assert stopped["run"]["run_id"] == run_id
    assert stopped["run"]["state"]["reason"]["kind"] == "stopped_by_person"


async def test_picking_auto_again_keeps_the_stopped_run_until_a_new_one_starts(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    run_id = start_briefless_run(tenants, ALICE, CID)
    person = local.mint_person(ALICE)
    await stop(app, person, run_id)
    async with http(app, person) as client:
        await client.put(f"/v1/conversations/{CID}/mode", json={"mode": "auto"})
        read = (await client.get(f"/v1/conversations/{CID}")).json()
    assert (read["mode"], read["auto_run"], read["run"]["run_id"]) == ("auto", None, run_id)
