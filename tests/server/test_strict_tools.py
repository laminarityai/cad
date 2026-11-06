import pytest
from mcp import Client

from cad.server.app import build_server

pytestmark = pytest.mark.anyio


async def test_every_tool_rejects_undeclared_arguments() -> None:
    async with Client(build_server()) as client:
        listed = await client.list_tools()
    lax = [
        tool.name
        for tool in listed.tools
        if tool.input_schema.get("additionalProperties") is not False
    ]
    assert lax == [], f"tools that silently drop misspelled arguments: {lax}"
