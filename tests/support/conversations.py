from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Final

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette

from cad.accounts.principal import AccountId
from cad.auto import log
from cad.auto.model import AutoRun, Started, nth_run_id
from cad.conversations import store
from cad.conversations.model import ConversationId, Mode
from cad.operations.tenants import Tenants
from cad.projects.model import ProjectId
from tests.support.hosted import BASE, MCP

ALICE: Final = AccountId("user_alice")
BOB: Final = AccountId("user_bob")
CID: Final = ConversationId("c-1")
PROJECT: Final = ProjectId("p-" + "0" * 16)
INITIALIZE: Final = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
ACCEPT: Final = {"Accept": "application/json, text/event-stream"}


@asynccontextmanager
async def http(app: Starlette, token: str | None = None) -> AsyncGenerator[httpx2.AsyncClient]:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url=BASE, headers=headers) as client:
        yield client


async def put_mode(app: Starlette, token: str, cid: str, mode: str) -> httpx2.Response:
    async with http(app, token) as client:
        return await client.put(f"/v1/conversations/{cid}/mode", json={"mode": mode})


async def stop(app: Starlette, token: str, run_id: str) -> httpx2.Response:
    async with http(app, token) as client:
        return await client.post(f"/v1/auto/{run_id}/stop")


async def agent_call(app: Starlette, token: str, tool: str, **arguments: Any) -> Any:
    async with (
        http(app, token) as client,
        Client(streamable_http_client(MCP, http_client=client)) as mcp,
    ):
        return await mcp.call_tool(tool, arguments)


def start_briefless_run(tenants: Tenants, account: AccountId, cid: ConversationId) -> str:
    tenant = tenants.of(account)
    store.create(tenant.conversations, cid)
    store.set_mode(tenant.roots, tenant.conversations, cid, Mode.AUTO)
    run_id = nth_run_id(PROJECT, "b" * 16, 1)
    started = Started(
        conversation=cid,
        brief_id="b" * 16,
        project=PROJECT,
        decision_sha256="d" * 64,
        material_key="prusament-pla",
        watermark=(),
        conflicts=(),
    )

    def open_under_lock() -> AutoRun:
        log.create_run(tenant.roots, run_id, started)
        return log.read_run(tenant.roots, run_id)

    return store.start_run(
        tenant.roots, tenant.conversations, cid, started.brief_id, open_under_lock
    ).run_id


def records(tenants: Tenants, account: AccountId, run_id: str) -> int:
    return len(list(log.run_dir(tenants.of(account).roots, run_id).glob("*.signed")))
