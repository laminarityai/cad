import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import Client

from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, BuildFailed, Built
from cad.variants import entry
from tests.support.browser import Person, request
from tests.support.rows import RAIL, TEXT, Rows


@dataclass(frozen=True)
class Proposed:
    brief_id: str
    project_id: str


@dataclass
class Session:
    """An MCP client on an in-process server, and the person's browser (plain HTTP)."""

    client: Client
    person: Person
    roots: Roots
    variants: Path
    rows: Rows = field(default_factory=Rows)
    request = staticmethod(request)

    def get(self, url: str, **headers: str) -> tuple[int, str]:
        return self.person.get(url, **headers)

    def post(
        self,
        url: str,
        answer: str,
        note: str = "",
        fields: dict[str, str] | None = None,
        **headers: str,
    ) -> tuple[int, str]:
        return self.person.post(url, answer, note, fields, **headers)

    async def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = await self.client.call_tool(tool, arguments)
        assert not result.is_error, result.content
        assert result.structured_content is not None
        return result.structured_content

    async def text(self, tool: str, **arguments: Any) -> str:
        """Everything a client sees from one call, ok or error."""
        result = await self.client.call_tool(tool, arguments)
        blocks = json.dumps([block.model_dump() for block in result.content])
        return blocks + json.dumps(result.structured_content)

    async def proposed(
        self, *requirements: dict[str, Any], project_id: str | None = None
    ) -> Proposed:
        joined = {} if project_id is None else {"project_id": project_id}
        created = await self.call("create_brief", text=TEXT, **joined)
        brief_id = created["brief_id"]
        await self.call("propose_requirements", brief_id=brief_id, requirements=list(requirements))
        return Proposed(brief_id, created["project_id"])

    async def ask(self, proposed: Proposed) -> dict[str, Any]:
        return await self.call("ask_to_confirm", project_id=proposed.project_id)

    def variant(self, code: str, brep: bytes | None = RAIL) -> str:
        vid = entry.variant_id(code, image_tag(BUILD))
        built = Build(outcome=Built(), output="")
        failed = Build(outcome=BuildFailed(error="NameError", traceback=""), output="")
        entry.save(self.variants, vid, code, built if brep else failed, brep)
        return vid
