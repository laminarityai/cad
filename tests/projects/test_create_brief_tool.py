from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.server.app import build_server

pytestmark = pytest.mark.anyio


def roots(tmp_path: Path) -> Roots:
    return Roots(tmp_path / "briefs", tmp_path / "projects")


async def test_a_second_brief_joins_the_project_the_first_one_started(tmp_path: Path) -> None:
    async with Client(build_server(roots=roots(tmp_path))) as client:
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
    assert project_briefs(roots(tmp_path), ProjectId(project)) == (
        first.structured_content["brief_id"],
        second.structured_content["brief_id"],
    )
    assert unknown.is_error
    assert "UnknownProject: no project p-0000000000000000 is stored" in unknown.content[0].text


@pytest.mark.parametrize(
    ("project_id", "refusal"),
    [
        ("pb-" + "0" * 16, "UnknownProject: project pb-0000000000000000 holds only the brief"),
        ("../briefs", "String should match pattern"),
        ("p-" + "0" * 400, "String should have at most 19 characters"),
    ],
)
async def test_create_brief_refuses_a_project_it_cannot_join(
    tmp_path: Path, project_id: str, refusal: str
) -> None:
    async with Client(build_server(roots=roots(tmp_path))) as client:
        result: Any = await client.call_tool(
            "create_brief", {"text": "a hook", "project_id": project_id}
        )
    assert result.is_error
    assert refusal in result.content[0].text
    assert not (tmp_path / "briefs").exists()


async def test_an_outside_client_passes_the_persons_words_and_their_later_words(
    tmp_path: Path,
) -> None:
    later = {
        "target": {"kind": "max_mass", "mass": {"magnitude": 120, "unit": "g"}},
        "quote": "under 120 g",
    }
    async with Client(build_server(roots=roots(tmp_path))) as client:
        missing: Any = await client.call_tool("create_brief", {})
        made: Any = await client.call_tool("create_brief", {"text": "a hook"})
        brief_id = made.structured_content["brief_id"]
        unsaid: Any = await client.call_tool(
            "propose_requirements", {"brief_id": brief_id, "requirements": [later]}
        )
        said: Any = await client.call_tool(
            "propose_requirements",
            {"brief_id": brief_id, "requirements": [later], "said": "keep it under 120 g"},
        )
        listed: Any = await client.call_tool("list_requirements", {"brief_id": brief_id})
    assert missing.is_error
    assert "pass text" in missing.content[0].text
    assert made.structured_content["text"] == "a hook"
    assert unsaid.is_error
    assert "pass the person's new words as said" in unsaid.content[0].text
    assert said.structured_content["proposal"] == 1
    assert listed.structured_content["text"] == "a hook\n\nkeep it under 120 g"
