import pytest
from mcp import Client

from cad.server.app import build_server

pytestmark = pytest.mark.anyio

ALLOWED_ARGUMENTS = {
    "server_info": set[str](),
    "build_variant": {"code", "brief_id"},
    # own_measurements is the agent's measuring code, shown as not verified, never a verdict.
    "score_variant": {"variant_id", "material_key", "brief_id", "own_measurements"},
    "list_materials": set[str](),
    "create_brief": {"text", "project_id"},
    "propose_requirements": {"brief_id", "requirements"},
    "ask_to_confirm": {"project_id"},
    "list_requirements": {"brief_id"},
    "search_knowledge": {"query", "k"},
    "submit_research": {"brief_id", "key", "field", "value", "unit", "url", "quote"},
}


async def listed_arguments() -> dict[str, set[str]]:
    async with Client(build_server()) as client:
        listed = await client.list_tools()
    return {tool.name: set(tool.input_schema.get("properties", {})) for tool in listed.tools}


async def test_the_server_exposes_no_tool_outside_the_allowlist() -> None:
    exposed = await listed_arguments()
    extra = sorted(set(exposed) - set(ALLOWED_ARGUMENTS))
    assert extra == [], f"tools outside the allowlist: {extra}"
    assert sorted(exposed) == sorted(ALLOWED_ARGUMENTS)


async def test_no_tool_takes_a_check_a_table_a_scorecard_or_a_decision_as_an_argument() -> None:
    assert await listed_arguments() == ALLOWED_ARGUMENTS
