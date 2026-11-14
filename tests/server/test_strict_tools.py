import pytest
from mcp import Client

from cad.server.app import build_server
from cad.variant_sets.model import MAX_MEMBERS

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


async def test_every_slot_argument_advertises_the_slots_a_set_has() -> None:
    async with Client(build_server()) as client:
        listed = await client.list_tools()
    slots = {
        tool.name: tool.input_schema["properties"]["slot"]
        for tool in listed.tools
        if "slot" in tool.input_schema.get("properties", {})
    }
    assert {"build_variant", "auto_revise"} <= set(slots)
    numbered = {"type": "integer", "minimum": 1, "maximum": MAX_MEMBERS}
    assert {name for name, slot in slots.items() if numbered not in slot["anyOf"]} == set()
