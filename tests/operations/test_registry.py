from collections.abc import Callable
from pathlib import Path

import pytest
from mcp import Client
from mcp.server import MCPServer
from pydantic import BaseModel

from cad.confirmations import http
from cad.confirmations.ballot import OS_OPEN, WAIT_SECONDS, Desk
from cad.confirmations.registry import kinds
from cad.context_parts.ingest import ingest
from cad.operations.model import BOTH, Audience, Input, Tenant, operation
from cad.operations.registry import OPERATIONS
from cad.operations.tools import agent_operations, tools
from cad.records.roots import Roots
from cad.server.app import build_server

pytestmark = pytest.mark.anyio


class Nothing(Input):
    pass


class Words(BaseModel):
    text: str


def say(text: str) -> Callable[[Tenant, Nothing], Words]:
    def run(tenant: Tenant, arguments: Nothing) -> Words:
        del tenant, arguments
        return Words(text=text)

    return run


def a_tenant(tmp_path: Path) -> Tenant:
    roots = Roots(briefs=tmp_path / "briefs", projects=tmp_path / "projects")
    desk = Desk(roots, kinds(roots), OS_OPEN, serve=http.serve, wait_seconds=WAIT_SECONDS)
    return Tenant(
        roots=roots,
        variants=tmp_path / "variants",
        geometry=tmp_path / "geometry",
        desk=desk,
        ingest=ingest,
    )


async def listed(server: MCPServer) -> dict[str, str]:
    async with Client(server) as client:
        return {tool.name: tool.description or "" for tool in (await client.list_tools()).tools}


def test_every_operation_has_its_own_name_and_a_description() -> None:
    names = [one.name for one in OPERATIONS]
    assert len(names) == len(set(names))
    assert all(one.description for one in OPERATIONS)


async def test_the_mcp_tool_list_equals_the_registrys_agent_operations() -> None:
    exposed = await listed(build_server())
    expected = {one.name: one.description for one in agent_operations(OPERATIONS)}
    assert exposed == expected


async def test_server_info_names_the_same_tools_the_server_lists() -> None:
    async with Client(build_server()) as client:
        info = await client.call_tool("server_info", {})
        names = sorted(tool.name for tool in (await client.list_tools()).tools)
    assert info.structured_content is not None
    assert info.structured_content["tools"] == names


async def test_an_operation_only_the_person_may_reach_is_not_a_tool(tmp_path: Path) -> None:
    mine = operation(
        name="mine",
        audience=Audience.PERSON,
        description="Person.",
        input=Nothing,
        output=Words,
        run=say("mine"),
    )
    ours = operation(
        name="ours",
        audience=BOTH,
        description="Both.",
        input=Nothing,
        output=Words,
        run=say("ours"),
    )
    theirs = operation(
        name="theirs",
        audience=Audience.AGENT,
        description="Agent.",
        input=Nothing,
        output=Words,
        run=say("theirs"),
    )
    server = MCPServer("test", tools=tools(a_tenant(tmp_path), (mine, ours, theirs)))
    assert sorted(await listed(server)) == ["ours", "theirs"]
    async with Client(server) as client:
        refused = await client.call_tool("mine", {})
        reached = await client.call_tool("ours", {})
    assert refused.is_error
    assert reached.structured_content == {"text": "ours"}


async def test_a_tool_refuses_an_argument_its_operation_does_not_declare(tmp_path: Path) -> None:
    ours = operation(
        name="ours",
        audience=BOTH,
        description="Both.",
        input=Nothing,
        output=Words,
        run=say("ours"),
    )
    server = MCPServer("test", tools=tools(a_tenant(tmp_path), (ours,)))
    async with Client(server) as client:
        result = await client.call_tool("ours", {"surprise": 1})
    assert result.is_error
