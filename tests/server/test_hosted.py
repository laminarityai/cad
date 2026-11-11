import os
import subprocess
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Door
from cad.confirmations.web import LocalSignIn
from cad.context_parts.ingest import ingest
from cad.operations.tenants import Tenants
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.server.hosted import build_app, choose_issuer
from cad.server.probe import free_port, wait_until_up
from cad.variants import entry

pytestmark = pytest.mark.anyio

BASE = "http://127.0.0.1:8765"
MCP = f"{BASE}/mcp"
CODE = "result = None"
RAIL = b"CASCADE Topology V3, a rail\n"


@pytest.fixture
def local(tmp_path: Path) -> LocalIssuer:
    return LocalIssuer.open(tmp_path, BASE)


@pytest.fixture
def tenants(tmp_path: Path) -> Tenants:
    return Tenants(tmp_path / "accounts", 60, Door(wait_seconds=0.3), ingest)


@pytest.fixture
async def app(local: LocalIssuer, tenants: Tenants) -> AsyncIterator[Starlette]:
    app = build_app(local.issuer(), tenants, LocalSignIn(local))
    async with app.router.lifespan_context(app):
        yield app


@asynccontextmanager
async def http(app: Starlette, token: str | None = None) -> AsyncGenerator[httpx2.AsyncClient]:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url=BASE, headers=headers) as client:
        yield client


async def call(app: Starlette, token: str, tool: str, **arguments: Any) -> Any:
    async with (
        http(app, token) as client,
        Client(streamable_http_client(MCP, http_client=client)) as mcp,
    ):
        return await mcp.call_tool(tool, arguments)


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
ACCEPT = {"Accept": "application/json, text/event-stream"}


async def test_the_metadata_names_the_issuer_and_mcp_challenges_without_a_token(
    app: Starlette,
) -> None:
    async with http(app) as client:
        metadata = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
        challenged = await client.post("/mcp", json=INITIALIZE, headers=ACCEPT)
    assert metadata["resource"] == MCP
    assert metadata["authorization_servers"] == ["http://127.0.0.1/cad-local-issuer"]
    assert challenged.status_code == 401
    assert "oauth-protected-resource/mcp" in challenged.headers["www-authenticate"]


async def test_the_metadata_names_a_bare_origin_issuer_exactly(
    local: LocalIssuer, tenants: Tenants
) -> None:
    clerk = replace(local.issuer(), url="https://neat-beetle-7570.clerk.accounts.dev")
    async with http(build_app(clerk, tenants, LocalSignIn(local))) as client:
        metadata = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
    assert metadata["authorization_servers"] == ["https://neat-beetle-7570.clerk.accounts.dev"]
    assert metadata["resource"] == MCP


async def test_a_session_token_on_mcp_gets_401(app: Starlette, local: LocalIssuer) -> None:
    async with http(app, local.mint_person("user_alice")) as client:
        refused = await client.post("/mcp", json=INITIALIZE, headers=ACCEPT)
    assert refused.status_code == 401


async def test_an_agent_token_on_a_web_route_gets_401(app: Starlette, local: LocalIssuer) -> None:
    path = "/v1/variants/0123456789abcdef/scorecard?material_key=prusament-pla"
    async with http(app, local.mint_agent("user_alice")) as client:
        refused = await client.get(path)
    async with http(app) as client:
        client.cookies.set("__session", local.mint_person("user_alice"))
        reached = await client.get(path)
    assert refused.status_code == 401
    assert reached.status_code == 404
    assert reached.json()["error"].startswith("UnknownVariant")


async def test_an_agent_token_reaches_the_tools(app: Starlette, local: LocalIssuer) -> None:
    result = await call(app, local.mint_agent("user_alice"), "server_info")
    assert not result.is_error
    assert "build_variant" in result.structured_content["tools"]


async def test_another_account_gets_unknown_variant_for_a_variant_it_did_not_build(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    vid = entry.variant_id(CODE, image_tag(BUILD))
    alice = tenants.of(AccountId("user_alice"))
    entry.save(alice.variants, vid, CODE, Build(outcome=Built(), output=""), RAIL)
    asked = {"variant_id": vid, "material_key": "prusament-pla"}
    bob = await call(app, local.mint_agent("user_bob"), "scorecard", **asked)
    alices = await call(app, local.mint_agent("user_alice"), "scorecard", **asked)
    assert bob.is_error
    assert "UnknownVariant" in bob.content[0].text
    assert "UnknownVariant" not in str(alices.content)


def test_the_local_issuer_serves_only_on_a_loopback_address(tmp_path: Path) -> None:
    assert choose_issuer(tmp_path, "127.0.0.1", 8765, {}).resource == MCP
    with pytest.raises(SystemExit, match="CLERK_PUBLISHABLE_KEY"):
        choose_issuer(tmp_path, "0.0.0.0", 8765, {})


@pytest.mark.usefixtures("alone_removing_orphans")
def test_the_link_cad_http_prints_signs_the_person_in_to_their_workspace(tmp_path: Path) -> None:
    port = free_port()
    command = (sys.executable, "-m", "cad.server.hosted", "--root", str(tmp_path))
    server = subprocess.Popen(
        (*command, "--port", str(port), "--account", "user_alice"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "ANTHROPIC_API_KEY": "unused"},
    )
    try:
        assert server.stdout is not None
        link = server.stdout.readline().decode().removeprefix("cad-http: sign in at ").strip()
        wait_until_up(f"http://127.0.0.1:{port}", server)
        with httpx2.Client() as client:
            landed = client.get(link)
            projects = client.get(f"http://127.0.0.1:{port}/v1/projects")
    finally:
        server.terminate()
        server.wait(10)
    assert (landed.status_code, landed.headers["location"]) == (303, "/app/")
    assert projects.status_code == 200, projects.text
