import json
from pathlib import Path
from typing import Any, Literal

import mcp_types
import pytest
from mcp import Client
from mcp.client.context import ClientRequestContext
from mcp.server import MCPServer

from cad.accounts.tenants import open_tenant
from cad.confirmations.waiting import Door, page_address
from cad.context_parts.ingest import ingest
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools
from cad.records.roots import Roots
from cad.server.app import LOCAL

pytestmark = pytest.mark.anyio
ORIGIN = "https://cad.example"
TEXT = "A wall bracket under 150 g"
UNDER_150 = {
    "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
    "quote": "under 150 g",
}
type Mode = Literal["auto", "legacy"]


@pytest.fixture
def server(tmp_path: Path) -> MCPServer:
    roots = Roots(tmp_path / "briefs", tmp_path / "projects")
    door = Door(page_url=page_address(ORIGIN), wait_seconds=0.2)
    tenant = open_tenant(
        LOCAL, roots, tmp_path / "variants", tmp_path / "geometry", None, door, ingest
    )
    return MCPServer("cad", tools=tools(lambda: tenant, OPERATIONS))


async def proposed(client: Client) -> str:
    created = await client.call_tool("create_brief", {"text": TEXT})
    assert created.structured_content is not None
    brief_id = created.structured_content["brief_id"]
    proposal = {"brief_id": brief_id, "requirements": [UNDER_150]}
    assert not (await client.call_tool("propose_requirements", proposal)).is_error
    return created.structured_content["project_id"]


def everything(result: mcp_types.CallToolResult) -> str:
    blocks = json.dumps([block.model_dump() for block in result.content])
    return blocks + json.dumps(result.structured_content)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_a_client_that_opens_urls_is_asked_to_open_the_page(
    server: MCPServer, mode: Mode
) -> None:
    asked: list[mcp_types.ElicitRequestParams] = []

    async def elicit(
        context: ClientRequestContext, params: mcp_types.ElicitRequestParams
    ) -> mcp_types.ElicitResult:
        del context
        asked.append(params)
        return mcp_types.ElicitResult(action="accept")

    async with Client(server, mode=mode, elicitation_callback=elicit) as client:
        project_id = await proposed(client)
        result = await client.call_tool("ask_to_confirm", {"project_id": project_id})
    [one] = asked
    assert isinstance(one, mcp_types.ElicitRequestURLParams)
    assert one.url == f"{ORIGIN}/projects/{project_id}/confirm"
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["status"] == "pending"
    assert "http" not in everything(result)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_a_client_that_cannot_open_urls_is_told_the_page_waits_in_the_web_app(
    server: MCPServer, mode: Mode
) -> None:
    async with Client(server, mode=mode) as client:
        project_id = await proposed(client)
        result = await client.call_tool("ask_to_confirm", {"project_id": project_id})
    assert result.structured_content is not None
    assert result.structured_content["status"] == "pending"
    assert "waiting in the web app" in result.structured_content["next"]
    assert "http" not in everything(result)


async def test_nothing_waiting_asks_the_client_for_nothing(server: MCPServer) -> None:
    asked: list[Any] = []

    async def elicit(context: ClientRequestContext, params: Any) -> mcp_types.ElicitResult:
        asked.append((context, params))
        return mcp_types.ElicitResult(action="accept")

    async with Client(server, elicitation_callback=elicit) as client:
        created = await client.call_tool("create_brief", {"text": TEXT})
        assert created.structured_content is not None
        project_id = created.structured_content["project_id"]
        result = await client.call_tool("ask_to_confirm", {"project_id": project_id})
    assert result.structured_content is not None
    assert result.structured_content["status"] == "nothing_to_confirm"
    assert asked == []


async def test_answer_page_is_no_tool(server: MCPServer) -> None:
    async with Client(server) as client:
        listed = await client.list_tools()
    assert "answer_page" not in {tool.name for tool in listed.tools}
    assert "ask_to_confirm" in {tool.name for tool in listed.tools}
