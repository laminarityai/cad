from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId
from cad.server.app import build_server

pytestmark = pytest.mark.anyio


async def test_a_second_brief_joins_the_project_the_first_one_started(tmp_path: Path) -> None:
    async with Client(build_server(briefs_root=tmp_path)) as client:
        first: Any = await client.call_tool("create_brief", {"text": "a hook"})
        project = first.structured_content["project_id"]
        second: Any = await client.call_tool(
            "create_brief", {"text": "a second hook", "project_id": project}
        )
        listed: Any = await client.call_tool(
            "list_requirements", {"brief_id": second.structured_content["brief_id"]}
        )
        unknown: Any = await client.call_tool(
            "create_brief", {"text": "a third hook", "project_id": "p-" + "0" * 16}
        )
    assert second.structured_content["project_id"] == project
    assert listed.structured_content["project_id"] == project
    assert project_briefs(tmp_path, ProjectId(project)) == (
        first.structured_content["brief_id"],
        second.structured_content["brief_id"],
    )
    assert unknown.is_error
    assert "UnknownProject: no project p-0000000000000000 is stored" in unknown.content[0].text
