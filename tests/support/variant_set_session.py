from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import Client

from cad.records.roots import Roots
from tests.support.rows import UNDER_150

TEXT = "A PLA plate under 150 g"
PLA = {"target": {"kind": "made_of", "material": "prusament-pla"}, "quote": "PLA"}


@dataclass
class Session:
    client: Client
    tmp: Path

    async def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = await self.client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return result.structured_content

    async def refusal(self, tool: str, **arguments: Any) -> str:
        result = await self.client.call_tool(tool, arguments)
        assert result.is_error
        return result.content[0].model_dump()["text"]

    @property
    def roots(self) -> Roots:
        return Roots(self.tmp / "briefs", self.tmp / "projects")

    async def proposed_brief(
        self, project_id: str | None = None, text: str = TEXT, *rows: dict[str, Any]
    ) -> str:
        joined = {} if project_id is None else {"project_id": project_id}
        brief_id = (await self.call("create_brief", text=text, **joined))["brief_id"]
        await self.call(
            "propose_requirements", brief_id=brief_id, requirements=list(rows or [PLA, UNDER_150])
        )
        return brief_id

    async def confirm(self, brief_id: str) -> None:
        listed = await self.call("list_requirements", brief_id=brief_id)
        answer = await self.call("ask_to_confirm", project_id=listed["project_id"])
        assert answer["status"] == "answered", answer

    async def confirmed_brief(self) -> str:
        brief_id = await self.proposed_brief()
        await self.confirm(brief_id)
        return brief_id
