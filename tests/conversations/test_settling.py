import pytest
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.operations import conversations
from cad.operations.tenants import Tenants
from tests.support.conversations import ALICE, CID, http, start_briefless_run

pytestmark = pytest.mark.anyio


async def read(app: Starlette, local: LocalIssuer) -> bool:
    async with http(app, local.mint_person(ALICE)) as client:
        found = await client.get(f"/v1/conversations/{CID}")
    assert found.status_code == 200, found.text
    return found.json()["checks_settling"]


async def test_a_running_run_reads_as_settling_only_while_its_checks_are_queued_or_running(
    app: Starlette, local: LocalIssuer, tenants: Tenants, monkeypatch: pytest.MonkeyPatch
) -> None:
    start_briefless_run(tenants, ALICE, CID)
    assert not await read(app, local)
    busy = {"now": True}

    def no_key(*_args: object) -> None:
        return None

    def no_members(*_args: object) -> tuple[()]:
        return ()

    def is_busy(*_args: object) -> bool:
        return busy["now"]

    monkeypatch.setattr(conversations, "set_key", no_key)
    monkeypatch.setattr(conversations, "members", no_members)
    monkeypatch.setattr(conversations.LANES, "busy", is_busy)
    assert await read(app, local)
    busy["now"] = False
    assert not await read(app, local)
