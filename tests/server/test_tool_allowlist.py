import pytest
from mcp import Client

from cad.server.app import build_server

pytestmark = pytest.mark.anyio

ALLOWED_ARGUMENTS = {
    "server_info": set[str](),
    "build_variant": {"code", "brief_id", "slot"},
    # own_measurements is the agent's measuring code, shown as not verified, never a verdict.
    "score_variant": {"variant_id", "material_key", "brief_id", "own_measurements"},
    "scorecard": {"variant_id", "material_key", "brief_id"},
    "list_materials": set[str](),
    "create_brief": {"text", "project_id"},
    "propose_requirements": {"brief_id", "requirements"},
    "ask_to_confirm": {"project_id"},
    "list_requirements": {"brief_id"},
    "propose_context_part": {"brief_id", "quote", "name", "variant_id"},
    "search_knowledge": {"query", "k"},
    "submit_research": {"brief_id", "key", "field", "value", "unit", "url", "quote"},
    # The agent gives code or a note; the run's verdict comes from the server's scorecards.
    "auto_start": {"brief_id", "material_key"},
    "auto_revise": {"run_id", "code", "slot"},
    "auto_ask": {"run_id", "note"},
    # Reads, so the agent finds the slots and their code itself and never asks the person.
    "variant_set": {"project_id", "brief_id", "material_key"},
    "variant_code": {"variant_id"},
}


async def listed_arguments() -> dict[str, set[str]]:
    async with Client(build_server()) as client:
        listed = await client.list_tools()
    return {tool.name: set(tool.input_schema.get("properties", {})) for tool in listed.tools}


async def test_no_tool_takes_a_check_a_table_a_scorecard_or_a_decision_as_an_argument() -> None:
    assert await listed_arguments() == ALLOWED_ARGUMENTS
